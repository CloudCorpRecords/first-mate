# First Mate

![First Mate logo](logo.png)

Disclosure: First Mate was built by AI agents directed by Rene Turcios for the Boat Hackathon.

We are building a helper that sits in a team chat.
It reads what the team shares and makes a simple list of what to do next, and it keeps it private.

## What it does

Paste a team chat in, get a Ship Log out. The Ship Log lists:

- What to do next, as a checklist
- What the team decided
- The links the team shared, with a short note on each one
- A short summary
- An All accesses section, listing every access the run made, and the ones it did not make, with the reason

Copy the Ship Log back into your team chat to share it. That is the whole product.

No sponsor credits, keys, or codes are needed for any of this. First Mate runs complete on free, no key modes. Keys, if you happen to have them, are optional upgrades only, and nothing in this project waits on them.

## How it uses the four hackathon tools

### 1. Teamily - the team chat

- Input: a Teamily group chat, exported or copied and pasted as plain text.
- Output: the Ship Log is a short markdown message, formatted to paste straight back into the Teamily group.
- Integration point: `first_mate/transcript.py` parses the pasted chat, and the web UI and CLI both end with the Ship Log in that paste-back format. There is no Teamily API key in this prototype, and none is claimed. The paste in, paste back loop is the integration, and it works with any Teamily export today.

### 2. Context.dev - reading links

- Adapter: `first_mate/context_dev.py`
- Default, free mode: with no key, it fetches each page directly and pulls out plain text with a simple HTML to text pass. This is a complete working mode, not a stub.
- Optional upgrade: when `CONTEXT_DEV_API_KEY` is set in `.env`, it calls the Context.dev web scrape API at `api.context.dev` (base URL configurable in `.env`) and asks for markdown for each shared link. If that call fails, it uses direct fetch instead.
- Honest labels: every link in the Ship Log says how it was read, `Context.dev`, `Direct fetch (fallback)`, or `Not fetched`. A failed fetch never stops the Ship Log, the link is kept for the team to open.

### 3. NY Token Exchange / TrustedRouter - private thinking

- Adapter: `first_mate/inference.py`
- Default, free mode: it uses a local extractive summarizer that runs in this process only. No network call is made, so no team content leaves the machine. This is the normal mode, and the demo runs complete in it.
- Optional upgrade: when a key (`NYTE_API_KEY` or `TRUSTEDROUTER_API_KEY`), a base URL, and a model are all set in `.env`, it sends the chat to that route in the common OpenAI compatible chat completions shape, for private inference. The base URL is configurable on purpose. This project does not guess an endpoint and present it as fact.
- Honest labels: every Ship Log says `Privacy mode: Private via NYTE` for that optional route, or `Privacy mode: Local only` for the default local mode.

### 4. Boat.dev - where it lives

- First Mate can run on a persistent Boat.dev VM, so it is always there when the team is working, and its Ship Logs stay on disk. It also runs locally with the same code, and the All accesses panel says which one a given run used.
- Deploy steps: see `deploy/boat.md`. Plain Python steps and a Docker option are both there.
- Persistence: every Ship Log is archived to `data/ship-logs/` (configurable with `FIRST_MATE_DATA_DIR`) in addition to the output files.
- Health: `python3 -m first_mate health` on the command line, or `GET /health` on the web UI.

## All accesses: the website shows everything

Every run collects an access record as it goes, in `first_mate/accesses.py`. It is data collected during the run, not fixed text. The same record appears in three places: the All accesses panel on the web UI result page, the All accesses section in `ship-log.html`, and the Accesses section in `ship-log.md`.

It lists, with the time of the run:

- Teamily chat in: the source of the chat, and how many messages, links, decisions, and actions were read
- Each link access: the URL, the tool used (`Context.dev`, `Direct fetch (fallback)`, or `Not fetched`), and whether it worked or failed
- The AI access: `NY Token Exchange` private route if it was configured and used, otherwise `Local only`, with a clear line that no team data left the machine in local mode
- Boat.dev hosting status: running locally or on a Boat VM, and the health check result
- Ship Log out: where the files were saved, and that the log is formatted for Teamily

It also lists the accesses that were NOT made, and why. For example: `Context.dev: not used, no key, used direct fetch instead`, the NY Token Exchange route not used in local mode, the Teamily API not used (paste in, paste back), and a Boat VM not used when a run was local. A judge looking at the page can verify every sponsor tool was considered, and exactly how each one was used.

## Setup

You need Python 3.10 or newer. There are no packages to install, First Mate uses the standard library only.

```bash
cd first-mate
```

That is the whole setup. An `.env` file is optional. Copy `.env.example` to `.env` only if you already have a key and want an optional upgrade route used instead of the free mode. Every key is blank in `.env.example` on purpose. With no keys at all, First Mate runs in Local only mode with direct fetch for links, and that mode is fully working and complete for the demo.

