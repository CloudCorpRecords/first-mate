# BUILD REPORT — First Mate, Deck Edition

Built: Sat 2026-11-21 (VM, America/Los_Angeles morning) for Boat Hackathon
Demo Day, today 1–5pm PT, Pier 9.
Location: `~/workspace/goals/boat-hackathon-nov-14-21/files/first-mate-deck/`
Source (unmodified): `../first-mate/`

## Files created / copied

Copied verbatim from source (engine untouched — see verification below):
- `first_mate/` — all 10 original `.py` modules, byte-identical
- `sample/` — 4 sample chats + saved outputs
- `tests/test_first_mate.py`, `README.md`, `LICENSE`, `SAMPLE-OUTPUT.md`, `logo.png`
- `data/ship-logs/` — empty, ready for on-device saves

New files (Deck Edition only):
- `first_mate/deck_server.py` — NEW Deck UI server (stdlib only). Routes:
  `GET /` (home), `GET /sample/<slug>` (one-tap run), `POST /ship-log`
  (paste), `GET /logs` (sync list), `GET /logs/<file>` (view one log,
  basename-only, traversal returns 404), `GET /status` (real connectivity
  check), `GET /health` (engine health). Binds 0.0.0.0, port from
  `FIRST_MATE_PORT` (default 8000, via engine config).
- `deck.py` — standalone entry: `python3 deck.py`
- `launch.sh` — starts server, waits for `/health`, `xdg-open
  http://localhost:8000`. Plain bash, no deps. Executable.
- `README-DECK.md` — what it is, Deck launch (Desktop Mode → launch.sh,
  non-Steam game later), online/offline honesty, limits.
- `BUILD-REPORT.md` — this file.

