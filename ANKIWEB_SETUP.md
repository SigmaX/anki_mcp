# AnkiWeb connection: isolated download first

The initial connection downloads a collection snapshot into a **new directory**.
It does not enable reviewing the real collection or sending changes back.
The existing review server continues to accept only synthetic demo collections.

## Credentials

Add these secret environment variables through the cloud environment's
configuration UI, not in chat, source files, shell command arguments, or Git:

- `ANKIWEB_USERNAME`: your AnkiWeb account email/username.
- `ANKIWEB_PASSWORD`: your AnkiWeb password.

After applying the configuration, run:

```sh
.venv/bin/python -m anki_review.ankiweb check
```

This prints only whether each value is present and the installed Anki version;
it does not log in or validate the password. The runtime status tool separately
reports secret readiness. An authenticated download is the live connection test.
Neither the password nor the returned Anki session token is saved by this code.

## First download

Sync your latest desired changes from your normal Anki client before taking the
snapshot. Keep an independently retained full backup including media. The new
cloud snapshot is not a replacement for that backup.

```sh
.venv/bin/python -m anki_review.ankiweb download \
  --directory /workspace/anki-mcp/data/ankiweb/snapshot-001
```

The directory must not exist, even if empty. A new private directory prevents
the full download from replacing an existing local collection. If a transfer
fails, retain its incomplete folder and choose a new destination for a retry.
The command never offers a full upload, ordinary two-way sync, or media sync.
It uses Anki's own authenticated collection download, not a CSV/deck export.

After success, `snapshot.json` records counts of cards, notes and review-history
rows, an integrity-check result, the Anki library version and a SHA-256 of the
closed database. It contains no account identifiers or credentials. Do not treat
an incomplete directory without a successful manifest as a usable snapshot.

The first download is the collection database only. Images/audio are not included.
Anki media sync merges changes; it needs its own reviewed workflow. This command
also does not demonstrate that AnkiWeb contains all history expected on your
desktop: compare the counts and representative records against your normal
collection before relying on it.

## Implementation boundaries

1. Create a brand-new local collection in the new destination.
2. Authenticate through `Collection.sync_login`.
3. Resolve the account's sync endpoint through `sync_status`, without exchanging
   card or review changes. Accept only HTTPS AnkiWeb subdomains.
4. Follow Anki Desktop's `close_for_full_sync`, full download (`upload=False`,
   `server_usn=None`), and `reopen(after_full_sync=True)` lifecycle, including on
   failure. A `None` media USN avoids automatic media sync.
5. Check local integrity/counts, close, hash, and mark complete.

Authentication/status/download may update remote session or sync metadata. The
claim is that this code never uploads local collection/review/media changes,
not that contacting AnkiWeb has zero remote side effects.

Pinned Anki 26.9.3 buffers a collection download in memory. Check available
memory/disk and observe the first transfer before drawing conclusions about
performance on the roughly 80,000-card collection. Tests use fake network
boundaries and real small local collections; no account has been tested yet.

## Before real review writes or sync-back

Compare source/download counts, sample historical reviews, note IDs/types, deck
options, FSRS settings, and media expectations. Retain a pristine snapshot and
rehearse on a copy. Validate mature/relearning/filtered cards and restoration.
Then design incremental sync and conflict handling separately; do not attach a
demo marker to this snapshot to bypass the current real-data guard.

## Sources checked

- [Anki sync manual](https://docs.ankiweb.net/syncing.html).
- [Pinned Anki Desktop sync lifecycle](https://github.com/ankitects/anki/blob/29bb700b/qt/aqt/sync.py).
- [Pinned backend full-sync implementation](https://github.com/ankitects/anki/blob/29bb700b/rslib/src/backend/sync.rs).
- [Pinned endpoint resolution](https://github.com/ankitects/anki/blob/29bb700b/rslib/src/sync/collection/meta.rs).
