"""Tiny web UI, stdlib http.server only.

Pages:
  GET  /         Paste chat text form
  POST /ship-log Build a Ship Log from pasted text and show it
  GET  /health   JSON health check, for a Boat.dev VM or any host

Demo use: run this, open it in a browser, paste a team chat, get a
Ship Log back that you can copy into Teamily.
"""
from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .cli import health_payload
from .config import load_config
from .ship_log import build_ship_log, render_accesses_html, save_ship_log
from pathlib import Path

HOME_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>First Mate</title>
<style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#14324a}
h1{color:#0b5fa5} textarea{width:100%;box-sizing:border-box}
button{background:#0b5fa5;color:#fff;border:0;padding:.6rem 1.2rem;border-radius:.4rem;font-size:1rem;cursor:pointer}
pre{background:#eef4f8;padding:1rem;overflow:auto;white-space:pre-wrap}
</style></head><body>
<h1>First Mate</h1>
<p>We are building a helper that sits in a team chat.<br>
It reads what the team shares and makes a simple list of what to do next, and it keeps it private.</p>
<p>Paste a team chat below. Export or copy it from Teamily, paste it here, and get a Ship Log back.</p>
<form method="post" action="/ship-log">
<textarea name="chat" rows="14" placeholder="Paste team chat here, for example:&#10;Maya: We decided to keep it simple&#10;Rene: I will build the first version by Friday&#10;Maya: Useful link https://boat.dev/"></textarea>
<p><button type="submit">Make my Ship Log</button></p>
</form>
<p><small>Privacy mode is shown on every Ship Log. With no keys set, all work stays on this machine, and that is a complete working mode, no credits needed. Every result page also shows an All accesses panel, listing every access the run made and the ones it did not make, with the reason.</small></p>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # keep demo logs quiet
        pass

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps(health_payload()).encode("utf-8")
            self._send(200, "application/json", body)
        elif self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HOME_PAGE.encode("utf-8"))
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path != "/ship-log":
            self._send(404, "text/plain", b"Not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        fields = parse_qs(raw)
        chat = (fields.get("chat") or [""])[0]
        if not chat.strip():
            self._send(400, "text/plain", b"Paste some chat text first.")
            return
        config = load_config()
        log = build_ship_log(
            chat, config, source_label="Web UI paste (Teamily group chat, pasted text)"
        )
        save_ship_log(log, Path("."), config)
        accesses_panel = render_accesses_html(log.accesses)
        page = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Your Ship Log - First Mate</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;"
            "padding:0 1rem;line-height:1.5;color:#14324a}h1{color:#0b5fa5}"
            "pre{background:#eef4f8;padding:1rem;overflow:auto;white-space:pre-wrap}"
            ".accesses{background:#f7fafc;border:1px solid #cfe0ec;border-radius:.5rem;"
            "padding:1rem 1.2rem;margin:1.5rem 0}</style>"
            "</head><body><h1>Your Ship Log</h1>"
            "<p>Copy this back into your Teamily group chat.</p>"
            f"<pre>{html.escape(log.markdown)}</pre>"
            f"{accesses_panel}"
            "<p><a href=\"/\">Make another</a></p>"
            f"<div>{log.html_page}</div>"
            "</body></html>"
        )
        self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))

    def _send(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve() -> None:
    config = load_config()
    server = ThreadingHTTPServer((config.host, config.port), Handler)
    print(f"First Mate web UI at http://{config.host}:{config.port}")
    print("Health check at /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    serve()
