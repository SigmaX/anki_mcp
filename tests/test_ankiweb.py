import json
from types import SimpleNamespace

import pytest

from anki_review.ankiweb import SetupError, collection_summary, download_snapshot, main
from anki_review.review import ReviewService, create_demo


class DownloadCollection:
    """Fake network boundary; every operation is recorded, with no server access."""
    def __init__(self, path, calls, *, fail=None, endpoint="https://sync2.ankiweb.net/"):
        self.path, self.calls, self.fail = path, calls, fail
        self.endpoint = endpoint
        self.db = SimpleNamespace(scalar=self.scalar)
        self.decks = SimpleNamespace(all_names_and_ids=lambda: [1, 2])

    def scalar(self, sql):
        return {"pragma integrity_check": "ok", "select count(*) from cards": 80000,
                "select count(*) from notes": 40000, "select count(*) from revlog": 900000}[sql]

    def sync_login(self, username, password, endpoint):
        self.calls.append("login")
        assert endpoint is None
        if self.fail == "login":
            raise RuntimeError(f"secret: {password}")
        return SimpleNamespace(endpoint="", hkey="secret-session-token")

    def sync_status(self, auth):
        self.calls.append("status")
        return SimpleNamespace(new_endpoint=self.endpoint)

    def close_for_full_sync(self):
        self.calls.append("close_for_full_sync")

    def full_upload_or_download(self, *, auth, server_usn, upload):
        self.calls.append("download")
        assert upload is False
        assert server_usn is None  # No automatic media sync.
        assert auth.endpoint == self.endpoint
        if self.fail == "download":
            raise RuntimeError("credential-bearing network response")
        from pathlib import Path
        Path(self.path).write_bytes(b"synthetic-downloaded-database")

    def reopen(self, *, after_full_sync):
        assert after_full_sync is True
        self.calls.append("reopen")

    def close(self):
        self.calls.append("close")


def factory(calls, **options):
    return lambda path: DownloadCollection(path, calls, **options)


def test_download_only_lifecycle_routing_and_manifest(tmp_path):
    calls = []
    folder = tmp_path / "snapshot"
    result = download_snapshot(folder, "test-user", "SECRET-PASSWORD", collection_factory=factory(calls))
    assert calls == ["login", "status", "close_for_full_sync", "download", "reopen", "close"]
    assert result["summary"]["review_history_rows"] == 900000
    assert result["review_enabled"] is False
    assert result["uploads_enabled"] is False
    assert result["media_downloaded"] is False
    manifest = (folder / "snapshot.json").read_text()
    assert json.loads(manifest) == result
    assert "SECRET-PASSWORD" not in manifest
    assert "secret-session-token" not in manifest
    assert "test-user" not in manifest
    assert folder.stat().st_mode & 0o777 == 0o700
    assert not list(folder.glob("*.anki-mcp-demo.json"))


def test_existing_destination_is_never_opened_or_overwritten(tmp_path):
    sentinel = tmp_path / "collection.anki2"
    sentinel.write_bytes(b"precious existing collection")
    calls = []
    with pytest.raises(SetupError, match="already exists"):
        download_snapshot(tmp_path, "user", "pass", collection_factory=factory(calls))
    assert calls == []
    assert sentinel.read_bytes() == b"precious existing collection"


@pytest.mark.parametrize("fail,expected", [
    ("login", ["login", "close"]),
    ("download", ["login", "status", "close_for_full_sync", "download", "reopen", "close"]),
])
def test_failure_closes_collection_and_never_marks_complete(tmp_path, fail, expected):
    calls = []
    folder = tmp_path / "snapshot"
    with pytest.raises(SetupError, match="download failed") as error:
        download_snapshot(folder, "user", "SECRET", collection_factory=factory(calls, fail=fail))
    assert "SECRET" not in str(error.value)
    assert calls == expected
    assert not (folder / "snapshot.json").exists()


@pytest.mark.parametrize("endpoint", ["http://sync2.ankiweb.net/", "https://attacker.example/",
                                    "https://sync.ankiweb.net.attacker.example/",
                                    "https://user:secret@sync.ankiweb.net/"])
def test_unexpected_routing_endpoint_stops_before_download(tmp_path, endpoint):
    calls = []
    with pytest.raises(SetupError, match="unexpected sync endpoint"):
        download_snapshot(tmp_path / "new", "user", "pass", collection_factory=factory(calls, endpoint=endpoint))
    assert calls == ["login", "status", "close"]


def test_missing_credentials_create_nothing(tmp_path):
    folder = tmp_path / "snapshot"
    with pytest.raises(SetupError, match="environment secrets"):
        download_snapshot(folder, "", "")
    assert not folder.exists()


def test_check_and_failure_output_never_expose_credentials(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ANKIWEB_USERNAME", "PRIVATE-USER")
    monkeypatch.setenv("ANKIWEB_PASSWORD", "PRIVATE-PASSWORD")
    assert main(["check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["username_configured"] and result["password_configured"]
    assert result["network_contacted"] is False
    assert "PRIVATE" not in str(result)
    assert main(["download", "--directory", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err


def test_summary_reads_real_anki_history_and_rejects_unmarked_snapshot(tmp_path):
    path = tmp_path / "collection.anki2"
    create_demo(path)
    service = ReviewService(path)
    try:
        summary = collection_summary(service.col)
        assert summary["cards"] == summary["notes"] == 3
        assert summary["review_history_rows"] == 0
        assert summary["integrity"] == "ok"
    finally:
        service.close()
    path.with_suffix(".anki-mcp-demo.json").unlink()
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Only practice"):
        ReviewService(path)
    assert path.read_bytes() == before
