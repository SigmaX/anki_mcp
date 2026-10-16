# Anki review MCP prototype

A local, single-user MCP server using Anki's own collection and scheduler APIs.
This is a development draft. In live voice trials, the conversation generated
prompts outside the prepared batch and continued without committing ratings.
The conversational workflow is documented as intended behavior, not a reliable
voice integration. Direct agent tool connection and consistent card/session
tracking remain unfinished.
The server, console client, and tests are Python. Anki includes a compiled Rust
backend. Linux is currently required for the collection lease (`fcntl`).

## Current scope

The review tools accept only synthetic collections created by `demo`. They offer
no AnkiWeb sync, credentials, import, deletion, or collection editing operations.
For the separate download-only AnkiWeb setup command, see
[ANKIWEB_SETUP.md](ANKIWEB_SETUP.md). It creates an isolated inspection snapshot;
the review tools remain restricted to demo collections.
There is no public listener: the transport is local standard input/output.
The marker file is an accidental-use guard, not an access-control mechanism.
Do not attach it to a real collection to bypass the guard.

Tools: `list_decks`, `next_card`, `reveal_answer`, `rate_card`, `cancel_review`.
The demo also supports `prepare_batch` and `commit_batch` for up to ten reviews
between terminal interactions. Batch preparation saves no reviews; returned backs
are for the agent's later evaluation, not immediate presentation to the user.
The agent sends Again, Hard, Good, or Easy, using the user's explicit choice or
a session default the user has authorized. Fetching and
revealing do not record a review. Repeated fetches return the active question.
See [REVIEW_WORKFLOW.md](REVIEW_WORKFLOW.md) for the agreed conversation flow,
including this user's default of Good and saving before advancing.
Cancellation does not record a review, although deck selection/queue generation
can change ordinary Anki collection metadata.

## Install and run

From `/workspace/anki-mcp`, using Python 3.12 and uv:

```sh
UV_CACHE_DIR=/workspace/.cache/uv uv sync --locked --group dev
.venv/bin/python -m anki_review demo
.venv/bin/python -m anki_review console
```

`demo` refuses to overwrite an existing collection. For another practice deck,
use `--collection /workspace/anki-mcp/data/another/collection.anki2` with each command.
The console is a real MCP client that launches the server as a child process.
Use `decks`, `next DECK_ID`, `reveal`, `rate good`, `cancel`, and `quit`.
For batch mode use `batch DECK_ID 10`, then `commit JSON_LIST`, where the list
contains objects such as `{"card_id": 123, "rating": "good"}` for the completed
cards. Inspect returned receipts; a batch is not an atomic transaction.
`unrecorded_card_ids` and `uncertain_card_ids` are separate: never automatically
resubmit an uncertain review. Batch review timers currently start during commit,
so their near-zero durations do not measure spoken review time. Use this mode
only for the synthetic demo, not for learning-time analytics or real-data review.
An assistant with terminal access can use this console during conversation;
the server is not automatically registered as tools in this chat.

The requested Spanish A1 deck contains 20 word pairs and 40 cards, with each pair
reviewed in both directions using Anki's Basic (and reversed card) note type:

```sh
.venv/bin/python -m anki_review spanish-demo
.venv/bin/python -m anki_review console --collection /workspace/anki-mcp/data/spanish-a1/collection.anki2
```

Anki's normal daily limits and sibling-bury settings determine which cards appear
in a session; all 40 need not appear on the same day. Translation prompts are
intentionally simple and can have synonyms; you choose the rating yourself.

To connect another local MCP client, use:

```json
{
  "command": "/workspace/anki-mcp/.venv/bin/python",
  "args": ["-m", "anki_review", "server"],
  "cwd": "/workspace/anki-mcp"
}
```

## Tests

```sh
.venv/bin/python -m pytest -q
```

Pytest creates an isolated collection under its temporary directory for each test.
The suite covers all ratings, durable review-history writes, retries, expired
tokens, reveal gating, cancellation, cloze answer hiding, deck validation,
exclusive service access, backups and restoring them through Anki, preservation
of existing review rows/notes/unrelated cards/media, and an actual stdio MCP
client/server exchange. SQLite inspection in tests is read-only; scheduling
writes go through Anki.

In this managed environment the MCP subprocess test and console need the command
runner's network permission for local async communication, even though they make
no external network requests. Without it the transport can stall. Collection-only
tests can run with `pytest -q -k 'not real_mcp'`.

## Data handling and limits

- The service holds an advisory lock for its lifetime. This prevents a second
  instance of this service from opening the same path. Anki Desktop and other
  programs do not honor that lock; never open the same collection concurrently.
- Before opening an existing practice collection, a SQLite backup snapshots the
  database into the adjacent `backups/` folder. These snapshots do not include
  media and are not a complete export. Backups are not rotated yet.
- A successful rating closes and reopens the collection through Anki before
  returning success. This conservative persistence boundary needs performance
  evaluation before using a large collection. Tokens survive only within one
  server process. Same-token/same-rating retries return the original receipt;
  after restart all old tokens are rejected, preventing replay.
  If reopening fails after a successful save, the receipt still reports that the
  review was recorded, but the service stops until restarted. A write/close error
  returns `recorded: null`, `status: uncertain`; inspect history before continuing.
  A possibly saved review is never automatically submitted again.
- Cards are returned as text. Formatting, audio, images, arbitrary template
  JavaScript, add-ons, and custom scheduler JavaScript are not supported.
  Cloze data attributes and script/style content are excluded from study text.
- The tests use small synthetic collections. They do not certify safe operation
  on a real 80,000-card collection, AnkiWeb synchronization, crash recovery, or
  all historical Anki schemas and scheduling configurations.
- Workspace files are development artifacts, not an independent backup. Keep
  a separately retained full Anki export before any future real-data work.

## Sources and dependencies

- Anki: [official source](https://github.com/ankitects/anki),
  [PyPI package](https://pypi.org/project/anki/), pinned at 26.9.3.
- MCP: [official Python SDK](https://github.com/modelcontextprotocol/python-sdk),
  [PyPI package](https://pypi.org/project/mcp/), pinned at 1.26.0.
- `uv.lock` records resolved transitive dependencies. `uv sync --locked` recreates
  them without resolving newer versions. No vendoring or fork of Anki is used.

See [ROADMAP.md](ROADMAP.md) for real-data validation, analytics, and sync work.
