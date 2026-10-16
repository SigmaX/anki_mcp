"""Download-only setup for an isolated AnkiWeb snapshot. Never normal-sync/upload."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from anki.collection import Collection


class SetupError(Exception):
    """Safe-to-display setup error, without backend credential-bearing details."""


def credential_status() -> dict:
    return {"username_configured": bool(os.environ.get("ANKIWEB_USERNAME")),
            "password_configured": bool(os.environ.get("ANKIWEB_PASSWORD")),
            "anki_version": version("anki"), "mode": "download-only",
            "network_contacted": False}


def _validate_endpoint(endpoint: str) -> None:
    if not endpoint:
        return  # Anki's built-in default server.
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host.endswith(".ankiweb.net")
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment):
        raise SetupError("Anki returned an unexpected sync endpoint; download stopped.")


def collection_summary(col: Collection) -> dict:
    """Read counts and integrity through Anki, which supplies its SQLite collations."""
    integrity = col.db.scalar("pragma integrity_check")
    if integrity != "ok":
        raise SetupError("Downloaded collection failed its integrity check.")
    return {"cards": col.db.scalar("select count(*) from cards"),
            "notes": col.db.scalar("select count(*) from notes"),
            "review_history_rows": col.db.scalar("select count(*) from revlog"),
            "decks": len(col.decks.all_names_and_ids()), "integrity": "ok"}


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_snapshot(directory: Path, username: str, password: str, *,
                      collection_factory=None) -> dict:
    """Download into a new private directory; keep credentials only in memory.

    No overwrite/retry-in-place, normal sync, upload, or media sync is offered.
    On failure, retain the incomplete folder but do not mark it complete.
    """
    if not username or not password:
        raise SetupError("Configure ANKIWEB_USERNAME and ANKIWEB_PASSWORD as environment secrets.")
    directory = directory.absolute()
    try:
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    except FileExistsError:
        raise SetupError("Destination already exists. Choose a new, unused directory.") from None
    path = directory / "collection.anki2"
    factory = collection_factory or Collection
    col = None
    summary = None
    try:
        col = factory(str(path))
        auth = col.sync_login(username, password, None)
        _validate_endpoint(auth.endpoint)
        # Resolve account routing using status, without exchanging local changes.
        status = col.sync_status(auth)
        if status.new_endpoint:
            _validate_endpoint(status.new_endpoint)
            auth.endpoint = status.new_endpoint
        col.close_for_full_sync()
        try:
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
        finally:
            # Match Anki Desktop's lifecycle, including failed full downloads.
            col.reopen(after_full_sync=True)
        summary = collection_summary(col)
    except SetupError:
        raise
    except Exception:
        raise SetupError("AnkiWeb download failed. No upload was attempted. "
                         "The destination is incomplete; use a new directory to retry.") from None
    finally:
        if col is not None:
            try:
                col.close()
            except Exception:
                raise SetupError("Could not close the snapshot cleanly; it is not marked complete.") from None
    result = {"status": "downloaded", "collection": str(path),
              "anki_version": version("anki"), "summary": summary,
              "sha256": _file_hash(path), "media_downloaded": False,
              "uploads_enabled": False, "review_enabled": False,
              "credentials_stored": False}
    (directory / "snapshot.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check credential presence without contacting AnkiWeb")
    download = commands.add_parser("download", help="Download a snapshot into a brand-new directory")
    download.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            result = credential_status()
        else:
            result = download_snapshot(args.directory, os.environ.get("ANKIWEB_USERNAME", ""),
                                       os.environ.get("ANKIWEB_PASSWORD", ""))
        print(json.dumps(result, indent=2))
        return 0
    except (SetupError, OSError):
        # Avoid traceback, raw backend responses, or echoing secret values.
        print("Setup did not complete. Check secret bindings, network access, account credentials, "
              "and that the destination directory does not exist. No upload is available.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
