import shutil

import pytest

from anki_review.review import ReviewService, demo_marker
from conftest import read_rows


def test_unmarked_collection_is_rejected_without_modification(collection):
    path, _ = collection
    demo_marker(path).unlink()
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Only practice"):
        ReviewService(path)
    assert path.read_bytes() == original


def test_review_preserves_existing_history_notes_other_cards_and_media(collection):
    path, deck = collection
    service = ReviewService(path)
    try:
        for _ in range(2):
            token = service.next_card(deck)["review_token"]
            service.reveal_answer(token)
            service.rate_card(token, "easy")
        existing = read_rows(path, "select * from revlog order by id")
        notes = read_rows(path, "select * from notes order by id")
        cards = read_rows(path, "select * from cards order by id")
        media = path.with_suffix(".media")
        media.mkdir(exist_ok=True)
        sample = media / "preservation-test.bin"
        sample.write_bytes(b"synthetic-media-sentinel")
        front = service.next_card(deck)
        service.reveal_answer(front["review_token"])
        service.rate_card(front["review_token"], "good")
        history = read_rows(path, "select * from revlog order by id")
        assert len(history) == len(existing) + 1
        assert all(row in history for row in existing)
        assert read_rows(path, "select * from notes order by id") == notes
        other_before = [row for row in cards if row[0] != front["card_id"]]
        other_after = read_rows(path, "select * from cards where id != ? order by id", (front["card_id"],))
        assert other_after == other_before
        assert sample.read_bytes() == b"synthetic-media-sentinel"
    finally:
        service.close()


def test_backup_can_be_restored_and_opened_by_anki(collection, tmp_path):
    path, deck = collection
    service = ReviewService(path)
    token = service.next_card(deck)["review_token"]
    service.reveal_answer(token)
    service.rate_card(token, "easy")
    service.close()
    service = ReviewService(path)
    service.close()
    backup = sorted((path.parent / "backups").glob("*.anki2"))[-1]
    restored = tmp_path / "restore" / "collection.anki2"
    restored.parent.mkdir()
    shutil.copy2(backup, restored)
    shutil.copy2(demo_marker(path), demo_marker(restored))
    service = ReviewService(restored)
    try:
        assert service.col.db.scalar("select count(*) from revlog") == 1
        assert service.col.db.scalar("select count(*) from notes") == 3
        assert service.col.db.scalar("pragma integrity_check") == "ok"
    finally:
        service.close()
