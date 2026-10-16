# Anki MCP — project and conversation handoff

## Purpose and current state

This project is a hobby Anki MCP server for conversational, primarily hands-free
flashcard review. The user has roughly 80,000 cards and extensive review history.
Preserving the collection, scheduling, IDs, media and history is a central
requirement. The user's new task is named **Anki MCP** and is reportedly running
in the newly created, intended cloud environment.

The development draft is committed to `SigmaX/anki_mcp` on `main`. The main draft
commit is `12bf2a58e8b970353b63a6d667e4dddfb62b9f3c`; a preceding commit initialized
the repository and ignore rules. Source, tests, lockfile and documentation are
included. Credentials, installed dependencies, caches and local Anki databases
are excluded. The repository was public when inspected.

No real Anki collection was downloaded, reviewed, or uploaded during the old
session. There has been no authenticated AnkiWeb connection test.

## Implementation

- Python 3.12, uv, pinned `anki==26.9.3` and `mcp==1.26.0`; transitive dependencies
  are recorded in `uv.lock`. Anki's Python package includes its Rust backend.
- `anki_review/review.py`: collection lease/backup, demo decks, single-card review,
  text extraction, retry receipts, and batch preparation/commit.
- `anki_review/server.py`: actual MCP server using the official Python SDK and
  local stdio transport. Tools are `list_decks`, `next_card`, `reveal_answer`,
  `rate_card`, `cancel_review`, `prepare_batch`, and `commit_batch`.
- `anki_review/console.py`: interactive real MCP client used by the assistant
  through terminal commands. The old conversation never had the server wired up
  as directly callable MCP tools. Terminal approvals and round trips made review
  slow; the local MCP server itself was real, not a simulated protocol.
- `anki_review/ankiweb.py`: separate download-only AnkiWeb setup CLI.

The review service accepts only synthetic collections marked by the demo
generator. Downloaded real snapshots do not receive that marker and cannot be
opened by the review service. This remains an intentional protection.

## Tests and independent review

The last complete suite run passed **38 tests**. Before committing the draft,
**36 collection-level tests passed** with the two MCP transport cases excluded;
the prior full run had included those two successfully.

Coverage includes all ratings, saved review rows, retries, expired tokens,
reveal gating, cancellation, deck validation, cloze hiding, advisory locking,
backup restoration, preservation of existing notes/history/other cards/media,
both directions of the Spanish demo, batch validation/partial saves, failure
injection, actual stdio MCP exchanges and download-only setup.

Independent reviewers inspected the review logic, batch logic, and download-only
AnkiWeb path. A post-save reopen failure previously returned an error for an
already saved review; it was fixed with cached receipts and a stopped service
after storage errors. A possibly saved review is not automatically replayed.
Uncertain batch IDs are separated from definitely unrecorded IDs.

Reviewers found no remaining blocker for the isolated demo. That is not approval
for real-data review/sync. Large collections, mature/relearning/FSRS/filtered-card
behavior, crash recovery, media-inclusive restore and performance remain gaps.

## Live voice trials exposed an unresolved workflow failure

Initial per-card review was too slow because each fetch/reveal/save required
terminal interactions and often approvals. The user requested batches of ten.

Batch mode returned real prepared prompts and backs to the agent, with ratings
staged until commit. However, the voice conversation repeatedly generated extra
cards outside the prepared batch, repeated prompts, and continued without a
batch commit. At one point it incorrectly accepted `la olla` for Spanish `pan`;
the correct translation is bread. These were conversation failures, not Anki's
review schedule. Tests passing did not establish reliable live voice behavior.

The last old-workspace database inspection showed **five saved demo reviews**:
hola Easy; adiós, gracias, sí and no Good. Six more ratings were retained only in
old-session in-memory staging: agua→water, pan→bread, leche→milk, casa→house,
libro→book and hello→hola, all Good. Further spoken trials cannot be treated as
a reliable record of submitted reviews. No batch commit occurred. The new task
does not inherit the old process, tokens or staging; those answers must not be
automatically replayed as fresh reviews.

An application-supplied finite sequence and reliable session state could reduce
drift, but cannot by themselves guarantee that a conversational model never
invents a spoken prompt. The user explicitly challenged that overclaim. Direct
MCP integration, prompt/state fidelity, receipt checking and an actual voice
evaluation are unfinished work.

## Agreed conversational preferences

- Very low latency and immediate acknowledgment when the user's answer is heard.
  No unexplained silence while tools run; no success/save claims before receipts.
- A fixed-language review uses just the prompt, without repeatedly asking what
  the translation is. Mixed-language decks need a target-language cue when the
  direction is ambiguous, particularly English-to-target-language prompts.
