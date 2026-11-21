First Mate — Inbox drop folder
==============================

Drop any team chat as a plain .txt file into THIS folder (inbox/).

The Deck server watches this folder (every few seconds). Each new .txt
file is automatically run through First Mate as a Ship Log with the
source label "Inbox drop: <filename>", saved to data/ship-logs/ like
any other run — so it shows up on the Deck home (live), the phone app
and the watch — and the file is then moved to inbox/processed/.

No typing on the Deck needed: copy the chat on any machine that can
reach this folder (USB stick, file share, scp), drop it here, done.

This README.txt itself is ignored by the importer.
