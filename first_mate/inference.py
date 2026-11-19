"""Private inference adapter: NY Token Exchange / TrustedRouter.

Optional path, only when a key, a base URL, and a model are all set in .env:
  POST {NYTE_BASE_URL}/chat/completions in the common OpenAI compatible
  shape, with the key as a bearer token. The base URL and model are
  configurable on purpose. First Mate does not guess an endpoint and
  present it as fact. No key or credits are needed for the demo, this
  route is an optional upgrade only.

Default path, the normal free mode with no keys:
  A local, extractive summarizer that runs in this process only.
  No network call is made, so no team content leaves the machine.
  It is simple on purpose: it picks the messages that carry decisions
  and next steps, and shortens long notes.

Every result is labelled with the mode that was actually used:
  "Private via NYTE" for a live call, "Local only" for the fallback.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from .config import Config
from .transcript import Transcript


@dataclass
class Summary:
    bullets: list[str]
    mode: str  # "Private via NYTE" or "Local only"
    # How the NY Token Exchange route was actually used, for the
    # All accesses record: "used", "failed", or "not used".
    nyte_attempt: str = "not used"


def local_summary(transcript: Transcript, link_titles: list[str]) -> Summary:
    """Extractive, offline summary. No network, no external model."""
    bullets: list[str] = []
    for decision in transcript.decisions[:5]:
        bullets.append(f"Decided: {_shorten(_strip_speaker(decision))}")
    for action in transcript.actions[:5]:
        bullets.append(f"Next: {_shorten(_strip_speaker(action))}")
    if not bullets:
        for note in transcript.notes[:3]:
            bullets.append(_shorten(_strip_speaker(note)))
    for title in link_titles:
        if title:
            bullets.append(f"Shared link: {title}")
    if not bullets:
        bullets.append("Nothing clear yet. Share a link or a note and try again.")
    return Summary(bullets=bullets, mode="Local only")


def _strip_speaker(entry: str) -> str:
    if ": " in entry:
        return entry.split(": ", 1)[1]
    return entry


def _shorten(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def nyte_summary(
    transcript: Transcript, link_excerpts: list[str], config: Config
) -> Summary:
    """Live private call. Raises on any failure so the caller can fall back."""
    context_lines = []
    for msg in transcript.messages:
        context_lines.append(f"{msg.speaker}: {msg.text}")
    for excerpt in link_excerpts:
        if excerpt:
            context_lines.append(f"Link content: {excerpt[:600]}")
    prompt = (
        "You are First Mate, a helper in a team chat. From the chat below, "
        "write a short plain list: decisions first, then what to do next, "
        "one item per line, no intro text.\n\n" + "\n".join(context_lines)
    )
    payload = json.dumps(
        {
            "model": config.nyte_model,
            "messages": [
                {"role": "system", "content": "Keep team content private. Be brief and plain."},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    endpoint = config.nyte_base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.inference_api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    content = data["choices"][0]["message"]["content"]
    bullets = [
        re.sub(r"^[-*0-9. ]+", "", line).strip()
        for line in content.splitlines()
        if line.strip()
    ]
    if not bullets:
        raise ValueError("Empty response from inference route")
    return Summary(bullets=bullets[:10], mode="Private via NYTE", nyte_attempt="used")


def summarize(
    transcript: Transcript, link_titles: list[str], link_excerpts: list[str], config: Config
) -> Summary:
    if config.inference_configured:
        try:
            return nyte_summary(transcript, link_excerpts, config)
        except Exception:
            summary = local_summary(transcript, link_titles)
            summary.nyte_attempt = "failed"
            return summary
    return local_summary(transcript, link_titles)
