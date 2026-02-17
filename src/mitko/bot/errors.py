class BotError(Exception):
    """Raised when a bot invariant is violated with a specific user-visible message."""

    def __init__(self, user_message: str) -> None:
        self.user_message = user_message
        super().__init__(user_message)
