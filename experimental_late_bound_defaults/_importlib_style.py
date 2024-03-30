"""On second thought, maybe doing a pure importlib version isn't the best for per-file usage. Leaving this here in case
I come back to it.
"""

from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import sys
from typing import TYPE_CHECKING, ParamSpec, TypeAlias, TypeVar

from . import _modify_ast, _modify_source

if TYPE_CHECKING:
    import os
    import types
    from collections.abc import Callable

    from typing_extensions import Buffer as ReadableBuffer

    StrPath: TypeAlias = str | os.PathLike[str]

T = TypeVar("T")
P = ParamSpec("P")


def _call_with_frames_removed(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Calls a function while removing itself and that call from tracebacks, should any be generated."""

    return func(*args, **kwargs)


class LateBoundDefaultImporter(importlib.machinery.FileFinder, importlib.machinery.SourceFileLoader):
    def find_spec(self, fullname: str, target: types.ModuleType | None = None) -> importlib.machinery.ModuleSpec | None:
        spec = super().find_spec(fullname, target)
        if spec is None:
            return None
        loader = spec.loader
        if loader:
            loader.__class__ = type(self)
        return spec

    def source_to_code(  # type: ignore
        self,
        data: ReadableBuffer,
        path: ReadableBuffer | StrPath = "<string>",
        *,
        _optimize: int = -1,
    ) -> types.CodeType:
        source = importlib.util.decode_source(data)
        source = _modify_source(source)
        tree = _call_with_frames_removed(
            compile,
            source,
            path,
            "exec",
            dont_inherit=True,
            optimize=_optimize,
            flags=ast.PyCF_ONLY_AST,
        )
        tree = _modify_ast(tree)
        return _call_with_frames_removed(compile, tree, path, "exec", dont_inherit=True, optimize=_optimize, flags=0)


def install() -> None:
    # Attempts to recreate exactly how FileFinder.path_hook is registered. Probably not necessary.

    def _get_supported_file_loaders():  # noqa: ANN202 # Better inference by pyright without annotation.
        extensions = importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES
        source = LateBoundDefaultImporter, importlib.machinery.SOURCE_SUFFIXES
        bytecode = importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES
        return [extensions, source, bytecode]

    for i, hook in enumerate(sys.path_hooks):
        if "FileFinder.path_hook" in repr(hook):
            sys.path_hooks[i] = LateBoundDefaultImporter.path_hook(*_get_supported_file_loaders())
            break
