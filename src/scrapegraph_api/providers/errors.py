"""Shared error types used to distinguish access blocks from catalog failures."""


class SourceBlockedError(RuntimeError):
    """A provider explicitly denied access or returned a challenge/rate limit."""
