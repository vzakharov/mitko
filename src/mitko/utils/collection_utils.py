def compact[T](*args: T | None) -> list[T]:
    """
    Remove all None values from the arguments.
    """
    return [item for item in args if item is not None]
