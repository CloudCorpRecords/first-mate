"""First Mate — Deck Edition server. Stdlib only.

Fullscreen-first UI for Steam Deck 1280x800. Reuses the untouched
First Mate engine (build_ship_log / save_ship_log / render_accesses_html).
No engine behaviour is faked: link reading, privacy mode and the
All Accesses record come straight from the engine. Connectivity is
checked for real on the server (/status) with a short timeout.

Routes:
  GET  /                Home: one-tap sample buttons + paste form
  GET  /sample/<slug>   Run a bundled sample chat, show Ship Log
  POST /ship-log        Run pasted chat, show Ship Log
  GET  /logs            List saved Ship Logs in data/ship-logs
  GET  /logs/<file>     View one saved Ship Log (.md only, basename)
  GET  /status          JSON: online/offline (real fetch), privacy, hosting
  GET  /health          JSON health (engine health_payload)
  GET  /phone           Phone app (installable PWA surface, same server/store)
  GET  /manifest.webmanifest  PWA manifest
  GET  /sw.js           Service worker (shell only; sync data never cached)
  GET  /icon-192.png, /icon-512.png  PWA icons (from logo.png)
  GET  /watch           Galaxy Watch companion: latest Ship Log, huge text
  GET  /api/latest      JSON summary of the latest Ship Log (+ done flags)
  GET  /api/bridge      JSON: latest Bridge signals (newest first)
  POST /api/bridge      JSON {from, to, text} -> leave a Bridge signal
  GET  /qr.png          QR code pairing image -> http://<deck-ip>:<port>/phone
  POST /api/ship-log    JSON {chat, source} -> build+save, JSON result
  POST /api/actions/done  JSON {index} or {run_id, index} -> toggle done
  GET  /llms.txt        Agent-readable contract, plain text
  GET  /agent.json      Same contract as a JSON manifest

v2 — "no typing on the Deck": the Deck shows a QR code, a phone scans
it and pastes the chat there, and the Ship Log lands back on the Deck
screen (home polls /api/latest). Phone = capture, Deck = big-screen
bridge + offline brain, Watch = glance + check-off. A daemon thread
also auto-imports any .txt dropped into inbox/ as a Ship Log.

v4 — "Deck Mode": controller-first. A gamepad/keyboard spatial-nav
script (GAMEPAD_JS) is injected on Deck pages; interactive elements
carry the .foci class and focus is a thick gold ring visible across
the room. The Deck home has NO paste form (typing lives on the
phone), result pages render structured sections instead of raw
markdown, HTML is served Cache-Control: no-store, user-facing errors
are friendly HTML pages, and the service worker (first-mate-v4)
caches only the manifest + icons — navigations are network-only, so
a relaunch always shows the current build.

Sync model: this one server + data/ship-logs is the single source of
truth. Deck, phone and watch are surfaces of the SAME store — a run
made on any surface appears on all of them.
"""
from __future__ import annotations

import html
import json
import shutil
import socket
import struct
import threading
import time
import urllib.request
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import __version__, qrmini
from .cli import health_payload
from .config import load_config
from .ship_log import build_ship_log, render_accesses_html, save_ship_log
from .transcript import InputError

MAX_REQUEST_BYTES = 2_000_000
ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "sample"

SAMPLES = [
    ("sample-chat", "sample-chat.txt", "⚓ Demo Chat", "Hackathon crew — the original demo"),
    ("startup-product-team", "startup-product-team-chat.txt", "🚀 Startup Product Team", "Standup, decisions & launch tasks"),
    ("event-crew", "event-crew-chat.txt", "🎪 Event Crew", "Run sheet for doors-open day"),
    ("open-source-team", "open-source-team-chat.txt", "🌊 Open Source Team", "Maintainers — release triage"),
    ("agent-fleet", "agent-fleet-chat.txt", "🤖 Agent Fleet Report", "Many agents, one operator — the daily digest"),
]
SAMPLE_MAP = {slug: (fname, label) for slug, fname, label, _ in SAMPLES}

# --- connectivity: real check, cached 10s ---
_cache = {"at": 0.0, "online": False, "detail": "not checked yet"}

def check_online(timeout: float = 2.0) -> dict:
    now = time.time()
    if now - _cache["at"] < 10:
        return {"online": _cache["online"], "detail": _cache["detail"]}
    online, detail = False, ""
    for url in ("https://example.com/", "https://boat.dev/"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FirstMate-Deck/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                _ = resp.read(256)
            online, detail = True, f"Reached {url} (HTTP {resp.status})"
            break
        except Exception as exc:  # noqa: BLE001 - honest offline label
            detail = f"Could not reach {url}: {type(exc).__name__}"
    _cache.update(at=now, online=online, detail=detail)
    return {"online": online, "detail": detail}

def status_payload() -> dict:
    cfg = load_config()
    conn = check_online()
    return {
        "online": conn["online"],
        "mode": "ONLINE" if conn["online"] else "OFFLINE",
        "detail": conn["detail"],
        "privacy_mode": "Private via NYTE" if cfg.inference_configured else "Local only",
        "hosting": "Steam Deck (on-device)",
        "link_reading": "Context.dev" if cfg.context_dev_configured else "Direct fetch (when online); Not fetched when offline",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "port": cfg.port,
    }

# --- v2: QR pairing (no typing on the Deck) ---

def lan_ip() -> str:
    """This Deck's LAN IP, via the UDP-connect trick (no traffic sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:  # noqa: BLE001 - offline Deck: QR points at localhost
        return "127.0.0.1"
    finally:
        sock.close()

def phone_url() -> str:
    cfg = load_config()
    return f"http://{lan_ip()}:{cfg.port}/phone"

def _png_grayscale(rows: list[bytes], width: int) -> bytes:
    """Minimal stdlib PNG writer (8-bit grayscale, no interlace)."""
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, len(rows), 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

def qr_png_bytes(text: str, scale: int = 10, border: int = 4) -> bytes:
    """QR code PNG for `text`, from the vendored qrmini (Nayuki) module."""
    qr = qrmini.QrCode.encode_text(text, qrmini.QrCode.Ecc.MEDIUM)
    size = qr.get_size()
    n = size + border * 2
    rows: list[bytes] = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            mx, my = x - border, y - border
            dark = 0 <= mx < size and 0 <= my < size and qr.get_module(mx, my)
            row.extend(b"\x00" * scale if dark else b"\xff" * scale)
        rows.extend([bytes(row)] * scale)
    return _png_grayscale(rows, n * scale)

# --- v2: action check-off state (sidecar JSON next to each Ship Log) ---

_done_lock = threading.Lock()

def _done_path(md_file: Path) -> Path:
    return md_file.with_name(md_file.name[:-len(".md")] + "-done.json")

def load_done(md_file: Path, n_actions: int) -> list[bool]:
    try:
        data = json.loads(_done_path(md_file).read_text(encoding="utf-8"))
        done = [bool(x) for x in data.get("done", [])]
    except Exception:  # noqa: BLE001 - no sidecar yet = nothing done
        done = []
    return (done + [False] * n_actions)[:n_actions]

def save_done(md_file: Path, done: list[bool]) -> None:
    _done_path(md_file).write_text(json.dumps({"done": done}) + "\n", encoding="utf-8")

# --- The Bridge: signal channel between Muse, the fleet and the surfaces ---
# Append-only JSONL in the SAME data_dir as the Ship Log store: this file
# is the shared space. Any agent (or Muse) can leave a signal; every
# surface can read them. The Ship Log is the digest; the Bridge is the wire.

_bridge_lock = threading.Lock()

def bridge_path() -> Path:
    # data/bridge.jsonl — beside the ship-logs store (data_dir is
    # data/ship-logs itself), resolved from the same config as the logs.
    cfg = load_config()
    return Path(cfg.data_dir).parent / "bridge.jsonl"

def bridge_append(frm: str, to: str, text: str) -> int:
    """Append one signal; returns the total signal count."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "from": frm[:60],
        "to": (to or "all")[:60],
        "text": text[:500],
    }
    p = bridge_path()
    with _bridge_lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        try:
            with p.open(encoding="utf-8") as fh:
                return sum(1 for line in fh if line.strip())
        except OSError:
            return 0

def bridge_latest(limit: int = 20) -> list[dict]:
    """Latest signals, newest first. Corrupt lines are skipped, never fatal."""
    try:
        lines = bridge_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:  # noqa: BLE001 - one bad line must not break the wire
            continue
        if isinstance(e, dict):
            out.append({"ts": str(e.get("ts", "")), "from": str(e.get("from", "")),
                        "to": str(e.get("to", "all")), "text": str(e.get("text", ""))})
        if len(out) >= limit:
            break
    return out

def bridge_rows_html(signals: list[dict]) -> str:
    if not signals:
        return '<p class="muted" style="margin:.2em 0">No signals yet — the desk is clear. Muse or any agent can leave one at POST /api/bridge.</p>'
    rows = ""
    for s in signals:
        when = html.escape(s["ts"][:16].replace("T", " "))
        rows += (f'<div class="sigrow"><p class="sigmeta">{html.escape(s["from"])} → {html.escape(s["to"])} · {when} UTC</p>'
                 f'<p class="sigtext">{html.escape(s["text"])}</p></div>')
    return rows

def find_log_by_run_id(run_id: str) -> Path | None:
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_")
    if not safe or safe != run_id:
        return None
    cfg = load_config()
    target = Path(cfg.data_dir) / f"ship-log-{safe}.md"
    return target if target.is_file() else None

# --- v2: inbox auto-import (drop a .txt, get a Ship Log) ---

INBOX_DIR = ROOT / "inbox"
INBOX_PROCESSED = INBOX_DIR / "processed"

