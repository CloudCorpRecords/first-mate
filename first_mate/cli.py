"""Command line entry point.

Usage:
  python -m first_mate run sample/sample-chat.txt --out out
  python -m first_mate run chat.txt
  python -m first_mate health
  python -m first_mate config
  python -m first_mate serve

Bad input (missing file, not text, empty chat, oversized chat) exits
with code 2 and a plain error message, never a traceback.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import Config, load_config
from .ship_log import build_ship_log, save_ship_log
from .transcript import InputError

# Exit code for input problems the user can fix.
EXIT_INPUT_ERROR = 2


def data_dir_writable(config: Config) -> bool:
    """Probe the data dir the same way a run would use it."""
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        probe = config.data_dir / ".health-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def health_payload() -> dict:
    config = load_config()
    writable = data_dir_writable(config)
    return {
        "status": "ok" if writable else "degraded",
        "app": "first-mate",
        "version": __version__,
        "privacy_mode": "Private via NYTE" if config.inference_configured else "Local only",
        "context_dev": "configured" if config.context_dev_configured else "free mode (direct fetch)",
        "hosting": "Boat VM" if config.on_boat_vm else "local",
        "data_dir": str(config.data_dir),
        "data_dir_writable": writable,
        "routes": config.mode_summary(),
    }


def config_payload() -> dict:
    """The full configuration check: modes, routes, warnings, storage."""
    config = load_config()
    payload = {"app": "first-mate", "version": __version__}
    payload.update(config.mode_summary())
    payload["data_dir_writable"] = data_dir_writable(config)
    return payload


def cmd_run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    try:
        text = input_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: no such file: {args.input}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except IsADirectoryError:
        print(
            f"Error: {args.input} is a folder, not a chat file. "
            "Pass the chat transcript file itself.",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR
    except UnicodeDecodeError:
        print(
            f"Error: {args.input} is not plain UTF-8 text. Export or save "
            "the chat as a .txt file and try again.",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR
    except OSError as exc:
        print(
            f"Error: could not read {args.input}: {exc.strerror or exc}",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR
    config = load_config()
    try:
        log = build_ship_log(
            text, config, source_label=f"Chat transcript file {args.input} (Teamily group chat)"
        )
    except InputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    out_dir = Path(args.out) if args.out else Path(".")
    paths = save_ship_log(log, out_dir, config)
    print(log.markdown)
    print(f"[first-mate] wrote {paths['markdown']}", file=sys.stderr)
    print(f"[first-mate] wrote {paths['html']}", file=sys.stderr)
    print(f"[first-mate] wrote {paths['metadata']}", file=sys.stderr)
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


def cmd_config(_args: argparse.Namespace) -> int:
    print(json.dumps(config_payload(), indent=2))
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

    config_parser = sub.add_parser(
        "config", help="Print the active modes, routes, and warnings as JSON"
    )
    config_parser.set_defaults(func=cmd_config)

    serve_parser = sub.add_parser("serve", help="Run the tiny web UI")
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
