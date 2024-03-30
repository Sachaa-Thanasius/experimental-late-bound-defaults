from experimental_late_bound_defaults import _evaluate_late_binding, defer


def example_func(
    a: int,
    b: float = 1.0,
    /,
    ex: str = "hello",
    *,
    c: list[object] = defer(lambda a, b, ex: ["Preceding args", a, b, ex]),  # type: ignore # noqa: B008
    d: bool = False,
    e: int = defer(lambda a, b, ex, c, d: len(c)),  # type: ignore
) -> tuple[list[object], int]:
    _evaluate_late_binding(locals())
    return c, e


def test_func_with_late_bindings() -> None:
    c, e = example_func(10)
    assert c == ["Preceding args", 10, 1.0, "hello"]
    assert e == 4