def _inbox_sweep() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_PROCESSED.mkdir(parents=True, exist_ok=True)
    for f in sorted(INBOX_DIR.glob("*.txt")):
        if f.name.lower() == "readme.txt" or not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                cfg = load_config()
                log = build_ship_log(text, cfg, source_label=f"Inbox drop: {f.name}")
                with _done_lock:
                    save_ship_log(log, Path("."), cfg)
                print(f"[inbox] imported {f.name} -> run {log.metadata.get('run_id', '?')}")
            else:
                print(f"[inbox] skipped empty file {f.name}")
        except Exception as exc:  # noqa: BLE001 - one bad drop must not kill the watcher
            print(f"[inbox] failed on {f.name}: {type(exc).__name__}: {exc}")
        finally:
            dest = INBOX_PROCESSED / f.name
            n = 1
            while dest.exists():
                dest = INBOX_PROCESSED / f"{f.stem}-{n}{f.suffix}"
                n += 1
            try:
                shutil.move(str(f), str(dest))
            except Exception as exc:  # noqa: BLE001
                print(f"[inbox] could not move {f.name}: {exc}")

def _inbox_watcher() -> None:
    while True:
        try:
            _inbox_sweep()
        except Exception as exc:  # noqa: BLE001 - watcher must survive anything
            print(f"[inbox] sweep error: {exc}")
        time.sleep(3)

CSS = """
:root{
  color-scheme:dark;
  --ink:#060d18; --ink2:#0a1626; --paper:#f4f1ea; --paper-dim:rgba(244,241,234,.62);
  --gold:#d9a441; --gold-dim:rgba(217,164,65,.55); --teal:#5ea8a0;
  --line:rgba(244,241,234,.10); --glass:rgba(255,255,255,.032);
  --serif:Georgia,"Iowan Old Style","Palatino Linotype","Times New Roman",serif;
  --sans:"Avenir Next","Segoe UI",system-ui,-apple-system,sans-serif;
}
*{box-sizing:border-box} html,body{margin:0;padding:0}
body{background:linear-gradient(165deg,#060d18 0%,#0a1626 58%,#081120 100%);background-attachment:fixed;
  color:var(--paper);font-family:var(--sans);font-size:20px;line-height:1.55;min-height:100vh}
body::before{content:"";position:fixed;inset:-12%;z-index:-1;pointer-events:none;
  background:radial-gradient(560px 380px at 18% 8%,rgba(217,164,65,.055),transparent 70%),
             radial-gradient(720px 480px at 86% 92%,rgba(94,168,160,.05),transparent 70%);
  animation:fmDrift 30s ease-in-out infinite alternate}
@keyframes fmDrift{from{transform:translate3d(-1.5%,-1%,0)}to{transform:translate3d(1.5%,1.2%,0)}}
::selection{background:rgba(217,164,65,.85);color:#060d18}
::-webkit-scrollbar{width:10px} ::-webkit-scrollbar-thumb{background:rgba(244,241,234,.16);border-radius:6px}
::-webkit-scrollbar-track{background:transparent}
a{color:#8fd0c7} :focus{outline:3px solid rgba(217,164,65,.9);outline-offset:3px;border-radius:10px}
.kicker{font-size:15px;font-weight:600;letter-spacing:.32em;text-transform:uppercase;color:var(--gold);margin:0 0 10px}
header.status{position:sticky;top:0;z-index:10;background:rgba(6,13,24,.86);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--line);padding:13px 24px;display:flex;flex-wrap:wrap;gap:8px 26px;align-items:center;font-size:17.5px;color:var(--paper-dim)}
header.status b{color:var(--paper);font-weight:600}
header.status .brand{font-family:var(--serif);font-size:21px;color:var(--paper);letter-spacing:.01em}
header.status .brand em{font-style:normal;color:var(--gold)}
header.status a{color:var(--paper-dim);text-decoration:none;border-bottom:1px solid transparent}
header.status a:hover{color:var(--gold);border-bottom-color:var(--gold-dim)}
.pill{display:inline-block;padding:5px 14px;border-radius:999px;font-weight:700;font-size:13.5px;letter-spacing:.14em}
.pill.on{background:rgba(94,168,160,.13);color:#8fd0c7;border:1px solid rgba(94,168,160,.45)}
.pill.off{background:rgba(224,138,122,.10);color:#e8a08e;border:1px solid rgba(224,138,122,.4)}
main{max-width:1180px;margin:0 auto;padding:26px 24px 56px}
main>*{animation:fmRise .8s cubic-bezier(.16,.7,.24,1) both}
main>*:nth-child(2){animation-delay:.07s} main>*:nth-child(3){animation-delay:.14s}
main>*:nth-child(4){animation-delay:.21s} main>*:nth-child(5){animation-delay:.28s}
main>*:nth-child(6){animation-delay:.35s} main>*:nth-child(n+7){animation-delay:.42s}
@keyframes fmRise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
h1{font-family:var(--serif);font-weight:400;font-size:46px;line-height:1.12;margin:.15em 0 .3em;color:var(--paper);letter-spacing:.005em}
h2{font-family:var(--serif);font-weight:400;font-size:31px;color:var(--paper);margin:.4em 0 .5em}
h2.sect{margin-top:0}
.muted{color:var(--paper-dim)}
/* hero */
.hero{position:relative;padding:30px 4px 6px;overflow:hidden;border-radius:8px}
.hero .wheel{position:absolute;right:-84px;top:-58px;width:360px;height:360px;opacity:.05;pointer-events:none;animation:fmSpin 110s linear infinite reverse}
.hero-row{display:flex;align-items:center;gap:28px;flex-wrap:wrap;position:relative}
.hero .logo{width:98px;height:98px;border-radius:50%;box-shadow:0 10px 34px rgba(0,0,0,.5),0 0 0 1px var(--line);animation:fmSpin 80s linear infinite}
@keyframes fmSpin{to{transform:rotate(360deg)}}
.hero h1{font-size:64px;margin:0}
.hero .tagline{font-family:var(--serif);font-style:italic;font-size:25px;color:var(--paper-dim);margin:2px 0 0}
/* grids + cards */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0 8px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
a.bigbtn,button.bigbtn{position:relative;display:flex;flex-direction:column;gap:7px;justify-content:center;min-height:112px;
  padding:22px 24px;background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.014));
  border:1px solid var(--line);border-radius:18px;color:var(--paper);text-decoration:none;
  font-family:var(--serif);font-size:26px;font-weight:400;cursor:pointer;text-align:left;width:100%;
  transition:transform .28s cubic-bezier(.16,.7,.24,1),box-shadow .28s,border-color .28s}
a.bigbtn small,button.bigbtn small{font-family:var(--sans);font-size:17.5px;font-weight:400;color:var(--paper-dim);line-height:1.45}
a.bigbtn::after{content:"\\2192";position:absolute;right:22px;top:50%;transform:translateY(-50%) translateX(-6px);
  font-family:var(--sans);color:var(--gold);font-size:26px;opacity:0;transition:opacity .28s,transform .28s}
a.bigbtn:hover,button.bigbtn:hover{transform:translateY(-3px);border-color:var(--gold-dim);box-shadow:0 16px 36px rgba(0,0,0,.45)}
a.bigbtn:hover::after{opacity:1;transform:translateY(-50%) translateX(0)}
a.bigbtn:active,button.bigbtn:active{transform:translateY(-1px) scale(.995)}
button.bigbtn{font-family:var(--sans);font-weight:600;letter-spacing:.02em}
/* pairing — clean white card (QR must stay on light ground to scan) */
.pair{background:#faf8f2;color:#16233a;border-radius:20px;padding:28px 30px;margin:26px 0;
  display:flex;gap:32px;flex-wrap:wrap;align-items:center;box-shadow:0 24px 54px rgba(0,0,0,.42)}
.pair img{width:272px;height:272px;background:#fff;border-radius:10px;box-shadow:0 0 0 1px rgba(10,22,38,.08)}
.pair .kicker{color:#a4761a}
.pair h2{color:#0a1626;margin:0 0 8px}
.pair p{color:#3c4f6a;margin:.45em 0}
.pair .lead{font-size:23.5px;color:#16233a}
.pair .url{font-size:27px;font-weight:700;color:#0a1626;word-break:break-all;border-bottom:2px solid var(--gold);display:inline-block;padding-bottom:2px}
/* live panel — glass card */
.livebox{background:var(--glass);border:1px solid var(--line);border-radius:20px;padding:24px 28px;margin:16px 0 26px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 18px 40px rgba(0,0,0,.28)}
.livebox.flash{animation:fmArrive 2.4s cubic-bezier(.16,.7,.24,1)}
@keyframes fmArrive{0%{border-color:var(--gold-dim);box-shadow:0 0 0 0 rgba(217,164,65,.0),inset 0 0 60px rgba(217,164,65,.10)}
  35%{box-shadow:0 0 0 3px rgba(217,164,65,.22),inset 0 0 60px rgba(217,164,65,.06)}
  100%{border-color:var(--line);box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 18px 40px rgba(0,0,0,.28)}}
.livebox p{color:var(--paper-dim);margin:.3em 0 .6em}
.livebox ul{list-style:none;padding:0;margin:.3em 0}
.livebox li{font-size:22.5px;padding:11px 10px;margin:2px 0;border-bottom:1px solid rgba(244,241,234,.06);
  border-radius:8px;cursor:pointer;transition:background .25s,padding-left .25s;animation:fmItemIn .55s cubic-bezier(.16,.7,.24,1) both}
.livebox li:nth-child(2){animation-delay:.05s}.livebox li:nth-child(3){animation-delay:.1s}
.livebox li:nth-child(4){animation-delay:.15s}.livebox li:nth-child(5){animation-delay:.2s}
.livebox li:nth-child(n+6){animation-delay:.25s}
@keyframes fmItemIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.livebox li:hover{background:rgba(255,255,255,.045);padding-left:16px}
.livebox li:last-child{border-bottom:0}
.doneact{color:rgba(244,241,234,.42);background-image:linear-gradient(rgba(217,164,65,.8),rgba(217,164,65,.8));
  background-repeat:no-repeat;background-position:0 56%;background-size:100% 2px;animation:fmItemIn .55s both,fmStrike .5s .1s ease-out both}
@keyframes fmStrike{from{background-size:0% 2px}to{background-size:100% 2px}}
.livebox li.doneact{animation:fmItemIn .55s both,fmStrike .5s .1s ease-out both}
/* forms + code */
textarea{width:100%;background:rgba(255,255,255,.03);color:var(--paper);border:1px solid var(--line);border-radius:14px;
  padding:16px 18px;font-size:20px;font-family:var(--sans);min-height:150px;transition:border-color .25s}
textarea:focus{border-color:var(--gold-dim);outline:none;box-shadow:0 0 0 3px rgba(217,164,65,.18)}
pre{background:rgba(255,255,255,.028);border:1px solid var(--line);border-radius:16px;padding:22px 24px;
  white-space:pre-wrap;word-wrap:break-word;font-size:18.5px;line-height:1.6;color:rgba(244,241,234,.93)}
.accesses{background:var(--glass);border:1px solid var(--line);border-radius:16px;padding:20px 26px;margin:22px 0;font-size:18.5px;line-height:1.6}
.accesses h2{margin-top:.1em}
/* nav pills */
.nav{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}
.nav a{display:inline-block;padding:12px 24px;background:transparent;color:var(--paper);font-weight:600;
  border:1px solid rgba(217,164,65,.45);border-radius:999px;text-decoration:none;font-size:19.5px;
  transition:background .25s,color .25s,transform .25s,border-color .25s}
.nav a:hover{background:var(--gold);color:#0a1626;transform:translateY(-2px);border-color:var(--gold)}
/* bridge signals — display only, never gamepad targets */
.sigrow{padding:12px 4px;border-bottom:1px solid rgba(244,241,234,.06)}
.sigrow:last-child{border-bottom:0}
.sigrow .sigmeta{font-size:13.5px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin:0 0 3px}
.sigrow .sigtext{font-size:20px;color:var(--paper);margin:0}
/* saved logs */
.logrow{display:block;background:var(--glass);border:1px solid var(--line);border-radius:14px;padding:17px 22px;margin:11px 0;
  color:var(--paper);text-decoration:none;font-size:20.5px;transition:border-color .25s,transform .25s,background .25s}
.logrow small{color:var(--paper-dim);font-size:16.5px}
.logrow:hover{border-color:var(--gold-dim);transform:translateX(5px);background:rgba(255,255,255,.05)}
.foot{margin-top:38px;padding-top:18px;border-top:1px solid var(--line);color:var(--paper-dim);font-size:17px}
/* under the hood — quiet, provable facts */
.hood{background:rgba(255,255,255,.018);border:1px solid var(--line);border-radius:20px;padding:24px 28px;margin:16px 0 26px}
.hood .fact{display:flex;gap:20px;flex-wrap:wrap;padding:14px 0;border-bottom:1px solid rgba(244,241,234,.06);font-size:19.5px}
.hood .fact:last-child{border-bottom:0}
.hood .fact b{font-family:var(--serif);font-weight:400;color:var(--gold);min-width:205px;flex-shrink:0}
.hood .fact span{color:var(--paper-dim);flex:1;min-width:260px}
.curlbox{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:15px;line-height:1.55;
  background:rgba(0,0,0,.32);border:1px solid var(--line);border-radius:12px;padding:13px 16px;margin:10px 0 2px;
  white-space:pre-wrap;word-break:break-all;color:rgba(244,241,234,.85)}
.runline{color:var(--paper-dim);font-size:16.5px;letter-spacing:.05em;margin:16px 0 0}
/* deck mode v4 — controller focus + structured results */
.foci{outline:none}
.foci.fmf,.foci:focus{outline:4px solid var(--gold) !important;outline-offset:3px;
  transform:scale(1.03);box-shadow:0 0 0 7px rgba(217,164,65,.22),0 20px 46px rgba(0,0,0,.55);position:relative;z-index:3}
body.gamepad,body.gamepad a,body.gamepad li{cursor:none}
.padbar{margin:2px 0 0;padding:10px 18px;border:1px solid rgba(217,164,65,.4);border-radius:999px;
  color:var(--paper);font-size:17px;display:inline-block;background:rgba(217,164,65,.07)}
.padbar b{color:var(--gold)}
.actlist{list-style:none;padding:0;margin:.3em 0}
.actlist li{font-size:23px;padding:15px 16px;margin:6px 0;background:var(--glass);border:1px solid var(--line);
  border-radius:14px;cursor:pointer;transition:background .25s}
.actlist li:hover{background:rgba(255,255,255,.05)}
.plainlist{list-style:none;padding:0;margin:.3em 0}
.plainlist li{font-size:21px;padding:10px 6px;border-bottom:1px solid rgba(244,241,234,.06);color:var(--paper)}
.plainlist li:last-child{border-bottom:0}
details.accesseswrap{margin:22px 0}
details.accesseswrap>summary{cursor:pointer;font-family:var(--serif);font-size:24px;color:var(--gold);
  padding:14px 18px;border:1px solid var(--line);border-radius:14px;background:var(--glass);list-style:none}
details.accesseswrap>summary::-webkit-details-marker{display:none}
.errbox{background:var(--glass);border:1px solid rgba(217,164,65,.45);border-radius:20px;padding:30px 32px;margin:26px 0;font-size:21px}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation-duration:.001s !important;animation-iteration-count:1 !important;transition-duration:.001s !important}
}
"""

