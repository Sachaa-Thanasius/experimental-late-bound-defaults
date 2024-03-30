# experimental-late-bound-defaults
A way to test [PEP 671](https://peps.python.org/pep-0671/) in python.

## Installation
```shell
python -m pip install https://github.com/Sachaa-Thanasius/experimental-late-bound-defaults
```

# Usage
All you need is the encoding declaration at the top of your file and you're good to go for using the late binding syntax.

```python
# coding: experimental-late-bound-defaults

def example_func(
    a: int,
    b: list[int] => ([a] * a)
    c: int => (len(b) + a),
) -> tuple[list[object], int]:
    # If late-bound arguments like b and c aren't passed in, they're computed based
    # on the expressions after the '=>', in order, before the function body executes.
    assert b == ([a] * a)
    assert c == (len(b) + a)
    return c

assert example_func(5) == 10
```

## Motivation
I was annoyed with Python defaults, and resulting searches and discussion let to me being made awre of the above proposal and [PEP 661](https://peps.python.org/pep-0671/).
I didn't want to fork CPython and change all the grammar to try this out, so I cheated with a custom codecs and tokens/AST transformation.

## Caveats
The late-bound expression must be surrounded by parentheses, unlike the syntax proposed in the PEP. This may be fixed in the future.

## Acknowledgements
Thank you to [@asottile](https://github.com/asottile) and his future packages (e.g. [future-fstrings](https://github.com/asottile-archive/future-fstrings)) for providing an outline for how to do modify code like this.
