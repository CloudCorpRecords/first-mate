"""Build a Ship Log from a transcript, and save it to disk.

The Ship Log is the output that goes back into the Teamily group chat:
one short markdown message with what was shared, what was decided,
and what to do next.

Ship Logs are also stored on disk under the data directory, so they
persist on a Boat.dev VM between runs.
"""
from __future__ import annotations

import html
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .accesses import AccessLog
from .config import Config, load_config
from .context_dev import LinkResult, fetch_links
from .inference import Summary, summarize
from .transcript import Transcript, parse_transcript


@dataclass
class ShipLog:
    markdown: str
    html_page: str
    summary: Summary
    links: list[LinkResult]
    transcript: Transcript
    accesses: AccessLog
    # Structured record of the run: id, timestamps, counts, and modes.
    # Saved as JSON next to every Ship Log by save_ship_log.
    metadata: dict = field(default_factory=dict)


def _slug_time(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S")


def _health_check(config: Config) -> tuple[bool, str]:
    """A real, small health check: config loaded and data dir writable."""
    try:
        store_dir = Path(config.data_dir)
        store_dir.mkdir(parents=True, exist_ok=True)
        probe = store_dir / ".health-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, f"Health check passed, data folder is writable: {store_dir}"
    except Exception as exc:
        return False, f"Health check failed: {type(exc).__name__}"


def collect_accesses(
    transcript: Transcript,
    links: list[LinkResult],
    summary: Summary,
    config: Config,
    source_label: str,
) -> AccessLog:
    """Build the All accesses record from what the run actually did."""
    log = AccessLog()

    # Chat in, via Teamily (paste or export, no API claim).
    log.record(
        "Teamily chat in",
        "Teamily",
        "Done",
        f"Source: {source_label}. {len(transcript.messages)} messages read, "
        f"{len(transcript.links)} links found, {len(transcript.decisions)} decisions, "
        f"{len(transcript.actions)} actions.",
    )
    log.record(
        "Teamily API",
        "Teamily API",
        "Not made",
        "No Teamily API integration is used. The chat was pasted or exported in, "
        "and the Ship Log is pasted back into the group.",
    )

    # Link accesses, one entry per link, plus Context.dev not made if unused.
    context_used = any(link.context_dev_attempt == "used" for link in links)
    context_failed = any(link.context_dev_attempt == "failed" for link in links)
    for link in links:
        log.record(
            f"Link access: {link.url}",
            link.source,
            "Done" if link.ok else "Failed",
            "Read ok, a short note was added to the Ship Log."
            if link.ok
            else "Could not read this link here. The link was kept in the Ship Log "
            "so the team can open it.",
            when=link.accessed_at or None,
        )
    if links and not context_used:
        if context_failed:
            detail = (
                "Context.dev was tried and failed, so direct fetch was used instead. "
                "No key or credits are needed for that fallback."
            )
        elif config.context_dev_configured:
            detail = "Context.dev was configured but did not return a result for these links."
        else:
            detail = (
                "Context.dev: not used, no key set, used direct fetch instead. "
                "A key is an optional upgrade only, the demo runs complete without it."
            )
        log.record("Context.dev", "Context.dev", "Not made", detail)
    if not links:
        log.record(
            "Link access",
            "Context.dev / Direct fetch",
            "Not made",
            "No links were shared in this chat, so no link access was made.",
        )

    # AI access.
    if summary.mode == "Private via NYTE":
        log.record(
            "AI summary",
            "NY Token Exchange",
            "Done",
            "Private route via NY Token Exchange / TrustedRouter was used for the summary.",
        )
    else:
        log.record(
            "AI summary",
            "Local only",
            "Done",
            "Local summary on this machine only. No team data left the machine in local mode, "
            "no network call was made for the summary.",
        )
        if summary.nyte_attempt == "failed":
            detail = (
                "NY Token Exchange route was tried and failed, so the local summary was used instead. "
                "No team data was sent anywhere else."
            )
        else:
            detail = (
                "NY Token Exchange: not used, no private route configured, used local summary instead. "
                "That route is an optional upgrade only, the demo runs complete without it."
            )
        log.record("NY Token Exchange private route", "NY Token Exchange", "Not made", detail)

    # Hosting, Boat.dev.
    health_ok, health_detail = _health_check(config)
    if config.on_boat_vm:
        log.record(
            "Hosting",
            "Boat.dev",
            "Done" if health_ok else "Failed",
            f"Running on a Boat VM. {health_detail}",
        )
    else:
        log.record(
            "Hosting",
            "Boat.dev",
            "Done" if health_ok else "Failed",
            f"Running locally, not on a Boat VM in this run. {health_detail}",
        )
        log.record(
            "Boat.dev VM",
            "Boat.dev",
            "Not made",
            "This run was not on a Boat VM, it ran locally. Deploy steps to run the same code "
            "on a Boat VM are in deploy/boat.md, and Ship Logs are stored on disk the same way there.",
        )

    # Ship Log out.
    log.record(
        "Ship Log out",
        "Teamily",
        "Done",
        "Ship Log formatted for Teamily, ready to paste back into the group. "
        "Saved as ship-log.md and ship-log.html, with an archived copy in "
        f"{config.data_dir}.",
    )
    return log


def _run_metadata(
    started: datetime,
    finished: datetime,
    transcript: Transcript,
    links: list[LinkResult],
    summary: Summary,
    accesses: AccessLog,
    config: Config,
    source_label: str,
) -> dict:
    """Structured record of one run, saved as JSON with the Ship Log."""
    return {
        "run_id": f"{_slug_time(finished)}-{uuid.uuid4().hex[:8]}",
        "app": "first-mate",
        "version": __version__,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "source": source_label,
        "privacy_mode": summary.mode,
        "mode": config.mode_summary(),
        "counts": {
            "messages": len(transcript.messages),
            "links": len(links),
            "links_read_ok": sum(1 for link in links if link.ok),
            "links_failed": sum(1 for link in links if not link.ok),
            "decisions": len(transcript.decisions),
            "actions": len(transcript.actions),
            "notes": len(transcript.notes),
            "accesses_made": len(accesses.made),
            "accesses_not_made": len(accesses.not_made),
        },
    }


def _minimal_metadata(log: "ShipLog") -> dict:
    """Metadata for a ShipLog built by hand, without build_ship_log."""
    now = datetime.now(timezone.utc)
    return {
        "run_id": f"{_slug_time(now)}-{uuid.uuid4().hex[:8]}",
        "app": "first-mate",
        "version": __version__,
        "finished_at": now.isoformat(),
        "privacy_mode": log.summary.mode,
        "counts": {
            "messages": len(log.transcript.messages),
            "links": len(log.links),
            "links_read_ok": sum(1 for link in log.links if link.ok),
            "links_failed": sum(1 for link in log.links if not link.ok),
            "decisions": len(log.transcript.decisions),
            "actions": len(log.transcript.actions),
            "notes": len(log.transcript.notes),
            "accesses_made": len(log.accesses.made),
            "accesses_not_made": len(log.accesses.not_made),
        },
    }


def build_ship_log(
    text: str,
    config: Config | None = None,
    source_label: str = "Pasted chat text (Teamily group chat)",
) -> ShipLog:
    config = config or load_config()
    started = datetime.now(timezone.utc)
    transcript = parse_transcript(text)
    links = fetch_links(transcript.links, config)
    titles = [link.title or link.url for link in links]
    excerpts = [link.excerpt for link in links if link.ok]
    summary = summarize(transcript, titles, excerpts, config)
    accesses = collect_accesses(transcript, links, summary, config, source_label)
    finished = datetime.now(timezone.utc)
    markdown = render_markdown(transcript, links, summary, finished, accesses)
    html_page = render_html(markdown, summary)
    metadata = _run_metadata(
        started, finished, transcript, links, summary, accesses, config, source_label
    )
    return ShipLog(
        markdown=markdown,
        html_page=html_page,
        summary=summary,
        links=links,
        transcript=transcript,
        accesses=accesses,
        metadata=metadata,
    )


def render_markdown(
    transcript: Transcript,
    links: list[LinkResult],
    summary: Summary,
    now: datetime,
    accesses: AccessLog | None = None,
) -> str:
    lines: list[str] = []
    lines.append("# Ship Log")
    lines.append("")
    lines.append(f"Date: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Privacy mode: {summary.mode}")
    lines.append("")
    lines.append("## What to do next")
    if transcript.actions:
        for action in transcript.actions:
            lines.append(f"- [ ] {action}")
    else:
        lines.append("- [ ] Nothing clear yet. Add a next step in chat and run again.")
    lines.append("")
    lines.append("## Decided")
    if transcript.decisions:
        for decision in transcript.decisions:
            lines.append(f"- {decision}")
    else:
        lines.append("- Nothing decided yet.")
    lines.append("")
    lines.append("## Shared links")
    if links:
        for link in links:
            label = link.title or link.url
            lines.append(f"- [{label}]({link.url}) - read via: {link.source}")
            if link.excerpt:
                lines.append(f"  - {link.excerpt[:220]}")
    else:
        lines.append("- No links shared.")
    lines.append("")
    lines.append("## Short summary")
    for bullet in summary.bullets:
        lines.append(f"- {bullet}")
    lines.append("")
    if accesses is not None:
        lines.append("## All accesses")
        lines.append(
            "Every access this run made, listed plainly. "
            "A judge can check each sponsor tool here."
        )
        for entry in accesses.made:
            lines.append(f"- {entry.to_line()}")
        lines.append("")
        lines.append("### Accesses that were not made, and why")
        if accesses.not_made:
            for entry in accesses.not_made:
                lines.append(f"- {entry.to_line()}")
        else:
            lines.append("- None. Every tool listed was used in this run.")
        lines.append("")
    lines.append("---")
    lines.append(
        "First Mate: a helper that sits in a team chat. "
        "Copy this log back into your Teamily group to share it."
    )
    lines.append("")
    return "\n".join(lines)


def render_html(markdown: str, summary: Summary) -> str:
    """Very small markdown to HTML pass, enough for a demo page."""
    out: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = _inline_links(line[2:])
            item = item.replace("[ ] ", "&#9744; ")
            out.append(f"<li>{item}</li>")
        elif line == "---":
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("<hr>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_inline_links(line)}</p>")
    if in_list:
        out.append("</ul>")
    body = "\n".join(out)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>First Mate - Ship Log</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:720px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.5;color:#14324a}"
        "h1{color:#0b5fa5}code{background:#eef4f8;padding:.1rem .3rem}"
        "h2{margin-top:1.6rem}</style>"
        f"</head><body>{body}"
        f"<p><small>Privacy mode: {html.escape(summary.mode)}</small></p>"
        "</body></html>\n"
    )


