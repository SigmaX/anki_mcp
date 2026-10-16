# Next stages

## Before using a real collection

1. Independent code and pytest review, including what the tests fail to establish.
2. A full collection export including scheduling/history and media, retained
   independently, plus a demonstrated restoration into a separate profile.
3. Explicit import/copy workflow; preserve card and note IDs, note types, deck
   options, tags, media, review logs, and FSRS data. Never experiment on the only copy.
4. Offline rehearsal on a copy of the user's roughly 80,000-card collection.
   Compare before/after records and verify all unrelated data remains intact.
5. Test realistic histories, mature/relearning cards, FSRS settings, filtered and
   hierarchical decks, sibling burying, learning queues, timezone/day rollover,
   custom scheduling, schema compatibility, interrupted writes and retry recovery.
6. Measure startup, per-review latency, backup size and recovery time at that scale.
   Add meaningful failure-injection and large-collection tests before real use.

## Learning analytics (requested next, outside the first pass)

Expose focused, read-only MCP tools that answer learning-trend questions without
exporting a large review history into the conversation on every request.

- New cards first learned per year, with yearly breakdowns and an average.
- Grouping/filtering by Korean, other languages, all languages, history, and other
  subjects, using agreed deck and/or tag mappings.
- Review volume, retention, workload and learning trends over selected periods.
- Perform bounded aggregation inside the service. Return small summaries with
  definitions, filter criteria, timezone, date coverage and caveats.

Agree what "learned" means: first learning review, first graduation, or a retention
threshold are different metrics. Do not count imported creation timestamps or
relearning as first learning. Flag incomplete/deleted history; define whether
averages include partial years. Subject labels may overlap. Add fixture histories
with known expected totals and test queries before accessing user data.

## Voice review with optional visual cards (requested)

Support hands-free conversation while showing a card rendering when desired,
especially equations and other visual material. Investigate an interface embedded
alongside chat, with synchronized question/answer visibility and media support.
Render equations rather than expecting spoken math to replace them. Language
audio and safe HTML/template/media rendering also need dedicated support and tests.
The present text-only MCP prototype does not implement a chat-integrated app.

## Later: synchronization and deployment

Download-only connection setup is now implemented in `anki_review.ankiweb`;
see [ANKIWEB_SETUP.md](ANKIWEB_SETUP.md). Live authentication awaits environment
secret configuration. This does not enable real review writes or sync-back.

Design an AnkiWeb sync workflow only after offline validation. Establish version
compatibility, single-writer coordination, backup/restore and conflict handling.
Do not automate a full upload/download that overwrites either collection.

Persistent hosting and a remote authenticated MCP endpoint are optional later
steps. A terminal-assisted review session in this development environment is
enough for initial evaluation, subject to environment/session lifetime.
