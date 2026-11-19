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
    return re.sub(r"\s+", " ", text).strip()


def parse_transcript(text: str) -> Transcript:
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
