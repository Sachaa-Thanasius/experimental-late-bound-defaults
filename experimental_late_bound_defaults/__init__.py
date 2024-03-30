"""An attempt at an implementation of PEP 671 (late-bound function defaults) in "pure" Python."""

from __future__ import annotations

import ast
import codecs
import ctypes
import sys
import tokenize
from collections import deque
from collections.abc import Callable, Generator, Iterable
from encodings import utf_8
from io import StringIO
from itertools import takewhile
from typing import Generic, ParamSpec, TypeGuard, TypeVar

T = TypeVar("T")
P = ParamSpec("P")


# === The parts that will actually do the work of implementing late binding argument defaults.


class _defer(Generic[P, T]):
    """A class that holds the functions used for late binding in function signatures."""

    def __init__(self, func: Callable[P, T]):
        self.func = func

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return self.func(*args, **kwargs)


def _evaluate_late_binding(orig_locals: dict[str, object]) -> None:
    """Does the actual work of evaluating the late bindings and assigning them to the locals."""

    # Evaluate the late-bound function argument defaults (i.e. those with type `_defer`).
    new_locals = orig_locals.copy()
    for arg_name, arg_val in orig_locals.items():
        if isinstance(arg_val, _defer):
            new_locals[arg_name] = arg_val(*takewhile(lambda val: not isinstance(val, _defer), new_locals.values()))

    # Update the locals of the last frame with these new evaluated defaults.
    frame = sys._getframe(1)
    try:
        frame.f_locals.update(new_locals)
        ctypes.pythonapi.PyFrame_LocalsToFast(ctypes.py_object(frame), ctypes.c_int(0))
    finally:
        del frame


# === Token modification.


class Peekable(Generic[T]):
    # Implementation of this class is copied from https://github.com/mikeshardmind/discord-rolebot/blob/main/rolebot/encoder.py
    # which is available under the MPL License here: https://github.com/mikeshardmind/discord-rolebot/blob/main/LICENSE

    def __init__(self, iterable: Iterable[T]):
        self._it = iter(iterable)
        self._cache: deque[T] = deque()

    def __iter__(self):
        return self

    def has_more(self) -> bool:
        try:
            self.peek()
        except StopIteration:
            return False
        return True

    def peek(self) -> T:
        if not self._cache:
            self._cache.append(next(self._it))
        return self._cache[0]

    def __next__(self) -> T:
        if self._cache:
            return self._cache.popleft()
        return next(self._it)


def _modify_tokens(tokens_iter: Iterable[tokenize.TokenInfo]) -> Generator[tokenize.TokenInfo, None, None]:
    """Replaces '=>' with '= _PEP671_MARKER' in the token stream to mark where 'defer' objects should go."""

    peekable_tokens_iter = Peekable(tokens_iter)
    for tok in peekable_tokens_iter:
        if (
            tok.exact_type == tokenize.EQUAL
            and peekable_tokens_iter.has_more()
            and (peek := peekable_tokens_iter.peek()).exact_type == tokenize.GREATER
        ):
            yield tok

            # Replace this next token with a marker.
            next(peekable_tokens_iter)
            start_col, start_row = peek.start
            new_start = (start_col, start_row + 1)
            new_end = (start_col, start_row + 15)
            yield tokenize.TokenInfo(tokenize.NAME, "_PEP671_MARKER", new_start, new_end, tok.line)

            # Fix the positions of the rest of the tokens on the same line.
            late_bound_row = new_tok_row = tok.start[0]

            while True:
                tok = next(peekable_tokens_iter)  # noqa: PLW2901
                new_tok_row = int(tok.start[0])
                if late_bound_row != new_tok_row:
                    yield tok
                    break

                new_start = (tok.start[0], tok.start[1] + 13)
                new_end = (tok.end[0], tok.end[1] + 13)
                yield tokenize.TokenInfo(tok.type, tok.string, new_start, new_end, tok.line)

        else:
            yield tok


def _modify_source(src: str) -> str:
    """Replaces late binding tokens with valid Python, along with markers for the ast transformer."""

    tokens_gen = _modify_tokens(tokenize.generate_tokens(StringIO(src).readline))
    return tokenize.untokenize(tokens_gen)


# === AST modification.


