import os
import re


def redact(text):
    """Remove API keys from text before it is stored or logged."""
    text = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "[redacted]", text)
    secret = os.environ.get("ANTHROPIC_API_KEY")
    return text.replace(secret, "[redacted]") if secret else text
