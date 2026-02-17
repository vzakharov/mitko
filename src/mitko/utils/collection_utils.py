from typing import TypeVar

_T = TypeVar("_T")


def compact(*args: _T | None) -> list[_T]:
    """
    Remove all None values from the arguments.
    """
    return [item for item in args if item is not None]
