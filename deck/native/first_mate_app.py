#!/usr/bin/env python3
"""First Mate — native Steam Deck app (pygame-ce / SDL2).

A REAL Deck app: SDL reads the controller directly (D-pad, sticks,
buttons) — no browser, no web input layer. It is a surface of the
same on-device store the server uses: data/ship-logs (Ship Logs +
done sidecars) and data/bridge.jsonl (Bridge signals). Checking an
action off here writes the same sidecar the phone/watch read.

Controls:
  D-pad / left stick   move selection
  A (button 0)         check off / open
  B (button 1)         back to latest log
  L1 / R1 (4 / 5)      switch screen: Ship Log | Signals | Logs
  Menu (button 7)      quit
Keyboard fallback: arrows, Enter, Esc, Tab. Touch/mouse: click rows.
Every joystick event is logged to input.log next to this file so the
input path can be verified from the machine itself.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pygame

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = DATA_DIR / "ship-logs"
BRIDGE_FILE = DATA_DIR / "bridge.jsonl"
INPUT_LOG = APP_DIR / "input.log"

INK = (6, 13, 24)
INK2 = (10, 22, 38)
PAPER = (244, 241, 234)
DIM = (150, 160, 175)
GOLD = (217, 164, 65)
TEAL = (94, 168, 160)
ROW_BG = (16, 28, 46)
ROW_SEL = (38, 54, 82)

W, H = 1280, 800


def log_input(msg: str) -> None:
    try:
        with INPUT_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
    except Exception:
        pass


_MODEL = None


def transcribe_wav(path: Path) -> str:
    """On-device speech to text (Vosk small en model, fully offline).
    Returns '' when nothing was caught or the engine is unavailable."""
    global _MODEL
    try:
        import wave

        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        if _MODEL is None:
            _MODEL = Model(str(APP_DIR / "models" / "vosk-model-small-en-us-0.15"))
        wf = wave.open(str(path), "rb")
        rec = KaldiRecognizer(_MODEL, wf.getframerate())
        out = ""
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                out += json.loads(rec.Result()).get("text", "") + " "
        out += json.loads(rec.FinalResult()).get("text", "")
        return out.strip()
    except Exception as e:
        log_input(f"transcribe FAILED {e}")
        return ""


# ---------- store (same files the server uses) ----------

def section_items(text: str, heading: str) -> list[str]:
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


def done_path(md_file: Path) -> Path:
    return md_file.with_name(md_file.name[: -len(".md")] + "-done.json")


def load_done(md_file: Path, n: int) -> list[bool]:
    try:
        done = [bool(x) for x in json.loads(done_path(md_file).read_text()).get("done", [])]
    except Exception:
        done = []
    return (done + [False] * n)[:n]


def save_done(md_file: Path, done: list[bool]) -> None:
    done_path(md_file).write_text(json.dumps({"done": done}) + "\n", encoding="utf-8")


def list_logs() -> list[Path]:
    if not LOGS_DIR.is_dir():
        return []
    return sorted(LOGS_DIR.glob("ship-log-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def read_log(md_file: Path) -> dict:
    text = md_file.read_text(encoding="utf-8", errors="replace")
    meta = {}
    mp = md_file.with_name(md_file.name[: -len(".md")] + "-meta.json")
    if mp.is_file():
        try:
            meta = json.loads(mp.read_text())
        except Exception:
            meta = {}
    actions = section_items(text, "What to do next")
    return {
        "file": md_file,
        "source": meta.get("source", md_file.name),
        "date": meta.get("started_at", ""),
        "actions": actions,
        "decisions": section_items(text, "Decided"),
        "links": section_items(text, "Shared links"),
        "done": load_done(md_file, len(actions)),
    }


def read_signals(limit: int = 12) -> list[dict]:
    if not BRIDGE_FILE.is_file():
        return []
    out = []
    try:
        for line in BRIDGE_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return list(reversed(out))[:limit]


# ---------- text helpers ----------

def wrap(font: pygame.font.Font, text: str, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------- app ----------

class App:
    SCREENS = ["SHIP LOG", "CHAT", "SIGNALS", "LOGS", "ABOARD"]

    def __init__(self) -> None:
        pygame.init()
        pygame.joystick.init()
        self.screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
        pygame.display.set_caption("First Mate")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.f_title = pygame.font.SysFont("dejavusans", 54, bold=False)
        self.f_head = pygame.font.SysFont("dejavusans", 30, bold=True)
        self.f_row = pygame.font.SysFont("dejavusans", 30)
        self.f_small = pygame.font.SysFont("dejavusans", 22)
        self.f_tab = pygame.font.SysFont("dejavusans", 26, bold=True)
        self.tab = 0
        self.sel = 0
        self.current: Path | None = None
        self.log_data: dict | None = None
        self.logs: list[Path] = []
        self.signals: list[dict] = []
        self._stamp = 0.0
        self.stick_cool = 0.0
        self.banner = ""
        self.banner_until = 0.0
        self._last_sig_ts = ""
        self._last_log_mtime = 0.0
        self.pinned = False
        self.rec_proc = None
        self.rec_start = 0.0
        self.rec_file: Path | None = None
        self.transcribing = False
        self.pads = []
        for i in range(pygame.joystick.get_count()):
            j = pygame.joystick.Joystick(i)
            j.init()
            self.pads.append(j)
            log_input(f"joystick {i}: {j.get_name()} buttons={j.get_numbuttons()} hats={j.get_numhats()} axes={j.get_numaxes()}")
        log_input(f"app start, {len(self.pads)} joystick(s)")
        self.reload(force=True)

    def reload(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._stamp < 2.0:
            return
        self._stamp = now
        self.logs = list_logs()
        # The Ship Log screen IS the latest log by definition: always
        # follow the newest file unless the user pinned one in LOGS.
        if self.logs and (self.current is None or (self.tab == 0 and not getattr(self, "pinned", False))):
            if self.current != self.logs[0]:
                self.current = self.logs[0]
                self.sel = 0
        if self.current is not None and self.current.is_file():
            self.log_data = read_log(self.current)
        new_signals = read_signals()
        # live-arrival detection: banner when a signal or a log lands
        if new_signals:
            ts = str(new_signals[0].get("ts", ""))
            if self._last_sig_ts and ts > self._last_sig_ts:
                self.banner = f"New signal from {new_signals[0].get('from', '?')} — R1 to Signals"
                self.banner_until = now + 5
            self._last_sig_ts = ts
        if self.logs:
            mt = self.logs[0].stat().st_mtime
            if self._last_log_mtime and mt > self._last_log_mtime:
                self.banner = "New Ship Log filed — it is on this screen"
                self.banner_until = now + 5
                self.current = self.logs[0]
                self.log_data = read_log(self.current)
            self._last_log_mtime = mt
        self.signals = new_signals

    # ----- actions -----
    def rows(self) -> int:
        if self.tab == 0:
            return len(self.log_data["actions"]) if self.log_data else 0
        if self.tab == 2:
            return len(self.signals)
        if self.tab == 3:
            return len(self.logs)
        return 0

    def move(self, d: int) -> None:
        n = self.rows()
        if n:
            self.sel = max(0, min(n - 1, self.sel + d))

    def activate(self) -> None:
        if self.tab == 1:
            self.toggle_recording()
        elif self.tab == 0 and self.log_data and self.log_data["actions"]:
            i = self.sel
            done = self.log_data["done"]
            done[i] = not done[i]
            save_done(self.log_data["file"], done)
            self.log_data["done"] = done
        elif self.tab == 3 and self.logs:
            self.current = self.logs[self.sel]
            self.log_data = read_log(self.current)
            self.pinned = True
            self.tab = 0
            self.sel = 0

    def back(self) -> None:
        if self.rec_proc is not None:
            self.toggle_recording()
        if self.tab != 0:
            self.tab = 0
            self.sel = 0
        elif self.pinned or (self.logs and self.current != self.logs[0]):
            self.pinned = False
            if self.logs:
                self.current = self.logs[0]
                self.log_data = read_log(self.current)
            self.sel = 0

    # ----- voice chat (push to talk, like the Muse chat) -----
    def toggle_recording(self) -> None:
        import subprocess

        if self.transcribing:
            return
        if self.rec_proc is None:
            voice_dir = DATA_DIR / "voice"
            voice_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            self.rec_file = voice_dir / f"voice-{stamp}.wav"
            try:
                self.rec_proc = subprocess.Popen(
                    ["pw-record", "--rate", "16000", "--channels", "1", str(self.rec_file)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self.rec_start = time.time()
                log_input(f"recording start {self.rec_file.name}")
            except Exception as e:
                log_input(f"recording FAILED {e}")
                self.rec_proc = None
        else:
            dur = max(1, int(time.time() - self.rec_start))
            proc, self.rec_proc = self.rec_proc, None
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            log_input(f"recording stop {dur}s")
            if self.rec_file is not None and self.rec_file.is_file():
                # transcribe ON the Deck first, then send the words
                self.transcribing = True
                wav, dur_s = self.rec_file, dur

                def _send() -> None:
                    text = transcribe_wav(wav)
                    if text:
                        body = text
                    else:
                        body = f"(voice note, {dur_s}s — no words caught; audio saved aboard as {wav.name})"
                    sig = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "from": "Rene (voice)",
                        "to": "Muse (Tree)",
                        "text": body,
                    }
                    try:
                        with BRIDGE_FILE.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(sig) + "\n")
                    except Exception:
                        pass
                    if text:
                        # the words also become a Ship Log via the inbox
                        try:
                            inbox = ROOT / "inbox"
                            inbox.mkdir(exist_ok=True)
                            (inbox / f"voice-{wav.stem}.txt").write_text(
                                f"Rene (voice note): {text}\n", encoding="utf-8"
                            )
                        except Exception:
                            pass
                    self.banner = "Sent to Tree"
                    self.banner_until = time.time() + 5
                    self.transcribing = False
                    log_input(f"transcribed+sent: {body[:60]!r}")

                import threading

                threading.Thread(target=_send, daemon=True).start()

    def switch(self, d: int) -> None:
        self.tab = (self.tab + d) % len(self.SCREENS)
        self.sel = 0

    # ----- drawing -----
    def draw_wheel(self, cx: int, cy: int, r: int) -> None:
        s = self.screen
        col = (52, 62, 84)
        pygame.draw.circle(s, col, (cx, cy), r, 3)
        pygame.draw.circle(s, col, (cx, cy), r // 4, 3)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7), (0.7, 0.7)):
            pygame.draw.line(s, col, (cx, cy), (cx + int(dx * r * 1.25), cy + int(dy * r * 1.25)), 3)

    def draw(self) -> None:
        s = self.screen
        s.fill(INK)
        self.draw_wheel(1150, 300, 210)
        # header
        pygame.draw.rect(s, INK2, (0, 0, W, 86))
        t = self.f_head.render("⚓ FIRST MATE", True, GOLD)
        s.blit(t, (36, 26))
        clock = datetime.now().strftime("%H:%M")
        st = f"{clock}  ·  Steam Deck — on-device  ·  {len(self.signals)} signals on the bridge"
        s.blit(self.f_small.render(st, True, DIM), (W - self.f_small.size(st)[0] - 36, 34))
        # tabs
        x = 36
        for i, name in enumerate(self.SCREENS):
            label = f"  {name}  "
            tw = self.f_tab.size(label)[0]
            if i == self.tab:
                pygame.draw.rect(s, GOLD, (x, 100, tw, 46), border_radius=10)
                s.blit(self.f_tab.render(label, True, INK), (x, 108))
            else:
                pygame.draw.rect(s, DIM, (x, 100, tw, 46), 2, border_radius=10)
                s.blit(self.f_tab.render(label, True, DIM), (x, 108))
            x += tw + 18
        # live banner
        if self.banner and time.time() < self.banner_until:
            bw = self.f_head.size(self.banner)[0] + 56
            pygame.draw.rect(s, GOLD, (W - bw - 36, 96, bw, 52), border_radius=12)
            s.blit(self.f_head.render(self.banner, True, INK), (W - bw - 8, 106))
        if self.tab == 0:
            self.draw_log()
        elif self.tab == 1:
            self.draw_chat()
        elif self.tab == 2:
            self.draw_signals()
        elif self.tab == 3:
            self.draw_logs()
        else:
            self.draw_aboard()
        # footer — controls live here, never overlapping content
        pygame.draw.rect(s, INK2, (0, H - 46, W, 46))
        if self.tab == 1:
            hint = "A start talking · A again to send · B back — Tree answers on the bridge"
        else:
            hint = "D-pad move · A check off · B latest · L1/R1 screens · Menu quit"
        s.blit(self.f_small.render(hint, True, DIM), (36, H - 34))
        pygame.display.flip()

    def draw_chat(self) -> None:
        s = self.screen
        s.blit(self.f_small.render("The bridge, as a conversation. Talk to your Muse — Tree — from the Deck.", True, DIM), (36, 160))
        # conversation — newest always visible: keep the suffix that fits
        convo = list(reversed(self.signals))
        area_top, area_bottom = 196, H - 210
        sized = []
        for sig in convo:
            lines = wrap(self.f_row, str(sig.get("text", ""))[:240], 760)
            sized.append((sig, lines, 44 + len(lines) * 38))
        keep, total = [], 0
        for item in reversed(sized):
            if total + item[2] + 12 > area_bottom - area_top and keep:
                break
            keep.append(item)
            total += item[2] + 12
        keep.reverse()
        y = area_top
        for sig, lines, bh in keep:
            frm = str(sig.get("from", "?"))
            mine = frm.startswith("Rene")
            bx = W - 36 - 820 if mine else 36
            pygame.draw.rect(s, (24, 44, 66) if mine else ROW_BG, (bx, y, 820, bh), border_radius=14)
            s.blit(self.f_small.render(frm, True, GOLD if mine else TEAL), (bx + 20, y + 8))
            ty = y + 36
            for ln in lines:
                s.blit(self.f_row.render(ln, True, PAPER), (bx + 20, ty))
                ty += 38
            y += bh + 12
        # the big talk button
        recording = self.rec_proc is not None
        by = H - 196
        if recording:
            pulse = int(time.time() * 2) % 2 == 0
            col = (178, 44, 44) if pulse else (140, 32, 32)
            label = f"● RECORDING {int(time.time() - self.rec_start)}s — press A to send"
        elif self.transcribing:
            col = TEAL
            label = "✍  TRANSCRIBING ON THE DECK…"
        else:
            col = GOLD
            label = "🎤  PRESS A AND TALK TO TREE"
        pygame.draw.rect(s, col, (36, by, W - 72, 118), border_radius=20)
        tw = self.f_title.size(label)[0]
        s.blit(self.f_title.render(label, True, INK if not recording else PAPER), ((W - tw) // 2, by + 32))

    def draw_aboard(self) -> None:
        s = self.screen
        n_logs = len(self.logs)
        first = self.logs[-1].name[9:17] if self.logs else "—"
        last = self.logs[0].name[9:17] if self.logs else "—"
        size_kb = 0
        try:
            size_kb = sum(p.stat().st_size for p in LOGS_DIR.rglob("*") if p.is_file()) // 1024
        except Exception:
            pass
        lines = [
            ("First Mate is an agent that lives aboard a persistent machine.", PAPER),
            ("", PAPER),
            (f"Memory held aboard: {n_logs} Ship Logs ({first} → {last}), {size_kb} KB, on disk.", PAPER),
            ("It survives reboots. The service restarts itself. Nothing lives in a tab.", PAPER),
            ("", PAPER),
            ("Built for Boat — persistent VMs where agents live and keep working.", GOLD),
            ("Demo runs on this Steam Deck: the same shape, one machine that never forgets.", PAPER),
            ("", PAPER),
            ("The agent contract is public aboard: /llms.txt and /agent.json.", TEAL),
            ("Zero dependencies. $0.00 to run locally. Limits are printed, not hidden.", TEAL),
        ]
        y = 190
        for text, col in lines:
            if text:
                for ln in wrap(self.f_row, text, W - 120):
                    s.blit(self.f_row.render(ln, True, col), (36, y))
                    y += 42
            y += 14
        self._rects = []

    def draw_rows(self, rows: list[tuple[str, str, bool]], y0: int = 196) -> list[tuple[int, int, int]]:
        """rows: (main, sub, struck). Windowed so the selection is always
        visible. Returns click rects (y, h, index)."""
        s = self.screen
        y_bottom = H - 62
        # precompute heights
        heights = []
        for (main, sub, _st) in rows:
            lines = wrap(self.f_row, main, W - 190)
            heights.append(30 + len(lines) * 40 + (30 if sub else 12))
        win = getattr(self, "_win", 0)
        if self.sel < win:
            win = self.sel
        # advance window until sel fits
        while True:
            y = y0
            fits = True
            for i in range(win, len(rows)):
                if i == self.sel and y + heights[i] > y_bottom:
                    fits = False
                y += heights[i] + 12
                if y > y_bottom and i < self.sel:
                    fits = False
            if fits or win >= self.sel:
                break
            win += 1
        self._win = win
        if win > 0:
            s.blit(self.f_small.render("▲ more above", True, GOLD), (W - 190, y0 - 26))
        rects = []
        y = y0
        for i in range(win, len(rows)):
            main, sub, struck = rows[i]
            rh = heights[i]
            if y + rh > y_bottom:
                s.blit(self.f_small.render("▼ more below", True, GOLD), (W - 190, y_bottom + 4))
                break
            bg = ROW_SEL if i == self.sel else ROW_BG
            pygame.draw.rect(s, bg, (36, y, W - 72, rh), border_radius=12)
            if i == self.sel:
                pygame.draw.rect(s, GOLD, (36, y, W - 72, rh), 3, border_radius=12)
            ty = y + 16
            for ln in wrap(self.f_row, main, W - 190):
                col = DIM if struck else PAPER
                s.blit(self.f_row.render(ln, True, col), (118, ty))
                if struck:
                    pygame.draw.line(s, GOLD, (118, ty + 20), (118 + self.f_row.size(ln)[0], ty + 20), 3)
                ty += 40
            if sub:
                s.blit(self.f_small.render(sub, True, TEAL), (118, ty + 2))
            rects.append((y, rh, i))
            y += rh + 12
        return rects

    def draw_log(self) -> None:
        s = self.screen
        if not self.log_data:
            s.blit(self.f_title.render("No Ship Logs yet", True, PAPER), (36, 200))
            s.blit(self.f_row.render("File a report from the phone — it lands here.", True, DIM), (36, 270))
            self._rects = []
            return
        d = self.log_data
        n_done = sum(1 for x in d["done"] if x)
        meta = f"{d['source']}  ·  {len(d['decisions'])} decided  ·  {len(d['links'])} links"
        while self.f_small.size(meta)[0] > W - 420 and len(meta) > 20:
            meta = meta[:-4]
        if self.f_small.size(meta)[0] > W - 420:
            meta = meta[:60] + "…"
        s.blit(self.f_small.render(meta, True, DIM), (36, 160))
        # progress — the log visibly fills as work is checked off
        total = max(1, len(d["actions"]))
        label = f"{n_done} of {len(d['actions'])} done"
        s.blit(self.f_small.render(label, True, GOLD), (W - 36 - self.f_small.size(label)[0], 160))
        pygame.draw.rect(s, ROW_BG, (36, 186, W - 72, 10), border_radius=5)
        if n_done:
            pygame.draw.rect(s, GOLD, (36, 186, int((W - 72) * n_done / total), 10), border_radius=5)
        rows = []
        for i, a in enumerate(d["actions"]):
            box = "☑ " if d["done"][i] else "☐ "
            rows.append((box + a, "", d["done"][i]))
        for dec in d["decisions"]:
            rows.append(("⚓ " + dec, "decided", False))
        self._rects = self.draw_rows(rows, y0=212)

    def draw_signals(self) -> None:
        s = self.screen
        if not self.signals:
            s.blit(self.f_title.render("No signals yet", True, PAPER), (36, 190))
            s.blit(self.f_row.render("Muse and the fleet leave signals on the bridge — they land here.", True, DIM), (36, 260))
            self._rects = []
            return
        rows = []
        for sig in self.signals:
            main = str(sig.get("text", ""))[:300]
            sub = f"{sig.get('from','?')} → {sig.get('to','all')} · {str(sig.get('ts',''))[11:16]} UTC"
            rows.append((main, sub, False))
        self._rects = self.draw_rows(rows)

    def draw_logs(self) -> None:
        rows = []
        for p in self.logs:
            d = read_log(p)
            rows.append((f"{d['source']}"[:90], f"{len(d['actions'])} actions · {p.name}", False))
        self._rects = self.draw_rows(rows)

    # ----- main loop -----
    def run(self) -> None:
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_DOWN,):
                        self.move(1)
                    elif ev.key == pygame.K_UP:
                        self.move(-1)
                    elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.activate()
                    elif ev.key == pygame.K_ESCAPE:
                        self.back()
                    elif ev.key == pygame.K_TAB:
                        self.switch(1)
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    for (y, h, i) in getattr(self, "_rects", []):
                        if y <= ev.pos[1] <= y + h:
                            self.sel = i
                            self.activate()
                            break
                elif ev.type == pygame.JOYHATMOTION:
                    log_input(f"hat {ev.value}")
                    if ev.value[1] == 1:
                        self.move(-1)
                    elif ev.value[1] == -1:
                        self.move(1)
                elif ev.type == pygame.JOYBUTTONDOWN:
                    log_input(f"button {ev.button}")
                    if ev.button == 0:  # A
                        self.activate()
                    elif ev.button == 1:  # B
                        self.back()
                    elif ev.button == 4:  # L1
                        self.switch(-1)
                    elif ev.button == 5:  # R1
                        self.switch(1)
                    elif ev.button in (7, 9):  # menu / options
                        running = False
                    elif ev.button in (13,):  # dpad down on some mappings
                        self.move(1)
                    elif ev.button in (12,):  # dpad up
                        self.move(-1)
                    elif ev.button in (14,):  # dpad left
                        self.switch(-1)
                    elif ev.button in (15,):  # dpad right
                        self.switch(1)
                elif ev.type == pygame.JOYAXISMOTION and ev.axis in (1,):
                    now = time.time()
                    if now > self.stick_cool:
                        if ev.value > 0.55:
                            self.move(1)
                            self.stick_cool = now + 0.24
                        elif ev.value < -0.55:
                            self.move(-1)
                            self.stick_cool = now + 0.24
            self.reload()
            self.draw()
            self.clock.tick(30)
        log_input("app exit")
        pygame.quit()


if __name__ == "__main__":
    App().run()
