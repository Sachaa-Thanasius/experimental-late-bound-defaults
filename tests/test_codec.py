import codecs

from experimental_late_bound_defaults import register

TEST_STR = """\
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
"""


def test_decode():
    register()

    with open("tests/codec_in_action.py", "rb") as fp:
        text = codecs.decode(fp.read(), "experimental-late-bound-defaults")

    code = compile(text, fp.name, mode="exec")

    globals_ = globals()
    exec(code, globals_)  # noqa: S102
    example_func = globals_["example_func"]
    c, e = example_func(10)

    assert c == ["Preceding args", 10, 1.0, "hello"]
    assert e == 4