UI specifics: dark nautical theme (#071a2e / gold / teal), designed for
1280×800, body text 20px minimum, sample buttons 26px / min-height 110px,
persistent status header (mode pill + privacy + "Steam Deck (on-device)"
+ Home/Saved Logs links) on every page, all controls are real links/
buttons — focusable, Enter/Space activates, thick gold `:focus` outline,
sensible tab order. No typing required for the demo path.

## Engine-untouched verification

`cmp` on every original module, source vs deck copy — all IDENTICAL:
`__init__.py, __main__.py, accesses.py, cli.py, config.py, context_dev.py,
inference.py, server.py, ship_log.py, transcript.py`.
Only addition inside the package is the new `deck_server.py`.

## Test results (actual output)

Copied suite, run in the deck folder:
```
$ python3 -m unittest discover -s tests -v
Ran 32 tests in 33.649s
OK
```

## Smoke test (actual output, VM, port 8123/8124)

Server: `FIRST_MATE_PORT=8123 python3 deck.py`
- `GET /` → `HTTP 200, 4389 bytes` — contains all four sample buttons
  (Demo Chat, Startup Product Team, Event Crew, Open Source Team),
  "Steam Deck (on-device)", and the OFFLINE pill (see limits).
- `GET /sample/sample-chat` → `HTTP 200, 10142 bytes` — page contains
  "Ship Log" (×22), "All accesses" (×2), "What to do next",
  "Privacy mode: Local only". Saved log + meta archived to
  `data/ship-logs/` (e.g. `ship-log-20261121-190059-1e9d5d8b.md`).
- Other samples: `startup-product-team`, `event-crew`,
  `open-source-team` → each `HTTP 200`, All Accesses present.
- `GET /status` → `HTTP 200`:
  `{"online": false, "mode": "OFFLINE", "detail": "Could not reach
  https://boat.dev/: URLError", "privacy_mode": "Local only",
  "hosting": "Steam Deck (on-device)", "link_reading": "Direct fetch
  (when online); Not fetched when offline", "port": 8123}`
- `GET /health` → `HTTP 200`, `{"status": "ok", "app": "first-mate",
  "version": "0.2.0", "privacy_mode": "Local only",
  "data_dir_writable": true, ...}`
- `GET /logs` → `HTTP 200` — lists the saved ship-log files; 
  `GET /logs/<file>` → `HTTP 200`; traversal `GET /logs/../deck.py` →
  `HTTP 404`; unknown sample → `HTTP 404`.
- `POST /ship-log` (pasted chat) → `HTTP 200`, Ship Log rendered and
  saved; empty paste → `HTTP 400`.

Smoke artifacts were cleaned afterwards, so the deploy copy ships with
an empty `data/ship-logs/`.

## Limits / honest notes

- **VM sandbox has no direct outbound web fetch**, so `/status`
  correctly reported OFFLINE here and sample links were labelled
  `Not fetched` by the engine — the honest path, not a bug. On the Deck
  on Pier 9 WiFi, the same `/status` check (2s timeout to example.com,
  then boat.dev, cached 10s) will report ONLINE and links will use the
  engine's live direct-fetch (or Context.dev only if a key is set).
- No Context.dev / NYTE / Boat VM use is claimed: default run is
  Local only, and every Ship Log's All Accesses panel says exactly
  what was and was not used.
- No login/accounts on the UI — Deck / private demo network only.
- **Not yet done (parent step): deploy to the Steam Deck and
  cold-launch verification on the real device.** Nothing here claims
  that has happened.

## Phone + Watch (added 2026-11-21, later the same morning)

New surfaces in `first_mate/deck_server.py` (engine still untouched),
all reading/writing the SAME server + `data/ship-logs/` store:

- **Phone PWA:** `GET /phone` (max-width 480px layout, status pill,
  one-tap samples via `/sample/<slug>?ui=phone`, paste form via
  `POST /ship-log?ui=phone`, saved-logs list with phone-styled viewer
  via `/logs/<file>?ui=phone`, phone-styled result pages, "Synced with
  Steam Deck — same Ship Logs everywhere" stated where the shared
  store is actually read). `GET /manifest.webmanifest`,
  `GET /sw.js` (caches shell `/`, `/phone`, manifest, icons only;
  `/status`, `/logs`, `/sample`, `/ship-log`, `/watch`, `/api/latest`
  are network-only), `GET /icon-192.png` + `/icon-512.png`
  (generated from `logo.png` with PIL, composited on navy #071a2e,
  committed as files; code falls back to serving `logo.png`).
  Manifest link + theme-color + apple-touch-icon + SW registration
  are on `/phone` and on the Deck shell (`/`).
- **Watch companion:** `GET /watch` (~400px, black bg, 28px+ text,
  meta-refresh 30s) showing the newest log in the shared store:
  date, top-5 "What to do next" checklist, decision/link/action
  counts, "🔄 Synced • <time>" line; empty store → "No Ship Logs
  yet — run one on Deck or phone." `GET /api/latest` returns the
  same summary as JSON. Deck home gained 📱 Phone / ⌚ Watch links.

Verification (VM, server on port 8125, actual output):

- `GET /phone` → `200, 3964B`; contains manifest link, SW
  registration, the sync line, and all 4 sample links with
  `?ui=phone`.
- `GET /manifest.webmanifest` → `200`; JSON validated:
  `First Mate | First Mate | standalone | #071a2e | ['/icon-192.png', '/icon-512.png']`.
- `GET /sw.js` → `200`, contains the never-cache list incl.
  `/api/latest`.
- `GET /icon-192.png` → `200 image/png 25814B` (`PNG image data,
  192 x 192`); `/icon-512.png` → `200 image/png 22168B` (`512 x 512`).
- Empty store: `GET /watch` → "No Ship Logs yet — run one on Deck
  or phone."; `GET /api/latest` →
  `{"latest": null, "message": "No Ship Logs yet — run one on Deck or phone."}`.
- Phone run `GET /sample/event-crew?ui=phone` → `200, 9248B`,
  phone layout, All Accesses present, log saved. Then:
  - `GET /api/latest` → that same run:
    `file: ship-log-20261121-191215-1686f41f.md`,
    `counts: {actions: 6, decisions: 4, links: 1, messages: 15}`,
    `actions_top5[0]: "Marcus: I will bring the printed badges and the lanyards by tomorrow"`.
  - `GET /watch` → shows the same top-5 actions as ☐ checklist
    items, `✅ 4 decided · 🔗 1 links · 📋 6 to do`,
    `Synced • 19:12:19`, meta-refresh 30 present.
  - `GET /logs/<file>?ui=phone` → `200`, phone layout.
  - `POST /ship-log?ui=phone` (pasted 3-message chat) → `200`
    phone-styled result; `/api/latest` then pointed at the new run
    (`ship-log-20261121-191240-11740a85.md`) — newest-run sync
    across surfaces confirmed.
- Existing routes unbroken: `/`, `/health`, `/status`, `/logs` →
  `200`; Deck home contains `href="/phone"` and `href="/watch"`;
  traversal → `404`; unknown path → `404`.
- Test suite after the change: `Ran 32 tests in 33.661s — OK`.
- Smoke artifacts cleaned: `data/ship-logs/` ships empty (0 files).

Limits: watch surface is a web companion (Samsung Internet on the
watch, same WiFi) — no native Wear OS APK is claimed. VM sandbox has
no outbound fetch, so runs here were OFFLINE / Local only as before;
nothing about Context.dev / NYTE / Boat VM use is claimed.

## v2 — "No typing on the Deck" (2026-11-21, later same morning)

New in `first_mate/deck_server.py` (engine still untouched) +
`first_mate/qrmini.py` (new) + `inbox/` (new):

- **QR pairing:** `GET /qr.png` → PNG QR encoding
  `http://<deck-lan-ip>:<port>/phone` (LAN IP via UDP-connect trick,
  fallback 127.0.0.1). QR generated by `qrmini.py` — a vendored
  single-file copy of **qrcodegen 1.8.0 by Project Nayuki (MIT)**,
  downloaded as a wheel from PyPI and copied in with attribution, so
  the Deck needs no pip. PNG written with a stdlib zlib/struct
  encoder. (segno was also downloaded and used as a cross-check
  oracle during development, but it is a multi-module package, so
  the single-file Nayuki module is what shipped.)
- **Deck home (`/`):** pairing panel at top (QR image + phone URL in
  big text + "Scan → paste your chat on your phone → it lands
  here.") and a **live panel** polling `/api/latest` every 5s:
  newest run's actions + decisions rendered with DOM textContent,
  gold flash animation when `run_id` changes, tap an action to
  check it off.
- **`POST /api/ship-log`:** JSON `{chat, source}` → build + save,
  returns `{run_id, file, counts, actions, decisions, done, source}`.
- **Check-off sync:** `POST /api/actions/done` with `{index}` or
  `{run_id, index}` toggles done state, persisted in a
  `<log>-done.json` sidecar in `data/ship-logs/`. `GET /api/latest`
  now includes `"decisions"` and `"done": [...]`. Deck live panel,
  `/phone` (new "Latest Ship Log — tap to check off" block) and
  `/watch` (tap-to-toggle, ✅ + strikethrough) all render it.
- **Inbox auto-import:** daemon thread sweeps `inbox/` every 3s;
  new `.txt` → Ship Log with source `Inbox drop: <filename>`, file
  moved to `inbox/processed/`. `inbox/README.txt` documents it.
- SW cache bumped to `first-mate-v2`; `/api/*` and `/qr.png` added
  to the never-cache list.

Verification (VM, server on port 8126, actual output):

- **QR verified by decoding, not just structure:** `GET /qr.png` →
  `200, 986 bytes`, PNG magic bytes OK. The served PNG was decoded
  with **OpenCV's QRCodeDetector** (installed into a throwaway
  /tmp target, not the project): `DECODED: 'http://198.19.0.2:8126/phone'`
  — exactly the VM's LAN IP + test port + `/phone` that the server
  encoded. Points found: True.
- `POST /api/ship-log` (sample chat, source "Phone (smoke test)") →
  `200`, `run_id: 20261121-192558-f4fc535e`,
  `counts: {messages: 12, links: 3, decisions: 4, actions: 4, ...}`,
  `done: [False, False, False, False]`, log + meta + done sidecar
  saved in `data/ship-logs/`.
- Empty chat → `400 {"error": "Paste some chat text first (field: chat)."}`;
  non-JSON body → `400` JSON error.
- `GET /api/latest` → same run, `done` present.
- `POST /api/actions/done {"index": 0}` → `200`,
  `done: [True, False, False, False]`; `/api/latest` reflected it;
  `{"run_id": ..., "index": 0}` toggled it back to all-False.
  Index 99 → `400` out of range; unknown run_id → `404`.
- **Inbox:** copied `sample/event-crew-chat.txt` to
  `inbox/judges-crew-chat.txt` → within one sweep it was imported
  (`/api/latest` source: `Inbox drop: judges-crew-chat.txt`,
  counts 6 actions / 4 decisions / 1 link) and the file moved to
  `inbox/processed/judges-crew-chat.txt`.
- **Surfaces render done state:** after toggling action 0,
  `GET /watch` contained `class="done" ... ✅ Marcus: I will bring
  the printed badges…` and `GET /phone` contained
  `actrow doneact ... ✅ Marcus: ...`. Deck home contains the
  `/qr.png` panel, the pairing line, the phone URL, and the live
  panel markup + polling script.
- Existing routes all still `200`: `/`, `/phone`, `/watch`,
  `/logs`, `/status`, `/health`, `/manifest.webmanifest`, `/sw.js`,
  both icons, `/qr.png`, `/sample/sample-chat`,
  `/sample/event-crew?ui=phone`.
- Test suite: `Ran 32 tests in 33.638s — OK`.
- Smoke artifacts cleaned: server stopped, `data/ship-logs/`
  emptied, `inbox/processed/` emptied, `inbox/` keeps only
  `README.txt` (+ empty `processed/`), and the `ship-log.md` /
  `ship-log.html` / `ship-log-meta.json` files that `save_ship_log`
  writes into the CWD during smoke runs were removed from the
  project root.

Limits (unchanged honesty): VM sandbox has no outbound fetch, so
runs here show links `Not fetched` / OFFLINE exactly as the engine
reports; on Deck WiFi the same QR flow works with live link reads.
QR payload uses the Deck's current LAN IP — if the Deck changes
networks, restart the server (or just reload home) so `/qr.png`
re-detects the IP.


## Design v3 — premium restyle (2026-11-21, Demo Day)

A full visual redesign of every surface, all inside
`first_mate/deck_server.py` (CSS/HTML/JS strings only — engine modules
untouched, every route and behaviour preserved). Direction: refined,
minimal, editorial — "sleek like a European founder would ship."

Design system (shared tokens across Deck + phone):
- Palette: deep ink navy gradient `#060d18 → #0a1626`, warm off-white
  text `#f4f1ea`, one restrained gold accent `#d9a441`, muted teal
  `#5ea8a0` secondary. Hairline 1px borders at 10% white, glass cards
  (3% white + inset highlight), generous whitespace, `color-scheme: dark`.
- Type: Georgia / "Iowan Old Style" serif for display headings (64px
  hero wordmark, italic serif tagline), "Avenir Next" / "Segoe UI" /
  system-ui for body, letter-spaced small-caps gold kickers as section
  labels. Body stays ≥20px on Deck; tap targets unchanged (112px cards).
- Header: slim translucent bar with backdrop blur, serif brand, quiet
  outlined ONLINE/OFFLINE pills (teal / muted rust, no more traffic
  lights).

Motion (all CSS/JS inline, zero external assets, offline-safe):
- Staggered fade-and-rise entrance for page sections (0.07s steps).
- A very subtle ambient gradient drift (30s alternate) plus the hero
  ship's-wheel logo rotating at 80s/rev and an SVG wheel watermark at
  5% opacity counter-rotating at 110s — barely-there, not playful.
- Cards lift 3px with a soft shadow and gold edge on hover; a gold
  arrow slides in on sample cards; nav became outline pills that fill
  gold on hover.
- Live panel: a new Ship Log now arrives with a soft 2.4s gold-glow
  settle (was a full-panel colour flash); list items stagger in. The
  home poller now keeps a render signature (run_id + done flags +
  counts) and skips DOM rebuilds when nothing changed, so animations
  fire only on real changes — including check-offs.
- Check-off: the strike-through is a gold line that *draws itself*
  across the action (background-size keyframe) while the row dims.
- `prefers-reduced-motion` disables all of it.

Composition changes:
- Deck home: hero row (wheel logo, "First Mate" serif wordmark,
  tagline), then the pairing panel as a clean white card (QR stays on
  white — scannability — with dark ink text and a gold-underlined URL),
  live Ship Log as a glass card, samples as a refined 2×2 serif card
  grid, paste form demoted to a quiet "Last resort" section.
- Result page, saved-logs list and log view, phone home/result/log
  views: same tokens, serif headings, glass panels, outline-pill nav.
- Watch web view: unchanged layout (black, huge, simple); palette
  aligned to the gold/teal tokens.
- PWA: service-worker cache bumped `first-mate-v2 → first-mate-v3`;
  manifest + theme-color moved to `#060d18`.

Verification (this run):
- `python3 -m unittest discover -s tests` → **Ran 32 tests — OK**.
- Live server sweep: every route 200 (`/`, `/phone`, `/watch`,
  `/logs`, `/logs/<file>`, `/status`, `/health`, `/qr.png`,
  `/api/latest`, `/manifest.webmanifest`, `/sw.js`, both icons,
  `/sample/<slug>` ×2), bad log name → 404, and POST `/ship-log`,
  POST `/api/ship-log`, POST `/api/actions/done` all 200 with the
  latest-log JSON reflecting the toggle.
- Screenshots: **not possible in this VM** — the only browser binary
  (`/opt/meta-chromium/chrome`, a managed Hatch CVM build) refuses
  shell-launched headless runs ("Hatch WebGL domain policy is required
  for browser startup", with and without SwiftShader flags), and no
  other renderer (Firefox/wkhtmltoimage/Playwright/WeasyPrint) is
  installed. Verified instead by full HTML dumps of home, phone,
  result and watch pages (saved in `~/workspace/first-mate-deck-design/`)
  plus a CSS review pass that caught and fixed two real bugs before
  shipping: (1) `.livebox li` out-specified `.doneact`, which would
  have killed the strike-draw animation — added a
  `.livebox li.doneact` rule; (2) the hero wheel watermark could bleed
  10px past a 1280px viewport — hero now clips it as a design bleed.
  Contrast checked numerically: gold on ink ≈ 7.5:1, dim text ≈ 6.4:1,
  pair-card body text ≈ 7:1. Parent should still eyeball the home
  page once on the real Deck after deploy.
- Smoke data cleaned: `data/ship-logs/` empty, root `ship-log.*`
  removed, inbox untouched.

## Anicet pass — agent-readable + provable facts (2026-11-21)

Goal: surface the traits Boat's CEO demonstrably values, using ONLY
facts the app can prove about itself. All changes inside
`first_mate/deck_server.py`; engine untouched.

Added:
- `GET /llms.txt` — text/plain agent contract: 3-line what-it-is, the
  machine contract (POST /api/ship-log, GET /api/latest,
  POST /api/actions/done, GET /status, GET /health), persistence facts
  (data/ship-logs archive, survives restarts), privacy facts (Local
  only = nothing leaves the machine), cost ($0.00 local run, no keys,
  no account), limits stated plainly (extractive local summaries, no
  accounts/login, one-page link reads, offline links "Not fetched").
- `GET /agent.json` — JSON manifest: name, version (0.2.0, from the
  engine package), description, endpoints map with methods/bodies,
  surfaces (deck/phone/watch), persistence, privacy_modes, cost,
  dependencies "none (Python standard library only)".
- Deck home "UNDER THE HOOD" panel (v3 design tokens, after the live
  panel): four live-computed fact rows — Persistent (real archive
  count + oldest/newest from data/ship-logs; "archive starts with your
  first run" when empty), Agent-native (with a working curl one-liner
  for POST /api/ship-log in a mono block), Cost of a local run $0.00,
  Zero dependencies + plain limits. Footer gained machine-readable
  links: /llms.txt · /agent.json · /logs.
- Result pages (Deck + phone): one quiet footer line under the Ship
  Log — mode read from the run's own metadata, so "Local only" is
  claimed only when that run actually was.
- README-DECK.md: "Design principles" section mapping each principle
  (product speaks for itself, agent-readable by default, persistent
  state, honest limits) to the feature that proves it.

Verification (local server, port 8933, actual outputs):
- `/llms.txt` → HTTP 200, `Content-Type: text/plain; charset=utf-8`;
  body contains all five contract endpoints.
- `/agent.json` → valid JSON: `First Mate 0.2.0 | deps: none (Python
  standard library only) | endpoints: 9`.
- Sample run (event-crew) → result page 200 with footer:
  `Run cost $0.00 · Local only · Zero-dependency engine · Full record in All Accesses ↓`
  Phone result page (`?ui=phone`) shows the identical line.
- Home panel vs disk after that run: page said
  `1 Ship Log archived on this device — oldest 2026-11-21 19:50 UTC, newest 2026-11-21 19:50 UTC.`
  and `ls data/ship-logs/ship-log-*.md | wc -l` returned `1` — match.
- Route sweep all 200: `/ /phone /watch /logs /status /health /qr.png
  /api/latest /llms.txt /agent.json /manifest.webmanifest /sw.js
  /icon-192.png`; `POST /api/ship-log` 200; `POST /api/actions/done` 200.
- Test suite: `Ran 32 tests in 32.789s — OK`.
- Smoke data cleaned: `data/ship-logs/` empty, root `ship-log.*`
  removed, inbox untouched.

## Deck Mode v4 (2026-11-21, ~12:05–12:20 PT) — controller-first rebuild + Boat-native framing

Field report that drove it (Rene, photos, real Deck in Gaming Mode):
stale pre-v2 home served by the v3 service worker (cache-first '/'),
buttons unreachable without gamepad nav, paste-first home on a device
where pasting is effectively impossible, a bare-text 400 on empty
POST, and a raw-markdown <pre> result page. All changes in
`first_mate/deck_server.py` + `sample/agent-fleet-chat.txt`; engine
untouched; all API routes preserved.

Built:
- SW `first-mate-v4`: SHELL = manifest + icons only ('/' and '/phone'
  removed); navigations network-only; activate deletes old caches.
  Server sends `Cache-Control: no-store` on all HTML and on /sw.js.
- GAMEPAD_JS injected on Deck pages (home, result, logs, saved log):
  `.foci` elements, spatial nearest scoring (primary + 2.5× cross),
  arrows + Gamepad API poll @100ms (dpad 12–15, stick >0.5 with 220ms
  lockout, A=0 activate, B=1 back, menu=9 home), 4px gold outline +
  scale(1.03) + glow on the focused element, `body.gamepad` hides the
  cursor, padbar hint in the header on every Deck page.
- Deck home: paste form REMOVED (0 <textarea>, 0 <form> served).
  Order: hero → QR pair → live panel (action rows are .foci, A
  toggles via fmToggleDone) → 5 sample tiles (.foci) → Under the Hood
  → "Why a persistent machine" panel → nav.
- Result page (Deck): structured — actions as focusable check-off
  rows (done state read from the saved run's sidecar), decisions,
  links, run-cost footer line, All Accesses in <details>. Zero <pre>.
- Friendly errors: empty/oversized/InputError/unknown-sample/
  missing-log on user routes return styled HTML (empty paste says
  pasting happens on the phone); API JSON errors unchanged.
- 5th sample "Agent Fleet Report": parses to 7 actions, 3 decisions,
  2 links with the stock engine (verified via parse_transcript).
- Boat framing: home panel + /llms.txt "## Deployment" paragraph —
  demo on-device, package targets any persistent VM, Dockerfile +
  deploy guide included, NOT yet run on Boat. No live-Boat claim.

Verification (local server, FIRST_MATE_PORT=8898):
- `GET /` 200 with `Cache-Control: no-store`; textarea 0, form 0;
  getGamepads present; foci ×17; padbar present; Under the Hood 1;
  Why a persistent machine 1; Agent Fleet tile 1.
- `GET /sw.js` 200 + no-store; contains `first-mate-v4`; contains no
  cached `'/'`; navigate network-only branch present.
- `POST /ship-log` (empty, deck + ?ui=phone) → 400 with HTML body
  containing "That chat was empty".
- `GET /sample/agent-fleet` 200: foci ×14, actlist present, <pre> ×0,
  accesses <details> present, "Run cost $0.00" line present, sections
  What to do next / Decided / Shared links each rendered once.
- Route sweep all 200: / /phone /watch /logs /status /health
  /llms.txt /agent.json /manifest.webmanifest /sw.js /qr.png
  /icon-192.png /api/latest /sample/sample-chat /sample/event-crew;
  `POST /api/actions/done` 200 {"ok": true, ...}.
- Test suite: `32 passed` (pytest, 36.84s).
- Smoke data cleaned: `data/ship-logs/` empty.

## Agent Pack (2026-11-21, ~12:05 PT)

Productization layer added in `agent-pack/` — docs/package only, no
server code touched, no Xod involvement (per Rene's explicit call):

- `agent-pack/AGENT.md` — the First Mate agent charter, written to the
  operating agent: role (keeper of the Ship Log, memory of the
  operation), the reasoning (fleet scatter → one honest digest, living
  on a persistent machine), the working contract (/llms.txt first,
  POST /api/ship-log, GET /api/latest, POST /api/actions/done, inbox
  .txt import, data/ship-logs as append-only memory), the honesty
  constitution (All Accesses complete, no unlive integrations claimed,
  limits stated first, numbers only if measured, no overselling), the
  research-derived design principles each with its operational
  consequence, voice rules, and stated limits.
- `agent-pack/INSTALL.md` — the 3-step drop-in (copy folder, run
  server on 8899, point agent at AGENT.md + /llms.txt), Deck shortcut
  and always-on notes, the Boat persistent-VM path via the sibling
  package's Dockerfile + deploy/boat.md, labelled plainly as
  packaged-and-documented, not yet run live on a Boat VM; optional
  key routes described as off by default.
- `agent-pack/FLEET-REPORT-FORMAT.md` — the real-data contract that
  replaces samples: exact `Name: text` line format with the parser's
  actual decision/action marker words, link rules, and per-report
  limits; one real-shaped fleet morning-report example (no invented
  metrics); how a human reads the result on Deck / phone / watch / the
  saved Markdown file; an agent filing checklist.

Verification: the format doc's example was run through the real
parser (`first_mate.transcript.parse_transcript`) — output: 6
actions, 3 decisions, 2 links, 6 notes. The doc's stated counts were
corrected to match the parser exactly (the blocker line files as an
action because it names the unblocking work).

## Bridge (2026-11-21)

The Bridge: a signal channel between Muse, the fleet and the surfaces,
with First Mate's persistent store as the shared space. The Ship Log is
the digest; the Bridge is the live wire.

- Store: append-only `data/bridge.jsonl` beside the ship-logs store
  (resolved from the same config data_dir as the logs). Line schema:
  {"ts": ISO UTC, "from": str, "to": str, "text": str}; text capped at
  500 chars, from/to at 60; writes guarded by a dedicated lock.
- POST /api/bridge {from, to?, text} -> {ok: true, count: <total>};
  missing/empty from or text -> 400 JSON. `to` defaults to "all".
- GET /api/bridge -> {signals: [latest 20, newest first]}.
- Deck home: "Signals — The Bridge / The shared space" panel after the
  live Ship Log panel, server-rendered + JS poll of /api/bridge every
  5s, re-render only on change. Signal rows are display-only (no .foci).
  Honest line included: local network only, no auth yet.
- /llms.txt contract + /agent.json manifest gained both bridge
  endpoints, including the purpose line: "The bridge is how Muse
  reaches the fleet and the fleet reaches back — this store is the
  shared space."
- Phone home: server-rendered "Signals — the Bridge" block, latest 5.
- agent-pack/AGENT.md gained a "## The bridge" section: check the
  bridge on wake, file signals for what Muse/the human must see,
  signals are not the log — the Ship Log remains the record.

Verification (local server, port 8899):
- POST {"from":"Muse","to":"fleet","text":"Bridge is live..."} ->
  {"ok": true, "count": 1}; line on disk in data/bridge.jsonl matches
  the schema. POST without "to" -> stored as "all". POST with empty
  text -> 400.
- GET /api/bridge after a second POST returned newest first:
  ['Watch', 'Muse'].
- Home HTML contains the bridge panel (id=bridgelist, fmBridgePoll);
  /llms.txt contains /api/bridge (contract + persistence note);
  /agent.json contains both bridge endpoints; /phone shows the posted
  signal server-rendered.
- Route sweep: 16/16 routes 200 (/, /phone, /watch, /logs, /status,
  /health, /llms.txt, /agent.json, /api/latest, /api/bridge, /sw.js,
  /manifest.webmanifest, /qr.png, /icon-192.png, /sample/event-crew,
  /sample/agent-fleet); POST /api/actions/done still 200 {"ok": true}.
- Tests: 32 passed (pytest, 33.8s).
- Cleanup: all smoke signals and smoke Ship Logs removed —
  data/bridge.jsonl absent, data/ship-logs/ empty. Ships clean; the
  first real signal is Muse's to post live.
