"""Command line entry point.

Usage:
  python -m first_mate run sample/sample-chat.txt --out out
  python -m first_mate run chat.txt
  python -m first_mate health
  python -m first_mate serve
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .ship_log import build_ship_log, save_ship_log


def health_payload() -> dict:
    config = load_config()
    return {
        "status": "ok",
        "app": "first-mate",
        "version": __version__,
        "privacy_mode": "Private via NYTE" if config.inference_configured else "Local only",
        "context_dev": "configured" if config.context_dev_configured else "free mode (direct fetch)",
        "hosting": "Boat VM" if config.on_boat_vm else "local",
        "data_dir": str(config.data_dir),
    }


def cmd_run(args: argparse.Namespace) -> int:
    text = Path(args.input).read_text(encoding="utf-8")
    config = load_config()
    log = build_ship_log(
        text, config, source_label=f"Chat transcript file {args.input} (Teamily group chat)"
    )
    out_dir = Path(args.out) if args.out else Path(".")
    paths = save_ship_log(log, out_dir, config)
    print(log.markdown)
    print(f"[first-mate] wrote {paths['markdown']}", file=sys.stderr)
    print(f"[first-mate] wrote {paths['html']}", file=sys.stderr)
    print(f"[first-mate] archived {paths['archive']}", file=sys.stderr)
    print(
        f"[first-mate] privacy mode: {log.summary.mode}; "
        f"links: {len(log.links)}; actions: {len(log.transcript.actions)}; "
        f"decisions: {len(log.transcript.decisions)}",
        file=sys.stderr,
    )
    return 0


def cmd_health(_args: argparse.Namespace) -> int:
    print(json.dumps(health_payload(), indent=2))
    return 0


def cmd_serve(_args: argparse.Namespace) -> int:
    from .server import serve

    serve()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="first-mate", description="First Mate - a helper in a team chat.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Build a Ship Log from a chat transcript file")
    run_parser.add_argument("input", help="Path to a chat transcript text file")
    run_parser.add_argument("--out", default=".", help="Folder for ship-log.md and ship-log.html")
    run_parser.set_defaults(func=cmd_run)

    health_parser = sub.add_parser("health", help="Print a health check as JSON")
    health_parser.set_defaults(func=cmd_health)

    serve_parser = sub.add_parser("serve", help="Run the tiny web UI")
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
