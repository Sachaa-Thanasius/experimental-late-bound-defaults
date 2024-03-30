from experimental_late_bound_defaults import _defer, _evaluate_late_binding


def example_func(
    a: int,
    b: float = 1.0,
    /,
    ex: str = "hello",
    *,
    c: list[object] = _defer(lambda a, b, ex: ["Preceding args", a, b, ex]),  # noqa: B008
    d: bool = False,
    e: int = _defer(lambda a, b, ex, c, d: len(c)),
) -> tuple[list[object], int]:
    _evaluate_late_binding(locals())
    return c, e


def test_func_with_late_bindings() -> None:
    c, e = example_func(10)
    assert c == ["Preceding args", 10, 1.0, "hello"]
    assert e == 4
