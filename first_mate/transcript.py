"""Parse a team chat transcript.

Input shape: a Teamily group chat export, or any pasted transcript.
Each line is kept as-is. Lines that look like "Name: text" get a speaker.
Everything else is treated as a plain message.

The parser is simple and rule based on purpose, so it works offline
and its output is easy to explain in a demo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
SPEAKER_RE = re.compile(r"^([A-Za-z][A-Za-z .'-]{0,40}):\s+(.*)$")

# Input limits for one run. They are generous for a team chat and exist
# so a bad paste or a wrong file fails with a clear message instead of
# a long hang or a traceback.
MAX_INPUT_CHARS = 1_000_000
MAX_MESSAGES = 10_000


class InputError(ValueError):
    """Chat input that cannot be used. The message is safe to show to
    the user, it explains what is wrong and what to do instead."""

DECISION_MARKERS = (
    "decided",
    "decision:",
    "we will ",
    "we'll ",
    "agreed",
    "locked:",
    "final:",
    "going with",
)

ACTION_MARKERS = (
    "todo",
    "to do:",
    "action:",
    "needs to",
    "need to",
    "please ",
    "can you ",
    "will build",
    "will write",
    "will set up",
    "will check",
    "by friday",
    "by monday",
    "by tomorrow",
    "by nov",
)


@dataclass
class Message:
    speaker: str
    text: str


@dataclass
class Transcript:
    messages: list[Message] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    # Drop control characters (a pasted export can carry them), then
    # collapse whitespace as before.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_transcript(text: str) -> Transcript:
    if text is None or not text.strip():
        raise InputError(
            "The chat text is empty. Paste or pass a team chat with at "
            "least one message in it."
        )
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(
            f"The chat text is too large ({len(text)} characters). First Mate "
            f"accepts up to {MAX_INPUT_CHARS} characters per run. Split the "
            "chat into parts and run each part."
        )
    result = Transcript()
    seen_links: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("---"):
            continue
        match = SPEAKER_RE.match(line)
        if match:
            speaker, body = match.group(1).strip(), match.group(2).strip()
        else:
            speaker, body = "Team", line
        body = _clean(body)
        result.messages.append(Message(speaker=speaker, text=body))
        if len(result.messages) > MAX_MESSAGES:
            raise InputError(
                f"The chat has more than {MAX_MESSAGES} messages. First Mate "
                "accepts up to that many per run. Split the chat into parts "
                "and run each part."
            )

        for url in URL_RE.findall(body):
            url = url.rstrip(".,;")
            if url not in seen_links:
                seen_links.add(url)
                result.links.append(url)

        low = body.lower()
        entry = f"{speaker}: {body}"
        if any(marker in low for marker in DECISION_MARKERS):
            result.decisions.append(entry)
        elif any(marker in low for marker in ACTION_MARKERS) or body.startswith("@"):
            result.actions.append(entry)
        else:
            result.notes.append(entry)
    return result