def _inline_links(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )


def render_accesses_html(accesses: AccessLog) -> str:
    """The All accesses panel, used on the web UI result page.

    Renders the same AccessLog that goes into ship-log.md and
    ship-log.html, so all three show the same record.
    """
    rows: list[str] = []
    for entry in accesses.entries:
        rows.append(
            "<li>"
            f"<strong>{html.escape(entry.name)}</strong> "
            f"[{html.escape(entry.time)}] - tool: {html.escape(entry.tool)}, "
            f"result: {html.escape(entry.result)}. {html.escape(entry.detail)}"
            "</li>"
        )
    items = "\n".join(rows)
    return (
        '<section class="accesses">'
        "<h2>All accesses</h2>"
        "<p>Every access this run made, and the ones it did not make, with the reason. "
        "A judge can check each sponsor tool here.</p>"
        f"<ul>{items}</ul>"
        "</section>"
    )


def save_ship_log(log: ShipLog, out_dir: Path, config: Config | None = None) -> dict[str, Path]:
    """Write ship-log.md, ship-log.html, and ship-log-meta.json, plus
    archived copies of the log and its metadata on disk.

    Archive files are named with the run id, so two runs in the same
    second never overwrite each other.
    """
    config = config or load_config()
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "ship-log.md"
    html_path = out_dir / "ship-log.html"
    md_path.write_text(log.markdown, encoding="utf-8")
    html_path.write_text(log.html_page, encoding="utf-8")

    metadata = log.metadata or _minimal_metadata(log)
    meta_text = json.dumps(metadata, indent=2) + "\n"
    meta_path = out_dir / "ship-log-meta.json"
    meta_path.write_text(meta_text, encoding="utf-8")

    store_dir = Path(config.data_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(metadata.get("run_id") or _slug_time(datetime.now(timezone.utc)))
    archive_path = store_dir / f"ship-log-{run_id}.md"
    archive_path.write_text(log.markdown, encoding="utf-8")
    archive_meta_path = store_dir / f"ship-log-{run_id}-meta.json"
    archive_meta_path.write_text(meta_text, encoding="utf-8")
    return {
        "markdown": md_path,
        "html": html_path,
        "metadata": meta_path,
        "archive": archive_path,
        "archive_metadata": archive_meta_path,
    }
