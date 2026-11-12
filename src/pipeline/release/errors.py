class ReleaseError(RuntimeError):
    """A safe-to-display validation failure."""


class EmptyUnreleasedError(ReleaseError):
    """The changelog has an Unreleased heading with no release notes."""