- The user explicitly authorizes **Good as the default** for a completed card
  unless another rating is given. Explicit Again/Hard/Good/Easy overrides it.
  The server still receives an explicit rating argument.
- The agent judges correctness, allows reasonable synonyms, and briefly confirms
  correct answers. Incorrect or ambiguous judgments open discussion/debate before
  committing or advancing. The agent does not silently map errors to Again.
- Spanish→English: a correct answer needs only brief correctness feedback; the
  English back need not be read aloud. English→Spanish: always speak the actual
  Spanish answer from the back, even after a correct response.
- Spanish words should use natural Spanish pronunciation, including prompts.
  The user noticed American-English pronunciation and asked for improvement.
- Ratings are normally saved before the next card; the user authorized delaying
  saves until ten completed cards specifically to reduce development friction.
  Pending vs saved must remain explicit. A pause/disconnect is not a rating.
- The intended workflow is to become a reproducible Codex skill eventually.
  `REVIEW_WORKFLOW.md` is a working specification, not an installed skill or a
  guarantee of observed behavior.

The practice deck is 20 simple A1 Spanish–English pairs, 40 cards using Basic
(and reversed card). Other prompts invented in voice are not additional deck data.

## AnkiWeb authentication and environment transition

The user saved personal values in Personal Vault using type Environment variable:

```
ANKIWEB_USERNAME
ANKIWEB_PASSWORD
```

The old task had no binding for either value. Both the environment status tool
and the CLI presence check reported them absent. No secret value was read out,
printed or put in the repository. The user subsequently created a reusable
GitHub-backed environment and the new task. Its binding/readiness has not been
verified from this old conversation.

Personal Vault entries only reach environments requesting their matching keys,
with a matching Applies-to scope. Published environment changes generally require
a new task. The old task's environment could not be switched through available
tools. The repository was created/populated partly to make the project available
in that new environment; GitHub is not an Anki/MCP technical requirement.

The next connection milestone is credential-presence/readiness verification in
the new task, followed by an isolated download. The existing commands are:

```sh
uv sync --locked --group dev
.venv/bin/python -m anki_review.ankiweb check
.venv/bin/python -m anki_review.ankiweb download \
  --directory /workspace/anki-mcp/data/ankiweb/snapshot-001
```

Paths depend on the new checkout. The download destination must not exist.
`check` prints booleans/version only and does not validate a password. Secret
values belong in configuration, never in chat, shell arguments or Git.

The download path uses Anki login, status-based endpoint routing, close for full
sync, full download with `upload=False` and `server_usn=None`, reopen, integrity
and count inspection, close and hash. No normal two-way sync, full upload or
media sync is implemented. Credentials/session tokens are not persisted. Remote
session/sync metadata can change; the claim is no upload of local card/review/
media changes, not zero server-side effects.

The successful manifest records database hash, library version, card/note/history
counts and integrity. Media are not included. Pinned Anki buffers collection
downloads in RAM. A pristine snapshot, comparisons against the source collection,
independent media-inclusive backup/restore and realistic scheduler tests are
prerequisites for later real review writes and sync-back.

## Further requirements and hosting discussion

- Read-only learning analytics through focused MCP tools: new cards learned per
  year, averages and trends grouped by Korean, other languages, all languages,
  history or other subjects. The user's goal is concise server-side aggregation,
  avoiding repeated export of large histories into the conversation. Definitions
  of learned, year coverage, subject mappings and incomplete history need care.
- Hands-free voice plus optional visible rendered cards for mathematics and
  other visual material. Candidates were inline math/images, a lightweight
  companion browser page, and embedded MCP Apps UI. A real renderer also needs
  CSS, media and MathJax. Mobile/live-voice compatibility remains untested.
- Current study tools return extracted text, excluding script/style content and
  cloze attributes that can leak answers. No faithful HTML/audio/media rendering
  has been implemented.
- Development can remain in a cloud workspace for initial evaluation; permanent
  deployment is optional and deferred. Sites can supply an MCP/UI endpoint but
  its Worker runtime is not a direct host for Anki's native backend. Cloudflare
  Containers may be possible, with persistence engineering; a small server with
  persistent disk is simpler. No hosting choice/deployment was made.
- The user welcomes subagents for bounded work and specifically requested
  independent code review, especially pytest and data-preservation coverage.

## Related documentation

- `README.md`: installation, commands, scope and limitations.
- `REVIEW_WORKFLOW.md`: evolving conversation specification.
- `ANKIWEB_SETUP.md`: download-only connection and official source references.
- `ROADMAP.md`: real-data validation, analytics, rendering, sync and hosting.