# JS shared by Deck home / phone / watch: tap an action to toggle its
# done state on the server (POST /api/actions/done), then re-render.
TOGGLE_JS = """
function fmToggleDone(index, runId){
  var body = {index: index}; if(runId){ body.run_id = runId; }
  fetch("/api/actions/done", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})
    .then(function(){ if(window.fmRefresh){ window.fmRefresh(); } else { location.reload(); } })
    .catch(function(){});
}
"""

# Deck Mode v4: controller-first navigation, injected on Deck pages.
# D-pad / left stick / arrow keys move a visible gold focus ring between
# .foci elements (spatial nearest-neighbour scoring); A / Enter / Space
# activates; B / Escape goes back; the menu button goes home.
GAMEPAD_JS = """
(function(){
  function els(){ return Array.prototype.slice.call(document.querySelectorAll('.foci')); }
  var cur = null;
  function setFocus(el){
    if(cur){ cur.classList.remove('fmf'); }
    cur = el || null;
    if(!cur){ return; }
    cur.classList.add('fmf');
    try{ cur.focus({preventScroll: true}); }catch(e){ try{ cur.focus(); }catch(e2){} }
    try{ cur.scrollIntoView({block: 'nearest', inline: 'nearest'}); }catch(e){}
  }
  function center(el){ var r = el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }
  function move(dir){
    var list = els();
    if(!list.length){ return; }
    if(!cur || !document.contains(cur) || list.indexOf(cur) < 0){ setFocus(list[0]); return; }
    var c = center(cur), best = null, bestScore = Infinity;
    list.forEach(function(el){
      if(el === cur){ return; }
      var t = center(el), dx = t.x - c.x, dy = t.y - c.y, ok = false, primary = 0, cross = 0;
      if(dir === 'left' && dx < -4){ ok = true; primary = -dx; cross = Math.abs(dy); }
      if(dir === 'right' && dx > 4){ ok = true; primary = dx; cross = Math.abs(dy); }
      if(dir === 'up' && dy < -4){ ok = true; primary = -dy; cross = Math.abs(dx); }
      if(dir === 'down' && dy > 4){ ok = true; primary = dy; cross = Math.abs(dx); }
      if(!ok){ return; }
      var score = primary + 2.5 * cross;
      if(score < bestScore){ bestScore = score; best = el; }
    });
    if(best){ setFocus(best); }
  }
  function activate(){ if(cur && document.contains(cur)){ cur.click(); } }
  function back(){
    if(window.history.length > 1){ history.back(); }
    else if(location.pathname !== '/'){ location.href = '/'; }
  }
  document.addEventListener('keydown', function(e){
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if(tag === 'TEXTAREA' || tag === 'INPUT'){ return; }
    if(e.key === 'ArrowLeft'){ move('left'); e.preventDefault(); }
    else if(e.key === 'ArrowRight'){ move('right'); e.preventDefault(); }
    else if(e.key === 'ArrowUp'){ move('up'); e.preventDefault(); }
    else if(e.key === 'ArrowDown'){ move('down'); e.preventDefault(); }
    else if(e.key === ' '){ e.preventDefault(); activate(); }
    else if(e.key === 'Enter'){ if(!cur || (cur.tagName !== 'A' && cur.tagName !== 'BUTTON')){ activate(); e.preventDefault(); } }
    else if(e.key === 'Escape'){ back(); }
  });
  document.addEventListener('click', function(e){
    var t = e.target && e.target.closest ? e.target.closest('.foci') : null;
    if(t && t !== cur){ setFocus(t); }
  });
  var prev = [], stickLockUntil = 0;
  function poll(){
    var gps = (navigator.getGamepads ? navigator.getGamepads() : []) || [], gp = null, i;
    for(i = 0; i < gps.length; i++){ if(gps[i]){ gp = gps[i]; break; } }
    if(!gp){ return; }
    document.body.classList.add('gamepad');
    var b = [];
    for(i = 0; i < gp.buttons.length; i++){ b.push(!!gp.buttons[i].pressed); }
    function pressed(idx){ return b[idx] && !prev[idx]; }
    if(pressed(14)){ move('left'); }
    else if(pressed(15)){ move('right'); }
    else if(pressed(12)){ move('up'); }
    else if(pressed(13)){ move('down'); }
    if(pressed(0)){ activate(); }
    if(pressed(1)){ back(); }
    if(pressed(9) && location.pathname !== '/'){ location.href = '/'; }
    prev = b;
    var now = Date.now();
    if(now >= stickLockUntil && gp.axes && gp.axes.length >= 2){
      var ax = gp.axes[0] || 0, ay = gp.axes[1] || 0;
      if(Math.abs(ax) > 0.5 || Math.abs(ay) > 0.5){
        if(Math.abs(ax) >= Math.abs(ay)){ move(ax > 0 ? 'right' : 'left'); }
        else{ move(ay > 0 ? 'down' : 'up'); }
        stickLockUntil = now + 220;
      }
    }
  }
  setInterval(poll, 100);
  function init(){
    els().forEach(function(el){
      if(el.tabIndex < 0 && el.tagName !== 'A' && el.tagName !== 'BUTTON' && el.tagName !== 'SUMMARY'){ el.tabIndex = 0; }
    });
    var list = els();
    if(list.length){ setFocus(list[0]); }
  }
  if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', init); }
  else{ init(); }
})();
"""

