from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderReply:
    """What a provider hands back: why the model stopped, and each forced-tool input it produced."""

    stop_reason: str
    tool_inputs: list = field(default_factory=list)


class ExtractionError(Exception):
    """An attempt that must become an error record. `code` is a stable short name."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message
