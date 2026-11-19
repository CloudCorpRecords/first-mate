# Run First Mate on a Boat.dev VM

Boat.dev gives each project a persistent cloud VM. First Mate is built
to live on that VM: it has no dependencies beyond Python 3, and it
stores every Ship Log on disk so logs survive restarts. It also runs
locally with the same code, and no keys or credits are needed either way.

## Option A: plain Python, no Docker

1. Start a Boat VM from the Boat.dev dashboard or CLI. Open its
   terminal or SSH in.
2. Get the code onto the VM, for example:
   - `git clone <this project repo>` if the code is in a repo, or
   - upload the `first-mate` folder with the file tool in the VM desktop.
3. Go to the project folder:
   - `cd first-mate`
4. Optional, mark the hosting for the All accesses panel:
   - `export FIRST_MATE_ON_BOAT=1`
   - With that set, the All accesses record says the run was on a Boat VM.
   - Keys are not needed. Only add a `.env` file if you already have a
     key and want an optional upgrade route used.
5. Check it works:
   - `python3 -m first_mate health`
   - You should see JSON with `"status": "ok"` and `"hosting": "Boat VM"`.
6. Run the demo once from the sample chat:
   - `python3 -m first_mate run sample/sample-chat.txt --out out`
   - Open `out/ship-log.md` to see the result, including the All accesses section.
7. Start the web UI and leave it running:
   - `python3 -m first_mate serve`
   - Open the VM public URL or forwarded port 8000 in a browser.
   - Health check in a browser or with curl: `/health`

Ship Logs are stored in `data/ship-logs/` inside the project. That
folder is the persistent storage. Back it up or keep the VM stopped,
not deleted, to keep the logs.

## Option B: Docker

1. Start a Boat VM and open its terminal, as above.
2. Go to the project folder: `cd first-mate`
3. Build: `docker build -t first-mate .`
4. Run: `docker run -d --name first-mate -p 8000:8000 -e FIRST_MATE_ON_BOAT=1 -v first-mate-data:/app/data first-mate`
5. Check: `curl http://127.0.0.1:8000/health`
6. Open port 8000 in a browser for the demo UI.

## Stop and restart

- Plain Python: stop with Ctrl+C, restart with step 7 above.
- Docker: `docker stop first-mate` and `docker start first-mate`.
- Ship Logs stay in the data folder or Docker volume either way.

## Honest status

- With no keys at all, the VM run is Local only mode with direct
  fetch for links. That is the normal, complete mode, not a stub,
  and the demo needs no credits.
- The Context.dev and NYTE routes are optional upgrades only. They
  turn on only when their keys, and for NYTE also a base URL and
  model, are set in `.env`.
- The All accesses panel on each result shows whether that run was
  on a Boat VM or local, plus its health check result.