def header_html() -> str:
    s = status_payload()
    pill = '<span class="pill on">● ONLINE</span>' if s["online"] else '<span class="pill off">● OFFLINE</span>'
    return (
        '<header class="status"><span class="brand">First Mate <em>· Deck Edition</em></span>'
        f'<span id="fm-mode">{pill}</span>'
        f'<span>Privacy <b>{html.escape(s["privacy_mode"])}</b></span>'
        '<span>Hosting <b>Steam Deck — on-device</b></span>'
        '<span><a class="foci" href="/logs">Saved Logs</a> &nbsp;·&nbsp; <a class="foci" href="/">Home</a></span></header>'
        '<div style="padding:10px 24px 0"><span class="padbar"><b>D-pad</b> to move · <b>A</b> to select · <b>B</b> to go back — your phone is the keyboard</span></div>'
        '<script>fetch("/status").then(r=>r.json()).then(s=>{var e=document.getElementById("fm-mode");'
        'if(e){e.innerHTML=s.online?\'<span class="pill on">● ONLINE</span>\':\'<span class="pill off">● OFFLINE</span>\';}}).catch(()=>{});</script>'
    )

PWA_HEAD = (
    '<link rel="manifest" href="/manifest.webmanifest">'
    '<meta name="theme-color" content="#060d18">'
    '<link rel="apple-touch-icon" href="/icon-192.png">'
)
SW_SCRIPT = (
    '<script>if("serviceWorker" in navigator){navigator.serviceWorker.register("/sw.js").catch(()=>{});}</script>'
)

def page(title: str, body: str) -> bytes:
    doc = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — First Mate Deck</title>{PWA_HEAD}<style>{CSS}</style></head><body>{header_html()}<main>{body}</main><script>{GAMEPAD_JS}</script>{SW_SCRIPT}</body></html>'
    return doc.encode("utf-8")

def home_page() -> bytes:
    cards = "".join(
        f'<a class="bigbtn foci" href="/sample/{slug}">{html.escape(label)}<small>{html.escape(desc)} — press A to run, no typing</small></a>'
        for slug, _f, label, desc in SAMPLES
    )
    purl = html.escape(phone_url())
    facts = archive_facts()
    if facts["count"]:
        persist = (f'{facts["count"]} Ship Log{"s" if facts["count"] != 1 else ""} archived on this device — '
                   f'oldest {facts["oldest"]}, newest {facts["newest"]}. They survive restarts.')
    else:
        persist = "The archive starts with your first run — every Ship Log is kept on this device and survives restarts."
    base = phone_url().rsplit("/phone", 1)[0]
    curl = ("curl -X POST " + base + "/api/ship-log \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"chat\": \"Maya: We decided to ship Friday\\nRene: I will write the tests\", \"source\": \"agent\"}'")
    hood = f"""
<section class="hood">
  <p class="kicker">Under the hood</p>
  <h2 class="sect">What this machine can prove</h2>
  <div class="fact"><b>Persistent</b><span>{html.escape(persist)}</span></div>
  <div class="fact"><b>Agent-native</b><span>This product has an API and an <a href="/llms.txt">/llms.txt</a>. An agent can file a chat and read the log back — no screen to scrape.<div class="curlbox">{html.escape(curl)}</div></span></div>
  <div class="fact"><b>Cost of a local run</b><span>$0.00. No keys, no account, no per-seat anything.</span></div>
  <div class="fact"><b>Zero dependencies</b><span>Python standard library only. Limits, plainly: local summaries are extractive; there are no accounts.</span></div>
</section>
"""
    boat = """
<section class="hood">
  <p class="kicker">Why a persistent machine</p>
  <h2 class="sect">Built for an always-on home</h2>
  <p style="font-size:20.5px;color:var(--paper-dim);margin:.2em 0">First Mate belongs on an always-on machine: the crew's log stays current whether any laptop is open or not, and agents can file to it around the clock. This demo runs on a Steam Deck to prove it needs nothing special — zero dependencies, runs anywhere. The same package ships a Dockerfile and deploy guide for a persistent VM (Boat).</p>
</section>
"""
    wheel = (
        '<svg class="wheel" viewBox="0 0 200 200" fill="none" stroke="#f4f1ea" stroke-width="5" aria-hidden="true">'
        '<circle cx="100" cy="100" r="60"/><circle cx="100" cy="100" r="15"/>'
        '<line x1="100" y1="12" x2="100" y2="188"/><line x1="12" y1="100" x2="188" y2="100"/>'
        '<line x1="38" y1="38" x2="162" y2="162"/><line x1="162" y1="38" x2="38" y2="162"/></svg>'
    )
    body = f"""
<section class="hero">
  {wheel}
  <div class="hero-row">
    <img class="logo" src="/icon-512.png" alt="First Mate — ship's wheel logo">
    <div>
      <p class="kicker">Boat Hackathon · Crew Companion</p>
      <h1>First Mate</h1>
      <p class="tagline">Chats in. Ship Log out.</p>
    </div>
  </div>
</section>
<section class="pair">
  <img src="/qr.png" alt="QR code: scan to open First Mate on your phone">
  <div>
    <p class="kicker">Pair your phone</p>
    <h2>Your phone is the keyboard</h2>
    <p class="lead"><b>Scan — paste your chat on your phone — it lands here.</b></p>
    <p><span class="url">{purl}</span></p>
    <p>Phone captures. The Deck is the big-screen bridge. The watch glances and checks off.</p>
  </div>
</section>
<section>
  <p class="kicker">Live from the crew</p>
  <h2 class="sect">Latest Ship Log</h2>
  <div class="livebox" id="livebox"><p id="livemeta">Waiting for the first run… your phone sends chats here — or pick a crew below with the D-pad. A .txt dropped in the inbox folder works too.</p><ul id="liveactions"></ul><ul id="livedecisions"></ul></div>
</section>
<section>
  <p class="kicker">Signals — The Bridge</p>
  <h2 class="sect">The shared space</h2>
  <div class="livebox" id="bridgebox"><div id="bridgelist">{bridge_rows_html(bridge_latest(20))}</div></div>
  <p class="muted" style="margin:0">Muse, agents and surfaces leave signals here and read each other's. On this machine today; on a persistent VM, the same desk is always open. Local network only — no auth yet, stated plainly.</p>
</section>
<section>
  <p class="kicker">Controller ready · No typing</p>
  <h2 class="sect">Run a crew chat</h2>
  <p class="muted" style="margin:0">First Mate runs <b style="color:var(--paper)">on this Steam Deck</b> and shows the Ship Log — with its All Accesses record — right here.</p>
  <div class="grid">{cards}</div>
</section>
{hood}
{boat}
<div class="nav"><a class="foci" href="/logs">Saved Ship Logs</a><a class="foci" href="/phone">Phone app</a><a class="foci" href="/watch">Watch</a><a class="foci" href="/status">Status JSON</a></div>
<p class="foot">Same Ship Logs on every surface — the <a href="/phone">phone app</a> and <a href="/watch">watch view</a> read this Deck's saved logs. Run anywhere, see it everywhere.<br>Machine-readable: <a href="/llms.txt">/llms.txt</a> · <a href="/agent.json">/agent.json</a> · <a href="/logs">/logs</a></p>
<script>
{TOGGLE_JS}
var fmRun = null, fmSig = null;
function fmRender(s){{
  var box = document.getElementById("livebox"), meta = document.getElementById("livemeta");
  var ua = document.getElementById("liveactions"), ud = document.getElementById("livedecisions");
  if(!s || !s.actions){{ if(fmSig !== "none"){{ fmSig = "none"; meta.textContent = "No Ship Logs yet — run one from your phone or tap a crew below."; ua.innerHTML=""; ud.innerHTML=""; }} return; }}
  var sig = [s.run_id || "", (s.done || []).map(function(d){{return d ? "1" : "0";}}).join(""),
             (s.actions || []).length, (s.decisions || []).length].join("|");
  if(sig === fmSig){{ return; }}
  if(fmRun && s.run_id && s.run_id !== fmRun){{ box.classList.remove("flash"); void box.offsetWidth; box.classList.add("flash"); }}
  fmSig = sig;
  if(s.run_id){{ fmRun = s.run_id; }}
  meta.textContent = (s.date || "") + " · " + (s.source || "") + " · " + s.counts.actions + " to do · " + s.counts.decisions + " decided · " + s.counts.links + " links — press A on an action to check it off";
  ua.innerHTML = ""; ud.innerHTML = "";
  (s.actions || []).forEach(function(a, i){{
    var li = document.createElement("li");
    var done = s.done && s.done[i];
    li.textContent = (done ? "✅ " : "☐ ") + a;
    if(done){{ li.className = "doneact"; }}
    li.classList.add("foci"); li.tabIndex = 0;
    li.title = "Press A to check off / undo";
    li.addEventListener("click", function(){{ fmToggleDone(i, s.run_id); }});
    ua.appendChild(li);
  }});
  (s.decisions || []).slice(0, 5).forEach(function(d){{
    var li = document.createElement("li"); li.textContent = "⚓ " + d; li.style.cursor = "default"; ud.appendChild(li);
  }});
}}
window.fmRefresh = function(){{ fetch("/api/latest").then(function(r){{return r.json();}}).then(fmRender).catch(function(){{}}); }};
window.fmRefresh();
setInterval(window.fmRefresh, 5000);
var fmBridgeSig = null;
function fmRenderBridge(d){{
  var list = document.getElementById("bridgelist"); if(!list){{ return; }}
  var sigs = (d && d.signals) || [];
  var sig = sigs.map(function(s){{ return [s.ts, s.from, s.to, s.text].join("|"); }}).join("~");
  if(sig === fmBridgeSig){{ return; }}
  fmBridgeSig = sig;
  if(!sigs.length){{ list.innerHTML = '<p class="muted" style="margin:.2em 0">No signals yet — the desk is clear. Muse or any agent can leave one at POST /api/bridge.</p>'; return; }}
  list.innerHTML = "";
  sigs.forEach(function(s){{
    var row = document.createElement("div"); row.className = "sigrow";
    var meta = document.createElement("p"); meta.className = "sigmeta";
    meta.textContent = (s.from || "") + " → " + (s.to || "all") + " · " + (s.ts || "").replace("T", " ").slice(0, 16) + " UTC";
    var txt = document.createElement("p"); txt.className = "sigtext"; txt.textContent = s.text || "";
    row.appendChild(meta); row.appendChild(txt); list.appendChild(row);
  }});
}}
function fmBridgePoll(){{ fetch("/api/bridge").then(function(r){{return r.json();}}).then(fmRenderBridge).catch(function(){{}}); }}
fmBridgePoll();
setInterval(fmBridgePoll, 5000);
</script>
"""
    return page("Home", body)