class LateBoundDefaultTransformer(ast.NodeTransformer):
    @staticmethod
    def _is_marker_node(potential_node: object) -> TypeGuard[ast.Call]:
        return (
            isinstance(potential_node, ast.Call)
            and isinstance(potential_node.func, ast.Name)
            and potential_node.func.id == "_PEP671_MARKER"
        )

    @staticmethod
    def _replace_marker_node(node: ast.Call, index: int, all_previous_args: list[ast.arg]) -> ast.Call:
        lambda_arg_names = [arg.arg for arg in all_previous_args[:index]]
        new_lambda = ast.Lambda(
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg=name) for name in lambda_arg_names],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=ast.Tuple(elts=node.args) if len(node.args) > 1 else node.args[0],
        )
        return ast.Call(func=ast.Name(id="_defer", ctx=ast.Load()), args=[new_lambda], keywords=[])

    def _replace_late_bound_markers(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        all_func_defaults = node.args.defaults + node.args.kw_defaults
        try:
            next(default for default in all_func_defaults if default is not None and self._is_marker_node(default))
        except StopIteration:
            return

        # Handle args that are allowed to be passed in positionally.
        positional_args = node.args.posonlyargs + node.args.args
        default_offset = len(positional_args) - len(node.args.defaults)

        markers_in_defaults = [
            (index, default) for index, default in enumerate(node.args.defaults) if self._is_marker_node(default)
        ]
        for index, marker in markers_in_defaults:
            actual_index = index + default_offset
            node.args.defaults[index] = self._replace_marker_node(marker, actual_index, positional_args)

        # Handle args that are keyword-only.
        all_args = positional_args + node.args.kwonlyargs
        kw_default_offset = len(positional_args)

        markers_in_kw_defaults = [
            (index, kw_default)
            for index, kw_default in enumerate(node.args.kw_defaults)
            if self._is_marker_node(kw_default)
        ]

        for index, marker in markers_in_kw_defaults:
            actual_index = index + kw_default_offset
            node.args.kw_defaults[index] = self._replace_marker_node(marker, actual_index, all_args)

    def _add_late_binding_evaluate_call(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        evaluate_expr = ast.Expr(
            value=ast.Call(
                func=ast.Name(id="_evaluate_late_binding", ctx=ast.Load()),
                args=[ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[])],
                keywords=[],
            )
        )

        match node.body:
            case [ast.Expr(value=ast.Constant(value=str())), *_]:
                node.body.insert(1, evaluate_expr)
            case _:
                node.body.insert(0, evaluate_expr)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        # Replace the markers in the function defaults with actual defer objects.
        self._replace_late_bound_markers(node)

        # Put a call to evaluate the defer objects, the late bindings, as the first line of the function.
        self._add_late_binding_evaluate_call(node)

        return self.generic_visit(node)  # type: ignore

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        # Replace the markers in the function defaults with actual defer objects.
        self._replace_late_bound_markers(node)

        # Put a call to evaluate the defer objects, the late bindings, as the first line of the function.
        self._add_late_binding_evaluate_call(node)

        return self.generic_visit(node)  # type: ignore

    def visit_Module(self, node: ast.Module) -> ast.Module:
        """Import the defer type and evaluation functions so that the late binding-related symbols are valid."""

        import_stmt = ast.ImportFrom(
            module="experimental_late_bound_defaults",
            names=[ast.alias(name="_defer"), ast.alias(name="_evaluate_late_binding")],
            level=0,
        )

        match node.body:
            case [ast.Expr(value=ast.Constant(value=str())), *_]:
                node.body.insert(1, import_stmt)
            case _:
                node.body.insert(0, import_stmt)

        return self.generic_visit(node)  # type: ignore


def _modify_ast(tree: ast.AST) -> ast.Module:
    return ast.fix_missing_locations(LateBoundDefaultTransformer().visit(tree))


# === Codec registration.


def decode(input: bytes, errors: str = "strict") -> tuple[str, int]:
    source, read = utf_8.decode(input, errors=errors)
    source = _modify_source(source)
    tree = _modify_ast(ast.parse(source))
    source = ast.unparse(tree)
    return source, read


def searcher(name: str) -> codecs.CodecInfo | None:
    if name == "experimental-late-bound-defaults":
        return codecs.CodecInfo(
            name=name,
            encode=utf_8.encode,
            decode=decode,
            incrementalencoder=utf_8.IncrementalEncoder,
            incrementaldecoder=utf_8.IncrementalDecoder,
            streamreader=utf_8.StreamReader,
            streamwriter=utf_8.StreamWriter,
        )
    return None


def register() -> None:
    codecs.register(searcher)


def unregister() -> None:
    codecs.unregister(searcher)
