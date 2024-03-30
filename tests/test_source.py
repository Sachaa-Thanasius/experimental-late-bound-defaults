import ast

from experimental_late_bound_defaults import _modify_ast, _modify_source

PRE_MOD_FUNC = """\
def test_func(
    z: float,
    a: int = 1,
    b: list[int] => ([a] * a),
    /,
    c: dict[str, int] => ({str(a): b}),
    *,
    d: str => (str(a) + str(c)),
) -> str:
    result = [*b, a]
    return str(result)
"""

POST_RETOKENIZE_FUNC = """\
def test_func(
    z: float,
    a: int = 1,
    b: list[int] = _PEP671_MARKER([a] * a),
    /,
    c: dict[str, int] = _PEP671_MARKER({str(a): b}),
    *,
    d: str = _PEP671_MARKER(str(a) + str(c)),
) -> str:
    result = [*b, a]
    return str(result)
"""

POST_AST_TRANSFORM_FUNC = """\
from experimental_late_bound_defaults import _defer, _evaluate_late_binding

def test_func(
    z: float,
    a: int = 1,
    b: list[int] = _defer(lambda z, a: [a] * a),
    /,
    c: dict[str, int] = _defer(lambda z, a, b: {str(a): b}),
    *,
    d: str = _defer(lambda z, a, b, c: str(a) + str(c)),
) -> str:
    _evaluate_late_binding(locals())
    result = [*b, a]
    return str(result)
"""


def test_modify_source() -> None:
    retokenized_source = _modify_source(PRE_MOD_FUNC)
    assert retokenized_source == POST_RETOKENIZE_FUNC


def test_modify_ast() -> None:
    transformed_tree = _modify_ast(ast.parse(POST_RETOKENIZE_FUNC))

    transformed_dump = ast.dump(transformed_tree)
    expected_dump = ast.dump(ast.parse(POST_AST_TRANSFORM_FUNC))


    assert transformed_dump == expected_dump
