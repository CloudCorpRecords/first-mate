# First Mate: Production Use Cases

First Mate is a helper that sits in a team chat. A team pastes or exports its chat, and First Mate returns a Ship Log: a checklist of what to do next, the decisions the team made, the links the team shared with a note on how each one was read, a short summary, and an All accesses panel that lists every access the run made and every access it did not make, with the reason.

What is true today, and what every use case below is grounded in:

- Chat in, Ship Log out. The chat is parsed for action items, decisions, and links. The Ship Log comes out as markdown and HTML, formatted to paste straight back into the team chat.
- Private by default. In Local only mode the summary is produced on the machine itself. No network call is made for the summary, so no team content leaves the machine.
- Always on. First Mate is packaged to run on a persistent Boat.dev VM (Dockerfile and deploy guide included), so it is there whenever the team is working, and every Ship Log is archived to disk so the record survives restarts.
- Links are actually read. Each shared link is fetched and read, directly in the free mode, or through Context.dev when a key is configured. Every link in the Ship Log is labeled with how it was read, or honestly labeled Not fetched if the read failed.
- Verifiable. The All accesses panel shows the chat read, each link access and its result, the AI mode used, the hosting status and health check result, and the accesses that were not made, with reasons. Nobody has to trust a claim, they can check the panel.
- It runs with no keys and no credits. Fourteen tests pass. It is MIT licensed and open source.

Anything beyond that is labeled roadmap below. Roadmap items are not built and are never presented as built.

## 1. Hackathon teams: a chaotic event chat becomes a build plan

The pain: a hackathon team coordinates in one fast moving group chat. Tasks, decisions, sponsor docs, and demo deadlines scroll past each other, and by the second day nobody can say what was decided or who owns what.

How First Mate runs: the team exports or copies the chat and runs it through First Mate, on a laptop or on the Boat VM the team leaves running for the event. The Ship Log goes back into the same chat, so the whole crew sees one shared plan.

The concrete output: a checklist of next actions with the owner named where the chat named one, the decisions the team actually made (scope calls, the demo format, the name), every shared link in one place with a note on each, and an archive of Ship Logs on disk that shows how the plan changed across the event. This is exactly the flow First Mate was built and verified with during the Boat Hackathon itself.

Roadmap: a live bot that watches the chat and posts a fresh Ship Log on a schedule, instead of the team running it by hand.

## 2. Remote engineering teams: standup notes that write themselves

The pain: a distributed team talks all day in chat, but the record of the work lives in people's heads. Standups repeat what was already said in the channel, and decisions made on Tuesday are re-argued on Friday because nobody wrote them down.

How First Mate runs: at the end of the day, the channel export goes through First Mate on the team's Boat VM. Because the VM is persistent, the Ship Logs accumulate in one archive instead of scattering across laptops.

The concrete output: the day's action checklist with owners, a decisions list the team can point to when a question comes back, and the links shared that day already read and summarized, so a teammate in another timezone catches up from one page instead of scrolling a channel. In Local only mode the raw chat never leaves the team's own machine, which matters for teams whose channels carry customer names and internal links.

Roadmap: automatic daily runs per channel, and posting the Ship Log into an issue tracker as tasks.

## 3. Incident and on-call channels: a post-incident action list without the archaeology

The pain: after an outage, someone has to reread hundreds of messages to reconstruct what was tried, what was decided, and what follow up work was promised in the moment. That reconstruction is slow, and promised fixes quietly get lost.

How First Mate runs: the incident channel export goes through First Mate in Local only mode. Incident channels carry sensitive detail, so the fact that no team data leaves the machine in this mode is the point, not a limitation.

The concrete output: a checklist of every follow up action that was named during the incident, the decisions taken under pressure (roll back, fail over, page a vendor), and the links to dashboards, runbooks, and status pages that were shared, each labeled with how it was read. The All accesses panel doubles as an audit trail: it states plainly what the tool touched and what it did not, which is what a post-incident review actually needs.

Roadmap: severity and timeline extraction, and a structured export for incident review tools.

## 4. Open source maintainer teams: contributor chat triaged into tasks

The pain: maintainers coordinate in busy public and private chats where bug reports, feature requests, and offers to help arrive mixed together. Good contributions get missed because nobody converted the chat into a task list.

How First Mate runs: the maintainers run the day's chat through First Mate on a Boat VM that stays up around the clock, which suits a team spread across timezones that never shares a working day.

The concrete output: an action list separating what needs doing from what was merely discussed, the decisions maintainers made (accepted, declined, needs a repro), and every shared link, issue, and pull request reference collected in one place with a note on each. Because First Mate is MIT licensed and needs no keys, a project can run its own copy on its own VM and keep full control of the data.

Roadmap: deduplication against the existing issue list, and draft issue creation from action items.

## 5. Event operations crews: vendors and sponsors coordinated from one chat

The pain: an events team runs production out of group chats with vendors, sponsors, and venue staff. Load in times, signage decisions, and sponsor deliverables are agreed in chat and then buried, and on show day the team burns time re-asking questions that were already answered.

How First Mate runs: the ops chat goes through First Mate at each shift change, on a Boat VM that is always on during the event run. The Ship Log is pasted back into the ops chat, so vendors and staff work from the same page without new tooling or accounts.

The concrete output: the next actions list for the incoming shift, the decisions already locked (vendor arrival times, sponsor placements, schedule changes), and the shared links, contracts, floor plans, and run sheets, read and noted. This mirrors how Founders Bay event operations actually coordinates, and it works for a crew that will never adopt a project management tool mid event.

Roadmap: role based views (vendors see only their items), and a show day mode that refreshes the Ship Log hourly.

## Why the Boat VM matters in every case above

Each of these teams needs the helper to be present when the work happens, not installed on one person's laptop. A persistent Boat.dev VM gives First Mate an always on home, on disk Ship Log archives, and a health check the team can hit to confirm it is alive. The same code runs locally with no keys, so a team can start free and private, and move it onto a Boat VM when they want it always on.
