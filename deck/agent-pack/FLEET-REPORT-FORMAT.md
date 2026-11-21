# Fleet Report Format — the real-data contract

This replaces samples. When an agent (or a human) reports work to First
Mate, the report is plain text in the format below. It is the same
format a team chat export uses, so anything that can produce chat lines
can file a report — through `POST /api/ship-log`, or as a `.txt` file
in the `inbox/` folder.

## The format

One message per line. Every line starts with who is speaking:

```
Name: message text
```

- **Name** — the reporter's stable name: `CI agent`, `Research agent`,
  `Operator`, a person's name. Letters, spaces, and `.'-` only, up to
  ~40 characters. Keep one name per reporter across reports; the log
  attributes work by name.
- **Links** — paste bare URLs inline (`https://…`). Each unique link is
  collected into the Ship Log's Shared links, deduplicated.
- **Decisions** — a line becomes a decision when it says what was
  settled. The parser keys on plain words people actually use:
  `decided`, `Decision:`, `we will`, `we'll`, `agreed`, `locked:`,
  `final:`, `going with`. Write decisions as decisions:
  `Research agent: Decision: the digest goes out once, in the morning`.
- **Actions** — a line becomes an action when it carries work for
  someone: `TODO`, `to do:`, `action:`, `needs to`, `need to`,
  `please …`, `can you …`, `I will build / write / set up / check …`,
  a deadline phrase (`by Friday`, `by tomorrow`), or a line starting
  with `@Name` (a direct assignment). Write commitments in the first
  person with the verb in: `Lane agent: I will check the staging
  deploy tonight` is filed as an action; `Lane agent: deploy stuff`
  is filed as a note.
- **Notes** — everything else. Status, results, blockers stated as
  facts. Notes are kept in the log's record; they just are not actions
  or decisions. A blocker deserves its own line, plainly:
  `Lane agent: Blocked on the staging credentials, cannot continue
  until they are rotated`. If the blocker line also names the
  unblocking work (`someone needs to rotate them`), it files as an
  action as well — which is correct: unblocking is somebody's job.
- Blank lines and lines starting with `---` are ignored. Limits per
  report: 1,000,000 characters, 10,000 messages. Split a bigger report
  into parts and file each part.

File it with the reporter's name as the source:

```sh
curl -X POST http://127.0.0.1:8899/api/ship-log \
  -H 'Content-Type: application/json' \
  -d '{"source": "Morning fleet report", "chat": "<report text>"}'
```

## A real-shaped example

A fleet reporting one morning's work. Outcomes are stated as outcomes;
there are no numbers in it that nobody measured.

```
Operator: Morning report — status, blockers, and anything that needs my call, in this thread
Lane agent: The onboarding flow rebuild is finished and merged, the branch is closed
CI agent: The nightly suite passed on every target, full run log is here https://www.rfc-editor.org/rfc/rfc3986.txt
Research agent: The provider comparison is drafted, it is waiting on the benchmark check before it goes out
Comms agent: The launch announcement draft is done, it only needs the final screenshot
Lane agent: Blocked on the staging credentials, someone needs to rotate them before I can continue
Operator: TODO Lane agent, please rerun the full suite once the credentials land
Research agent: Decision: the digest goes out once a day, in the morning, no drip feed
CI agent: Agreed, failed builds post to this channel only, nowhere else
Comms agent: I will write the final announcement as soon as the screenshot is approved
Lane agent: The operator deploy checklist is here https://www.rfc-editor.org/rfc/rfc9110.txt
Research agent: Someone needs to verify the benchmark figures before they go into the report
Operator: Decision: the fleet pauses new work on Fridays for a one hour review
Comms agent: Operator, please approve the deploy before the release window closes
Lane agent: I will set up the release branch run tonight and post the result here
```

Filed, this produces a Ship Log with six actions (rotating the
credentials, the rerun, the announcement, the benchmark check, the
deploy approval, the release run), three decisions, and two shared
links — plus an All Accesses panel stating exactly what the run read
and what it did not. Note the blocker line files as an action, because
"someone needs to rotate them" *is* one; the same line stays in the
record as the reason the Lane agent is stopped. Verified against the
parser, not estimated.

## How a human reads the result

The Ship Log is one store on the server; every surface reads the same
store, so state never disagrees between screens.

- **Deck (the bridge):** the home screen shows the latest Ship Log
  live — actions as large rows, decisions under them. Nothing is typed
  on the Deck. The operator works it with the controller: D-pad moves,
  A checks an action off, B goes back. Check-off is written to the
  server, so it is true everywhere the moment it happens.
- **Phone (capture):** where reports are pasted or shared in — the
  Android share sheet and the paste-and-send strip file straight to
  the server — and where the operator reads the same log away from
  the desk, with the same tap-to-check-off.
- **Watch (glance + act):** the newest log's top actions, largest text,
  tap to check off, a buzz when a new Ship Log lands. The watch never
  shows more than the next few things to do; that is its job.
- **The file itself:** every run is saved as Markdown in
  `data/ship-logs/`, with its All Accesses record. The surfaces are
  views. The file is the log.

## Filing checklist for agents

1. One report per work period or event — do not batch a week into one
   file, and do not file the same work twice.
2. Your real name, every line. Attribution is how the human knows who
   is blocked and who is done.
3. Decisions phrased as decisions, commitments phrased as "I will …",
   blockers on their own line.
4. Links bare and inline, next to the line they belong to.
5. After filing, read `GET /api/latest` and confirm your run is the
   one in the log. If it is not there, it did not happen.
