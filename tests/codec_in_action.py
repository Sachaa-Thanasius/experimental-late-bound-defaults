# coding: experimental-late-bound-defaults

def example_func(
    a: int,
    b: float = 1.0,
    /,
    ex: str = "hello",
    *,
    c: list[object] => (["Preceding args", a, b, ex]),
    d: bool = False,
    e: int => (len(c)),
) -> tuple[list[object], int]:
    return c, e