def result_page(log, source_label: str) -> bytes:
    run_id = ""
    if getattr(log, "metadata", None):
        run_id = str(log.metadata.get("run_id") or "")
    done: list[bool] = []
    if run_id:
        target = find_log_by_run_id(run_id)
        if target is not None:
            done = load_done(target, len(log.transcript.actions))
    done = (done + [False] * len(log.transcript.actions))[:len(log.transcript.actions)]
    acts = "".join(
        f'<li class="foci{" doneact" if done[i] else ""}" tabindex="0" onclick="fmToggleDone({i}, \'{html.escape(run_id)}\')">{"✅" if done[i] else "☐"} {html.escape(a)}</li>'
        for i, a in enumerate(log.transcript.actions)
    ) or '<li style="cursor:default">No action items found in this chat.</li>'
    decs = "".join(f"<li>⚓ {html.escape(d)}</li>" for d in log.transcript.decisions) or "<li>No decisions recorded.</li>"
    lnks = "".join(f"<li>🔗 {html.escape(u)}</li>" for u in log.transcript.links) or "<li>No links shared.</li>"
    accesses_panel = render_accesses_html(log.accesses)
    body = f"""
<p class="kicker">Ship Log · Ready to share</p>
<h1>Your Ship Log</h1>
<p class="muted" style="font-size:21px">Source: {html.escape(source_label)} · Press A on an action to check it off — it syncs to phone and watch.</p>
<div class="nav"><a class="foci" href="/">← Home</a><a class="foci" href="/logs">Saved Logs</a></div>
<h2>What to do next</h2>
<ul class="actlist">{acts}</ul>
<h2>Decided</h2>
<ul class="plainlist">{decs}</ul>
<h2>Shared links</h2>
<ul class="plainlist">{lnks}</ul>
<p class="runline">{html.escape(run_footer_line(log))}</p>
<details class="accesseswrap"><summary class="foci">All Accesses — the full record</summary>{accesses_panel}</details>
<div class="nav"><a class="foci" href="/">← Make another</a><a class="foci" href="/logs">Saved Logs</a></div>
<script>{TOGGLE_JS}</script>
"""
    return page("Your Ship Log", body)

EMPTY_CHAT_MSG = ("That chat was empty — nothing to log yet. Pasting happens on your phone: "
                  "scan the QR code on the Deck home, paste the chat there, and the Ship Log lands right here.")

def error_page(title: str, message: str, ui_phone: bool = False) -> bytes:
    """Friendly HTML error — user-facing routes never return bare text."""
    if ui_phone:
        body = (f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
                '<div class="nav"><a href="/phone">← Phone home</a></div>')
        return phone_page("Oops", body)
    body = (f'<p class="kicker">First Mate</p><h1>{html.escape(title)}</h1>'
            f'<div class="errbox"><p style="margin:0">{html.escape(message)}</p></div>'
            '<div class="nav"><a class="bigbtn foci" href="/" style="align-items:center;text-align:center">← Back to Home</a></div>')
    return page("Oops", body)

