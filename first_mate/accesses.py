"""All accesses: a plain record of everything a run touched.

Transparency is the point. Every run collects an AccessLog as it goes:
what came in, every link it tried to read and how, how the thinking was
done, where it is hosted, and where the Ship Log went out. It also
records the accesses that were NOT made, and why, so a judge looking at
the page can verify every sponsor tool was considered and exactly how
each one was used.

This is a data structure collected during the run, not fixed text.
The Ship Log markdown, the Ship Log HTML page, and the web UI result
page all render the same list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


@dataclass
class AccessEntry:
    time: str
    name: str
    tool: str
    result: str  # "Done", "Failed", or "Not made"
    detail: str

    def to_line(self) -> str:
        return (
            f"[{self.time}] {self.name} - tool: {self.tool}, "
            f"result: {self.result}. {self.detail}"
        )


@dataclass
class AccessLog:
    entries: list[AccessEntry] = field(default_factory=list)

    def record(
        self,
        name: str,
        tool: str,
        result: str,
        detail: str,
        when: str | None = None,
    ) -> AccessEntry:
        entry = AccessEntry(
            time=when or _now_stamp(),
            name=name,
            tool=tool,
            result=result,
            detail=detail,
        )
        self.entries.append(entry)
        return entry

    @property
    def made(self) -> list[AccessEntry]:
        return [e for e in self.entries if e.result != "Not made"]

    @property
    def not_made(self) -> list[AccessEntry]:
        return [e for e in self.entries if e.result == "Not made"]

    def to_dicts(self) -> list[dict]:
        return [
            {
                "time": e.time,
                "name": e.name,
                "tool": e.tool,
                "result": e.result,
                "detail": e.detail,
            }
            for e in self.entries
        ]
