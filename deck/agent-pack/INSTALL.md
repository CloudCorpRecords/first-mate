# Install First Mate — pop it into your stuff

First Mate is a self-contained folder. No dependencies beyond Python 3
(standard library only), no build step, no account, no keys required.
If a machine can run `python3`, it can run First Mate.

## The 3-step drop-in

**1. Copy the folder.**

Copy `first-mate-deck/` onto the target machine — a laptop, a Steam
Deck, a home server, a VM. The folder is the product; `data/ship-logs/`
inside it becomes that machine's persistent memory.

**2. Run the server.**

```sh
cd first-mate-deck
./launch.sh            # or: python3 deck.py
```

The server listens on port **8899** (set `FIRST_MATE_PORT` to change
it). Verify it before you trust it:

```sh
curl http://127.0.0.1:8899/health
```

You should get JSON with a healthy status. The surfaces are then live:
Deck home at `/`, phone at `/phone`, watch at `/watch`, saved logs at
`/logs`.

On a Steam Deck in Gaming Mode, use the included `steam-launch.sh` as a
non-Steam game shortcut — it starts the server if needed and opens the
app fullscreen. On any always-on machine, run it under whatever keeps
your other long-lived processes alive (systemd user service,
launchd, a process manager) so the log survives reboots.

**3. Point your agent at it.**

Give your agent two things:

- `agent-pack/AGENT.md` — the charter: who the First Mate is, how it
  works, the honesty rules it operates under.
- The server's `/llms.txt` — the live machine contract (endpoints,
  payloads, privacy and cost facts). The agent reads this itself; you
  do not need to explain the API to it.

From there the agent can file reports (`POST /api/ship-log`), read the
current log (`GET /api/latest`), and check off work
(`POST /api/actions/done`). Agents that cannot make HTTP calls can drop
`.txt` reports into the `inbox/` folder instead — they are imported
automatically. Report format: `FLEET-REPORT-FORMAT.md`.

## The persistent-VM path (Boat)

First Mate's natural home is a machine that never sleeps, so the crew's
log is current around the clock. The original `first-mate` package
ships that path:

- `first-mate/Dockerfile` — container build for the core server.
- `first-mate/deploy/boat.md` — step-by-step guide for running on a
  Boat.dev persistent VM, with or without Docker, including
  `FIRST_MATE_ON_BOAT=1` so the All Accesses record states the hosting
  truthfully.

**Honest status: this path is packaged and documented, and has not yet
been run live on a Boat VM.** Every run so far was local — on a laptop
or on-device on a Steam Deck. The code is the same code either way
(zero dependencies, logs on disk in `data/ship-logs/`), but "packaged"
is what we claim, because packaged is what is true. When you do run it
on a VM: keep the VM stopped-not-deleted or back up `data/ship-logs/` —
that folder is the memory, and the VM's disk is the only copy.

## Optional routes (only if you already have keys)

With no keys configured, First Mate runs complete in **Local only**
mode: links are read by direct fetch when online, labelled "Not
fetched" when offline, and summaries are extractive. Two optional
upgrades exist and are off by default:

- A link-reading service key (Context.dev) for richer link summaries.
- A private inference route (base URL + key + model) for written
  summaries instead of extractive ones.

If a key is absent, the All Accesses record says the route was not
used and why. Nothing about the core product depends on either route.

## What "installed" means

You are done when: `/health` answers, a test report filed through the
API appears at `/api/latest`, and the run's file exists in
`data/ship-logs/`. Anything less is a copy of the folder, not an
install.