## Run it

Command line, from a chat transcript file:

```bash
python3 -m first_mate run sample/sample-chat.txt --out out
```

This writes `out/ship-log.md` and `out/ship-log.html`, prints the Ship Log, and archives a copy in `data/ship-logs/`.

Web UI, for a live demo:

```bash
python3 -m first_mate serve
```

Then open http://localhost:8000 in a browser, paste a team chat, and click the button.

Health check:

```bash
python3 -m first_mate health
curl http://localhost:8000/health
```

Docker:

```bash
docker build -t first-mate .
docker run -p 8000:8000 -v first-mate-data:/app/data first-mate
```

## 60 second live demo script

1. (0 to 10s) Say the two lines at the top of this README. Open the web UI. Say: no credits or keys are needed, this runs free.
2. (10 to 30s) Paste the sample chat from `sample/sample-chat.txt`. It has messy notes, three links, decisions, and tasks mixed together. Click "Make my Ship Log".
3. (30 to 45s) Show the Ship Log: a clean checklist of what to do next, the decisions, and the shared links. Point at the line `Privacy mode: Local only`. Say: nothing was sent to a random tool, and every link says how it was read.
4. (45 to 60s) Scroll to the All accesses panel. Show every access the run made, with times, and the accesses it did not make, with the reason for each one, like Context.dev not used because there is no key, with direct fetch used instead. Say: you do not have to trust the pitch, you can check the panel. Close with: copy this back into our Teamily group and the whole crew sees the same plan.

## Tests and verified demo run

Tests, 14 tests, all passing, run 2026-11-14:

```bash
python3 -m unittest discover -s tests -v
# Ran 14 tests, OK
```

The tests cover link extraction, decisions and action items, speaker parsing, the local summarizer, the rule that a key without a base URL is not treated as a configured private route, HTML to text cleanup, honest `Not fetched` labelling, building and saving a Ship Log, and the All accesses record: link accesses are recorded with their tool and result, the AI access is recorded with the correct mode, and accesses that were not made are explained, including Context.dev not used with no key and the NY Token Exchange route not used in local mode.

Verified demo run, 2026-11-14:

```bash
python3 -m first_mate run sample/sample-chat.txt --out out
# Exit 0. Wrote out/ship-log.md and out/ship-log.html.
# Archived data/ship-logs/ship-log-20261114-215023.md
# Result: privacy mode Local only, 3 links, 4 actions, 4 decisions.
# All accesses section included: 7 accesses made, 4 not made and explained.
```

The actual output of that run is saved as `SAMPLE-OUTPUT.md` in this folder, including the new All accesses section.

Web UI smoke test, 2026-11-14: server started on a test port, `GET /health` returned status ok with hosting local, and `POST /ship-log` with the sample chat returned 200 with a Ship Log showing `Privacy mode: Local only` and the All accesses panel on the result page.

Note on the demo run in this sandbox: direct web fetch is not available here, so the three sample links are honestly labelled `Not fetched` in `SAMPLE-OUTPUT.md`, with the links kept in the log, and each link access is listed as Failed in the All accesses section. On a normal network, the same run reads them with direct fetch in the free mode, or with Context.dev if that optional key is set.

## Honest status: free modes are the product

- Working now, no keys and no credits needed, and complete for the demo: chat parsing, decisions and action items, local summary, direct fetch link reading, Ship Log in markdown and HTML with the All accesses record, CLI, web UI with the All accesses panel, health check, on-disk storage, tests, Docker file, Boat VM deploy steps.
- Optional upgrades only, if keys happen to be available: Context.dev link reading instead of direct fetch, and NYTE / TrustedRouter private inference instead of the local summary. Neither is needed, neither is waited on, and neither is claimed as used unless a run actually used it. The All accesses panel shows which happened on each run.
- There are no blockers for the demo. No sponsor codes are assumed to exist.
- Teamily: paste in, paste back integration as described above. No API integration is claimed, and the All accesses record says so.

## Project layout

- `first_mate/transcript.py` - parses a pasted or exported team chat
- `first_mate/context_dev.py` - Context.dev adapter with direct fetch as the free default
- `first_mate/inference.py` - NYTE / TrustedRouter adapter with local summary as the free default
- `first_mate/accesses.py` - the All accesses record, collected during each run
- `first_mate/ship_log.py` - builds, renders, and saves Ship Logs, including the accesses section
- `first_mate/cli.py` - `run`, `health`, and `serve` commands
- `first_mate/server.py` - tiny web UI, standard library only
- `first_mate/config.py` - `.env` and environment config, no hardcoded keys
- `sample/sample-chat.txt` - sample messy team chat for the demo
- `tests/test_first_mate.py` - tests
- `deploy/boat.md` - how to run it on a Boat.dev VM
- `SAMPLE-OUTPUT.md` - actual output of the verified demo run