def logs_page() -> bytes:
    cfg = load_config()
    d = Path(cfg.data_dir)
    files = sorted(d.glob("ship-log-*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
    if files:
        rows = "".join(
            f'<a class="logrow foci" href="/logs/{html.escape(p.name)}">{html.escape(p.name)}<br><small>{p.stat().st_size} bytes · {datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · tap to open / share on this WiFi network</small></a>'
            for p in files
        )
    else:
        rows = "<p>No Ship Logs saved yet. Run a sample from Home first.</p>"
    body = f'<p class="kicker">On-device archive</p><h1>Saved Ship Logs</h1><p class="muted">Stored on-device in <code>{html.escape(str(d))}</code>. On the same WiFi, open this Deck address from another device to view/share them.</p>{rows}<div class="nav"><a class="foci" href="/">← Home</a></div>'
    return page("Saved Logs", body)

# --- latest Ship Log: parsed from the shared store (data/ship-logs) ---

def _section_items(text: str, heading: str) -> list[str]:
    items, current = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        if current != heading:
            continue
        s = line.strip()
        if s.startswith("- [ ]") or s.startswith("- [x]"):
            s = s[5:].strip()
        elif s.startswith("- "):
            s = s[2:].strip()
        else:
            continue
        if s:
            items.append(s)
    return items

def latest_log_summary() -> dict | None:
    """Newest Ship Log in the shared store, or None. Deck, phone and
    watch all read this same store — that is the sync."""
    cfg = load_config()
    d = Path(cfg.data_dir)
    if not d.is_dir():
        return None
    files = sorted(d.glob("ship-log-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    p = files[0]
    text = p.read_text(encoding="utf-8", errors="replace")
    meta = {}
    mp = d / (p.name[:-3] + "-meta.json")
    if mp.is_file():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - meta is a bonus, md is truth
            meta = {}
    actions = _section_items(text, "What to do next")
    decisions = _section_items(text, "Decided")
    links = _section_items(text, "Shared links")
    date_line = ""
    for line in text.splitlines():
        if line.startswith("Date:"):
            date_line = line[len("Date:"):].strip()
            break
    counts = meta.get("counts", {}) if isinstance(meta, dict) else {}
    return {
        "title": "Ship Log",
        "file": p.name,
        "run_id": meta.get("run_id", ""),
        "date": date_line or meta.get("started_at", ""),
        "source": meta.get("source", ""),
        "privacy_mode": meta.get("privacy_mode", ""),
        "actions": actions,
        "actions_top5": actions[:5],
        "decisions": decisions,
        "done": load_done(p, len(actions)),
        "counts": {
            "actions": counts.get("actions", len(actions)),
            "decisions": counts.get("decisions", len(decisions)),
            "links": counts.get("links", len(links)),
            "messages": counts.get("messages", 0),
        },
    }

def saved_log_files() -> list[Path]:
    cfg = load_config()
    d = Path(cfg.data_dir)
    if not d.is_dir():
        return []
    return sorted(d.glob("ship-log-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

# --- Anicet pass: agent-readable contract + facts the app can prove ---

def archive_facts() -> dict:
    """Real numbers about the on-device archive, computed from disk."""
    files = saved_log_files()  # newest first
    def fmt(p: Path) -> str:
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "count": len(files),
        "oldest": fmt(files[-1]) if files else None,
        "newest": fmt(files[0]) if files else None,
    }

def run_footer_line(log) -> str:
    """One quiet line for result pages. The mode is read from the run's
    own metadata, so 'Local only' is claimed only when this run was."""
    mode = ""
    if getattr(log, "metadata", None):
        mode = str(log.metadata.get("privacy_mode") or "")
    if not mode:
        cfg = load_config()
        mode = "Private via NYTE" if cfg.inference_configured else "Local only"
    return f"Run cost $0.00 · {mode} · Zero-dependency engine · Full record in All Accesses ↓"

def llms_txt() -> bytes:
    text = f"""# First Mate — agent contract

First Mate turns a pasted team chat into a Ship Log: what to do next, what
was decided, and the links the team shared, with an All Accesses record of
every access the run made — and the ones it did not make, with reasons.
It runs on one machine (here: a Steam Deck). Deck, phone and watch are
surfaces of this one server and one on-disk store.
Version: {__version__}

## Machine contract

Base URL: this host and port (GET /status reports the port).
POST /api/ship-log — JSON body {{"chat": "<team chat text>", "source": "<label>"}}
  -> 200 JSON {{run_id, file, counts, actions, decisions, done}}. Empty chat -> 400.
GET /api/latest -> JSON summary of the newest Ship Log, including
  "done": [true/false per action].
POST /api/actions/done — JSON body {{"index": 0}} or {{"run_id": "...", "index": 0}}
  -> toggles one action's done state; returns the full done array.
POST /api/bridge — JSON body {{"from": "<who>", "to": "<who, optional, default all>", "text": "<signal>"}}
  -> leaves a signal on the Bridge; returns {{"ok": true, "count": <total signals>}}.
  Empty from or text -> 400. Text is capped at 500 chars.
GET /api/bridge -> {{"signals": [latest 20, newest first]}} — read the Bridge.
  The bridge is how Muse reaches the fleet and the fleet reaches back — this store is the shared space.
GET /status -> JSON: online/offline (measured by a real fetch, not assumed),
  privacy_mode, hosting, port.
GET /health -> JSON: engine health and configuration summary.
GET /agent.json -> this contract as a JSON manifest.
GET /logs -> HTML list of saved Ship Logs. GET /logs/<file> -> one saved log.
GET /qr.png -> QR code that pairs a phone to /phone.

## Persistence

Every run is archived on disk in data/ship-logs/ as ship-log-<run_id>.md
plus a -meta.json metadata file, with a -done.json sidecar for check-off
state. Bridge signals are appended to data/bridge.jsonl in the same
store. Archives survive restarts. Nothing is stored anywhere else.

## Privacy

Default mode is "Local only": the summary is computed in-process and no
team data leaves the machine. "Private via NYTE" is used only when that
route is fully configured (key + base URL + model); /status reports the
mode actually in effect, and every Ship Log's All Accesses section shows
which accesses a run really made.

## Cost

A local run costs $0.00. No API keys, no account, no sign-up.

## Deployment

This demo runs on-device (a Steam Deck) to prove it needs nothing
special. The package is built for a persistent, always-on VM: agents
can file chats and read logs around the clock whether any laptop is
open or not. A Dockerfile and a step-by-step deploy guide for a
persistent VM (Boat) are included in the package. It has not yet been
run on Boat — the demo runs are local, and /status says which hosting
each run used.

## Limits, plainly

Local summaries are extractive: lines are selected, not rewritten.
Link reading is one page at a time with a simple HTML-to-text pass;
offline, links are labelled "Not fetched" — never faked.
There are no accounts and no login. Run it on a trusted network only.
Dependencies: none — Python standard library only.
"""
    return text.encode("utf-8")

def agent_manifest() -> dict:
    return {
        "name": "First Mate",
        "version": __version__,
        "description": "Turns a pasted team chat into a Ship Log: next actions, decisions, shared links, and an All Accesses record of every access made and not made.",
        "endpoints": {
            "POST /api/ship-log": {
                "body": {"chat": "string, required", "source": "string, optional label"},
                "returns": "JSON {run_id, file, counts, actions, decisions, done}",
            },
            "GET /api/latest": "JSON summary of the newest Ship Log, including done flags per action",
            "POST /api/bridge": {
                "body": {"from": "string, required", "to": "string, optional (default: all)", "text": "string, required, capped at 500 chars"},
                "returns": "JSON {ok, count} — leaves a signal on the Bridge, the shared space between Muse, the fleet and the surfaces",
            },
            "GET /api/bridge": "JSON {signals: [latest 20, newest first]} — read the Bridge",
            "POST /api/actions/done": {
                "body": {"index": "integer, required", "run_id": "string, optional (default: latest run)"},
                "returns": "JSON {ok, run_id, file, index, done}",
            },
            "GET /status": "JSON: measured online/offline, privacy mode, hosting, port",
            "GET /health": "JSON: engine health and configuration summary",
            "GET /llms.txt": "This contract in plain text, written for agent readers",
            "GET /logs": "HTML list of saved Ship Logs",
            "GET /logs/<file>": "One saved Ship Log",
            "GET /qr.png": "QR code pairing a phone to /phone",
        },
        "surfaces": {
            "deck": "GET / — fullscreen UI on this machine",
            "phone": "GET /phone — installable PWA (capture surface)",
            "watch": "GET /watch — latest Ship Log, tap to check off",
        },
        "persistence": "Ship Logs archived on disk in data/ship-logs/ (markdown + JSON metadata + done-state sidecar); they survive restarts",
        "privacy_modes": [
            "Local only (default — nothing leaves the machine)",
            "Private via NYTE (only when fully configured)",
        ],
        "cost": "$0.00 per local run; no keys, no account",
        "dependencies": "none (Python standard library only)",
        "limits": [
            "Local summaries are extractive, not rewritten",
            "No accounts or login",
            "Link reading is a one-page HTML-to-text pass; offline links are labelled Not fetched",
        ],
    }

# --- PWA: manifest + service worker ---

MANIFEST = {
    "name": "First Mate",
    "short_name": "First Mate",
    "description": "Paste a team chat, get a Ship Log. Synced with Steam Deck — same Ship Logs everywhere.",
    "start_url": "/phone",
    "scope": "/",
    "display": "standalone",
    "theme_color": "#060d18",
    "background_color": "#060d18",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    ],
}

SW_JS = """const CACHE = 'first-mate-v4';
const SHELL = ['/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(k => k !== CACHE).map(k => caches.delete(k))
  )).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  // Deck Mode v4: HTML navigations and all app data are NETWORK-ONLY.
  // Only the manifest + icons are cached, so a relaunch always shows
  // the current build — a stale UI can never come back.
  if (e.request.method !== 'GET' || e.request.mode === 'navigate') {
    return; // network only
  }
  const p = new URL(e.request.url).pathname;
  if (SHELL.indexOf(p) >= 0) {
    e.respondWith(
      caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
        return res;
      }))
    );
  }
  // everything else: network only
});
"""

def icon_bytes(name: str) -> bytes | None:
    target = ROOT / name
    if target.is_file():
        return target.read_bytes()
    logo = ROOT / "logo.png"  # fallback: serve the logo itself
    return logo.read_bytes() if logo.is_file() else None

# --- Phone app (PWA surface) ---

PHONE_CSS = """
:root{
  color-scheme:dark;
  --ink:#060d18; --paper:#f4f1ea; --paper-dim:rgba(244,241,234,.62);
  --gold:#d9a441; --gold-dim:rgba(217,164,65,.55); --teal:#5ea8a0;
  --line:rgba(244,241,234,.10); --glass:rgba(255,255,255,.032);
  --serif:Georgia,"Iowan Old Style","Palatino Linotype","Times New Roman",serif;
  --sans:"Avenir Next","Segoe UI",system-ui,-apple-system,sans-serif;
}
*{box-sizing:border-box} html,body{margin:0;padding:0}
body{background:linear-gradient(165deg,#060d18 0%,#0a1626 58%,#081120 100%);background-attachment:fixed;
  color:var(--paper);font-family:var(--sans);font-size:18px;line-height:1.55}
a{color:#8fd0c7} :focus{outline:3px solid rgba(217,164,65,.9);outline-offset:3px;border-radius:10px}
.wrap{max-width:480px;margin:0 auto;padding:18px 16px 44px}
.wrap>*{animation:fmRise .7s cubic-bezier(.16,.7,.24,1) both}
.wrap>*:nth-child(2){animation-delay:.06s}.wrap>*:nth-child(3){animation-delay:.12s}
.wrap>*:nth-child(4){animation-delay:.18s}.wrap>*:nth-child(n+5){animation-delay:.24s}
@keyframes fmRise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
header.pstatus{position:sticky;top:0;z-index:10;background:rgba(6,13,24,.88);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--line);padding:12px 16px;font-size:16.5px;color:var(--paper-dim)}
header.pstatus b{color:var(--paper);font-weight:600}
.pill{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;font-size:12.5px;letter-spacing:.14em;vertical-align:2px}
.pill.on{background:rgba(94,168,160,.13);color:#8fd0c7;border:1px solid rgba(94,168,160,.45)}
.pill.off{background:rgba(224,138,122,.10);color:#e8a08e;border:1px solid rgba(224,138,122,.4)}
h1{font-family:var(--serif);font-weight:400;font-size:32px;margin:.25em 0 .35em;color:var(--paper)}
h2{font-family:var(--serif);font-weight:400;font-size:23px;color:var(--paper);margin:1.1em 0 .45em}
a.pbtn,button.pbtn{display:flex;flex-direction:column;gap:4px;justify-content:center;min-height:76px;padding:15px 18px;margin:11px 0;
  background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.014));border:1px solid var(--line);border-radius:16px;
  color:var(--paper);text-decoration:none;font-family:var(--serif);font-size:21.5px;font-weight:400;cursor:pointer;width:100%;text-align:left;
  transition:transform .25s,border-color .25s,box-shadow .25s}
a.pbtn small{font-family:var(--sans);font-size:15.5px;font-weight:400;color:var(--paper-dim)}
a.pbtn:active,button.pbtn:active{transform:scale(.99);border-color:var(--gold-dim)}
button.pbtn{font-family:var(--sans);font-weight:600}
textarea{width:100%;background:rgba(255,255,255,.03);color:var(--paper);border:1px solid var(--line);border-radius:14px;padding:14px;font-size:18px;min-height:130px}
textarea:focus{border-color:var(--gold-dim);outline:none;box-shadow:0 0 0 3px rgba(217,164,65,.18)}
pre{background:rgba(255,255,255,.028);border:1px solid var(--line);border-radius:14px;padding:15px;white-space:pre-wrap;word-wrap:break-word;font-size:15.5px;line-height:1.6}
.accesses{background:var(--glass);border:1px solid var(--line);border-radius:14px;padding:14px 17px;margin:16px 0;font-size:15.5px;line-height:1.6}
.accesses h2{margin-top:.1em}
a.logrow{display:block;background:var(--glass);border:1px solid var(--line);border-radius:14px;padding:14px 17px;margin:10px 0;color:var(--paper);text-decoration:none;font-size:17.5px;min-height:56px;transition:border-color .25s}
a.logrow small{color:var(--paper-dim)}
a.logrow:active{border-color:var(--gold-dim)}
.nav{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.nav a{display:inline-block;padding:11px 20px;background:transparent;color:var(--paper);font-weight:600;border:1px solid rgba(217,164,65,.45);border-radius:999px;text-decoration:none;font-size:17px}
.nav a:active{background:var(--gold);color:#0a1626}
.sigrow{padding:10px 0;border-bottom:1px solid rgba(244,241,234,.06)}
.sigrow:last-child{border-bottom:0}
.sigrow .sigmeta{font-size:12px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--gold);margin:0 0 2px}
.sigrow .sigtext{font-size:16.5px;margin:0}
.sync{background:var(--glass);border:1px solid rgba(217,164,65,.35);border-radius:14px;padding:13px 16px;font-size:16px;margin:12px 0;color:var(--paper-dim)}
.sync b{color:var(--paper)}
.doneact{color:rgba(244,241,234,.42) !important;background-image:linear-gradient(rgba(217,164,65,.8),rgba(217,164,65,.8));
  background-repeat:no-repeat;background-position:0 56%;background-size:100% 2px}
a.actrow{display:block;background:rgba(255,255,255,.028);border:1px solid var(--line);border-radius:14px;padding:13px 16px;margin:8px 0;color:var(--paper);text-decoration:none;font-size:18px;transition:border-color .25s}
a.actrow:active{border-color:var(--gold-dim)}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation-duration:.001s !important;animation-iteration-count:1 !important;transition-duration:.001s !important}
}
"""

def phone_page(title: str, body: str) -> bytes:
    s = status_payload()
    pill = '<span class="pill on">● ONLINE</span>' if s["online"] else '<span class="pill off">● OFFLINE</span>'
    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)} — First Mate</title>{PWA_HEAD}<style>{PHONE_CSS}</style></head><body>'
        f'<header class="pstatus"><b>First Mate</b> {pill}<br>Privacy <b>{html.escape(s["privacy_mode"])}</b> · Hosting <b>Steam Deck — on-device</b></header>'
        f'<div class="wrap">{body}</div>{SW_SCRIPT}</body></html>'
    )
    return doc.encode("utf-8")

def phone_home_page() -> bytes:
    cards = "".join(
        f'<a class="pbtn" href="/sample/{slug}?ui=phone">{html.escape(label)}<small>{html.escape(desc)} — tap to run</small></a>'
        for slug, _f, label, desc in SAMPLES
    )
    files = saved_log_files()
    if files:
        rows = "".join(
            f'<a class="logrow" href="/logs/{html.escape(p.name)}?ui=phone">📄 {html.escape(p.name)}<br><small>{datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</small></a>'
            for p in files
        )
    else:
        rows = "<p>No Ship Logs saved yet. Run a sample above.</p>"
    latest = latest_log_summary()
    if latest is None:
        latest_block = "<p>No Ship Logs yet — your runs will appear here, on the Deck and on the watch.</p>"
    else:
        acts = "".join(
            f'<a class="actrow{" doneact" if latest["done"][i] else ""}" href="#" onclick="fmToggleDone({i}, \'{html.escape(latest["run_id"])}\'); return false;">{"✅" if latest["done"][i] else "☐"} {html.escape(a)}</a>'
            for i, a in enumerate(latest["actions"])
        ) or "<p>No actions in the latest log.</p>"
        latest_block = f'<p>{html.escape(latest["date"])} · {html.escape(latest["source"])}</p>{acts}'
    sigs = bridge_latest(5)
    if sigs:
        sig_rows = "".join(
            f'<div class="sigrow"><p class="sigmeta">{html.escape(s["from"])} → {html.escape(s["to"])} · {html.escape(s["ts"][:16].replace("T", " "))} UTC</p><p class="sigtext">{html.escape(s["text"])}</p></div>'
            for s in sigs
        )
    else:
        sig_rows = "<p>No signals yet — the desk is clear.</p>"
    signals_block = f"<h2>📡 Signals — the Bridge</h2>{sig_rows}"
    body = f"""
<h1>First Mate — Phone</h1>
<div class="sync">🔄 <b>Synced with Steam Deck — same Ship Logs everywhere.</b> This phone talks to the Deck's First Mate server; a run made here, on the Deck, or seen on the watch all come from the same saved logs on the Deck.</div>
<h2>Run a crew chat</h2>
{cards}
<h2>Or paste your own chat</h2>
<form method="post" action="/ship-log?ui=phone">
<textarea name="chat" placeholder="Paste team chat here…"></textarea>
<p><button class="pbtn" type="submit" style="align-items:center;text-align:center">Make my Ship Log</button></p>
</form>
<h2>Latest Ship Log — tap to check off</h2>
{latest_block}
{signals_block}
<h2>Saved Ship Logs (synced)</h2>
{rows}
<div class="nav"><a href="/">🖥 Deck view</a><a href="/watch">⌚ Watch view</a></div>
<script>
{TOGGLE_JS}
window.fmRefresh = function(){{ location.reload(); }};
</script>
"""
    return phone_page("Phone", body)

def phone_result_page(log, source_label: str) -> bytes:
    accesses_panel = render_accesses_html(log.accesses)
    body = f"""
<h1>Your Ship Log</h1>
<p>Source: {html.escape(source_label)} · Saved on the Deck — it now shows on Deck, phone and watch.</p>
<div class="nav"><a href="/phone">← Phone home</a><a href="/watch">⌚ Watch</a></div>
<pre>{html.escape(log.markdown)}</pre>
<p style="color:var(--paper-dim);font-size:15px;letter-spacing:.04em">{html.escape(run_footer_line(log))}</p>
{accesses_panel}
<div class="nav"><a href="/phone">← Make another</a></div>
"""
    return phone_page("Your Ship Log", body)

def phone_log_view(name: str, text: str) -> bytes:
    body = f'<h1 style="font-size:24px">{html.escape(name)}</h1><div class="nav"><a href="/phone">← Phone home</a></div><pre>{html.escape(text)}</pre>'
    return phone_page("Saved Log", body)

# --- Watch companion (Galaxy Watch web surface) ---

def watch_page() -> bytes:
    s = latest_log_summary()
    now = datetime.now().strftime("%H:%M:%S")
    if s is None:
        inner = "<h1>⛵ First Mate</h1><p>No Ship Logs yet — run one on Deck or phone.</p>"
    else:
        done = s.get("done", [])
        items = "".join(
            f'<li class="{"done" if i < len(done) and done[i] else ""}" onclick="fmToggleDone({i}, \'{html.escape(s["run_id"])}\')">{"✅" if i < len(done) and done[i] else "☐"} {html.escape(a)}</li>'
            for i, a in enumerate(s["actions_top5"])
        ) or "<li>No actions in this log.</li>"
        c = s["counts"]
        inner = (
            f"<h1>⛵ {html.escape(s['title'])}</h1>"
            f'<p class="when">{html.escape(s["date"])}</p>'
            f"<h2>What to do next</h2><ul>{items}</ul>"
            f'<p class="counts">✅ {c["decisions"]} decided · 🔗 {c["links"]} links · 📋 {c["actions"]} to do</p>'
        )
    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="30">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>First Mate — Watch</title><style>"
        "*{box-sizing:border-box}body{background:#000;color:#fff;font-family:system-ui,sans-serif;"
        "font-size:28px;line-height:1.45;margin:0;padding:26px 20px;text-align:center}"
        "h1{font-size:34px;color:#d9a441;margin:.2em 0;font-weight:400}h2{font-size:30px;color:#6fb3aa;font-weight:400}"
        "ul{list-style:none;padding:0;text-align:left}li{margin:16px 0;font-size:28px;cursor:pointer}"
        "li.done{text-decoration:line-through;color:#9db89a}"
        ".when{color:rgba(244,241,234,.62);font-size:24px}.counts{font-size:25px}.synced{color:#6fb3aa;font-size:22px;margin-top:26px}"
        "a{color:#8fd0c7;font-size:24px}"
        "</style></head><body>"
        f"{inner}"
        f'<p class="synced">🔄 Synced • {now}<br>Same Ship Log as Deck &amp; phone — tap an action to check it off</p>'
        '<p><a href="/phone">Phone</a> · <a href="/">Deck</a></p>'
        f"<script>{TOGGLE_JS}window.fmRefresh = function(){{ location.reload(); }};</script>"
        "</body></html>"
    )
    return doc.encode("utf-8")

class DeckHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send(self, status, ctype, body: bytes):
        self.send_response(status); self.send_header("Content-Type", ctype)
        # Deck Mode v4: HTML (and the SW script itself) is never cached,
        # so a relaunch always shows the current build.
        if ctype.startswith("text/html") or self.path.split("?")[0] == "/sw.js":
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        ui_phone = (query.get("ui") or [""])[0] == "phone"
        if path == "/health":
            self._send(200, "application/json", json.dumps(health_payload()).encode())
        elif path == "/status":
            self._send(200, "application/json", json.dumps(status_payload()).encode())
        elif path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", home_page())
        elif path == "/phone":
            self._send(200, "text/html; charset=utf-8", phone_home_page())
        elif path == "/manifest.webmanifest":
            self._send(200, "application/manifest+json", json.dumps(MANIFEST).encode())
        elif path == "/sw.js":
            self._send(200, "text/javascript", SW_JS.encode())
        elif path in ("/icon-192.png", "/icon-512.png"):
            data = icon_bytes(path.lstrip("/"))
            if data is None:
                self._send(404, "text/plain", b"Not found")
            else:
                self._send(200, "image/png", data)
        elif path == "/watch":
            self._send(200, "text/html; charset=utf-8", watch_page())
        elif path == "/qr.png":
            try:
                self._send(200, "image/png", qr_png_bytes(phone_url()))
            except Exception:
                self._send(500, "text/plain", b"QR generation failed")
        elif path == "/llms.txt":
            self._send(200, "text/plain; charset=utf-8", llms_txt())
        elif path == "/agent.json":
            self._send(200, "application/json", json.dumps(agent_manifest()).encode())
        elif path == "/api/bridge":
            self._send(200, "application/json", json.dumps({"signals": bridge_latest(20)}).encode())
        elif path == "/api/latest":
            s = latest_log_summary()
            payload = s if s is not None else {"latest": None, "message": "No Ship Logs yet — run one on Deck or phone."}
            self._send(200, "application/json", json.dumps(payload).encode())
        elif path == "/logs":
            self._send(200, "text/html; charset=utf-8", logs_page())
        elif path.startswith("/logs/"):
            self._serve_log(path[len("/logs/"):], ui_phone)
        elif path.startswith("/sample/"):
            self._run_sample(path[len("/sample/"):], ui_phone)
        else:
            self._send(404, "text/plain", b"Not found")

    def _serve_log(self, name: str, ui_phone: bool = False):
        # basename only — no traversal, .md only
        safe = Path(name).name
        if safe != name or not safe.startswith("ship-log-") or not safe.endswith(".md"):
            self._send(404, "text/html; charset=utf-8", error_page("No such log", "That Ship Log is not in the on-device archive.", ui_phone)); return
        cfg = load_config(); target = Path(cfg.data_dir) / safe
        if not target.is_file():
            self._send(404, "text/html; charset=utf-8", error_page("No such log", "That Ship Log is not in the on-device archive.", ui_phone)); return
        text = target.read_text(encoding="utf-8", errors="replace")
        if ui_phone:
            self._send(200, "text/html; charset=utf-8", phone_log_view(safe, text)); return
        body = f'<h1>{html.escape(safe)}</h1><div class="nav"><a class="foci" href="/logs">← All logs</a><a class="foci" href="/">Home</a></div><pre>{html.escape(text)}</pre>'
        self._send(200, "text/html; charset=utf-8", page("Saved Log", body))

    def _run_sample(self, slug: str, ui_phone: bool = False):
        entry = SAMPLE_MAP.get(slug)
        if not entry:
            self._send(404, "text/html; charset=utf-8", error_page("Unknown crew", "That sample crew does not exist on this Deck.", ui_phone)); return
        fname, label = entry
        fpath = SAMPLE_DIR / fname
        if not fpath.is_file():
            self._send(500, "text/html; charset=utf-8", error_page("Sample missing", "That sample chat file is missing on this device.", ui_phone)); return
        text = fpath.read_text(encoding="utf-8")
        cfg = load_config()
        try:
            log = build_ship_log(text, cfg, source_label=f"Deck sample {label} ({fname}, Teamily group chat)")
        except InputError as exc:
            self._send(400, "text/html; charset=utf-8", error_page("Could not build that Ship Log", str(exc), ui_phone)); return
        except Exception:
            self._send(500, "text/html; charset=utf-8", error_page("Something went wrong", "Something went wrong building the Ship Log. Head back home — your saved logs are untouched.", ui_phone)); return
        save_ship_log(log, Path("."), cfg)
        if ui_phone:
            self._send(200, "text/html; charset=utf-8", phone_result_page(log, label))
        else:
            self._send(200, "text/html; charset=utf-8", result_page(log, label))

    def _send_json(self, status, payload: dict):
        self._send(status, "application/json", json.dumps(payload).encode())

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > MAX_REQUEST_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 - bad JSON is a 400, handled by caller
            return None
        return data if isinstance(data, dict) else None

    def _api_ship_log(self):
        data = self._read_json_body()
        if data is None:
            self._send_json(400, {"error": "Body must be a JSON object like {\"chat\": \"...\", \"source\": \"Phone\"}."}); return
        chat = data.get("chat")
        if not isinstance(chat, str) or not chat.strip():
            self._send_json(400, {"error": "Paste some chat text first (field: chat)."}); return
        source = data.get("source")
        source_label = source.strip() if isinstance(source, str) and source.strip() else "Phone (API)"
        cfg = load_config()
        try:
            log = build_ship_log(chat, cfg, source_label=source_label)
        except InputError as exc:
            self._send_json(400, {"error": str(exc)}); return
        except Exception:
            self._send_json(500, {"error": "Something went wrong building the Ship Log."}); return
        with _done_lock:
            paths = save_ship_log(log, Path("."), cfg)
        meta = log.metadata or {}
        actions = list(log.transcript.actions)
        self._send_json(200, {
            "run_id": meta.get("run_id", ""),
            "file": paths["archive"].name,
            "counts": meta.get("counts", {}),
            "actions": actions,
            "decisions": list(log.transcript.decisions),
            "done": [False] * len(actions),
            "source": source_label,
        })

    def _api_bridge_post(self):
        data = self._read_json_body()
        if data is None:
            self._send_json(400, {"error": "Body must be a JSON object like {\"from\": \"Muse\", \"to\": \"fleet\", \"text\": \"...\"}."}); return
        frm = data.get("from")
        text = data.get("text")
        if not isinstance(frm, str) or not frm.strip() or not isinstance(text, str) or not text.strip():
            self._send_json(400, {"error": "Fields 'from' and 'text' are required and must be non-empty strings."}); return
        to = data.get("to")
        to_label = to.strip() if isinstance(to, str) and to.strip() else "all"
        count = bridge_append(frm.strip(), to_label, text.strip())
        self._send_json(200, {"ok": True, "count": count})

    def _api_actions_done(self):
        data = self._read_json_body()
        if data is None or not isinstance(data.get("index"), int) or isinstance(data.get("index"), bool):
            self._send_json(400, {"error": "Body must be JSON like {\"index\": 0} or {\"run_id\": \"...\", \"index\": 0}."}); return
        index = data["index"]
        run_id = data.get("run_id")
        if isinstance(run_id, str) and run_id:
            target = find_log_by_run_id(run_id)
            if target is None:
                self._send_json(404, {"error": f"No Ship Log with run_id {run_id}."}); return
        else:
            files = saved_log_files()
            if not files:
                self._send_json(404, {"error": "No Ship Logs yet."}); return
            target = files[0]
        text = target.read_text(encoding="utf-8", errors="replace")
        actions = _section_items(text, "What to do next")
        if index < 0 or index >= len(actions):
            self._send_json(400, {"error": f"index {index} out of range (0..{len(actions) - 1})."}); return
        with _done_lock:
            done = load_done(target, len(actions))
            done[index] = not done[index]
            save_done(target, done)
        meta = {}
        mp = target.with_name(target.name[:-len(".md")] + "-meta.json")
        if mp.is_file():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                meta = {}
        self._send_json(200, {"ok": True, "run_id": meta.get("run_id", ""), "file": target.name,
                              "index": index, "done": done})

    def do_POST(self):
        route = self.path.split("?")[0]
        if route == "/api/ship-log":
            self._api_ship_log(); return
        if route == "/api/bridge":
            self._api_bridge_post(); return
        if route == "/api/actions/done":
            self._api_actions_done(); return
        if route != "/ship-log":
            self._send(404, "text/plain", b"Not found"); return
        query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        ui_phone = (query.get("ui") or [""])[0] == "phone"
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, "text/html; charset=utf-8", error_page("That request looked off", "Something garbled came through. Head back home and send the chat from your phone.", ui_phone)); return
        if length < 0:
            self._send(400, "text/html; charset=utf-8", error_page("That request looked off", "Something garbled came through. Head back home and send the chat from your phone.", ui_phone)); return
        if length > MAX_REQUEST_BYTES:
            self._send(413, "text/html; charset=utf-8", error_page("That chat is too large", "That chat is too large for one run — split it into parts on your phone and send each part.", ui_phone)); return
        raw = self.rfile.read(length).decode("utf-8", "replace")
        chat = (parse_qs(raw).get("chat") or [""])[0]
        if not chat.strip():
            self._send(400, "text/html; charset=utf-8", error_page("That chat was empty", EMPTY_CHAT_MSG, ui_phone)); return
        cfg = load_config()
        try:
            log = build_ship_log(chat, cfg, source_label="Deck UI paste (Teamily group chat, pasted text)")
        except InputError as exc:
            self._send(400, "text/html; charset=utf-8", error_page("Could not build that Ship Log", str(exc), ui_phone)); return
        except Exception:
            self._send(500, "text/html; charset=utf-8", error_page("Something went wrong", "Something went wrong building the Ship Log. Head back home — your saved logs are untouched.", ui_phone)); return
        save_ship_log(log, Path("."), cfg)
        if ui_phone:
            self._send(200, "text/html; charset=utf-8", phone_result_page(log, "Pasted chat"))
        else:
            self._send(200, "text/html; charset=utf-8", result_page(log, "Pasted chat"))

def serve_deck(host: str = "0.0.0.0", port: int | None = None) -> None:
    cfg = load_config()
    p = port if port is not None else cfg.port
    server = ThreadingHTTPServer((host, p), DeckHandler)
    threading.Thread(target=_inbox_watcher, name="fm-inbox", daemon=True).start()
    print(f"First Mate — Deck Edition at http://{host}:{p}")
    print("Health: /health · Status: /status · Logs: /logs · Phone: /phone · Watch: /watch · Latest: /api/latest")
    print(f"Pairing: QR at /qr.png -> {phone_url()} · Inbox drop folder: {INBOX_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    serve_deck()
