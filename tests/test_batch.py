import pytest

from anki_review.review import ReviewService, create_demo
from conftest import review_count


def ratings(batch, rating="good"):
    return [{"card_id": c["card_id"], "rating": rating} for c in batch["cards"]]


def test_batch_preview_and_commit_preserve_history(collection):
    path, deck = collection
    service = ReviewService(path)
    try:
        front = service.next_card(deck)
        batch = service.prepare_batch(deck)
        assert batch["cards"][0]["review_token"] == front["review_token"]
        assert len(batch["cards"]) == 3
        assert all(c["question_text"] and c["answer_text"] for c in batch["cards"])
        assert review_count(path) == 0
        for call in (lambda: service.next_card(deck),
                     lambda: service.reveal_answer(front["review_token"]),
                     lambda: service.rate_card(front["review_token"], "good"),
                     lambda: service.cancel_review(front["review_token"])):
            with pytest.raises(ValueError, match="pending batch"):
                call()
        submitted = ratings(batch)
        receipt = service.commit_batch(batch["batch_token"], submitted)
        assert receipt["status"] == "recorded"
        assert len(receipt["receipts"]) == 3
        assert not receipt["unrecorded_card_ids"]
        assert review_count(path) == 3
        assert service.commit_batch(batch["batch_token"], submitted) == receipt
        assert review_count(path) == 3
        with pytest.raises(ValueError, match="different ratings"):
            service.commit_batch(batch["batch_token"], ratings(batch, "easy"))
    finally:
        service.close()
    reopened = ReviewService(path)
    try:
        assert review_count(path) == 3
        for c in batch["cards"]:
            assert reopened.col.get_card(c["card_id"]).reps == 1
    finally:
        reopened.close()


@pytest.mark.parametrize("bad", [
    [{"card_id": 123, "rating": "good"}],
    [{"card_id": 123, "rating": "wrong"}],
    [{"card_id": True, "rating": "good"}],
    [{"card_id": 123}],
])
def test_batch_invalid_input_writes_nothing(collection, bad):
    path, deck = collection
    service = ReviewService(path)
    try:
        batch = service.prepare_batch(deck)
        with pytest.raises(ValueError):
            service.commit_batch(batch["batch_token"], bad)
        assert review_count(path) == 0
        assert service.prepare_batch(deck) == batch
        # Invalid final entry is also rejected before the first valid write.
        submitted = ratings(batch)
        submitted[-1]["rating"] = "wrong"
        with pytest.raises(ValueError):
            service.commit_batch(batch["batch_token"], submitted)
        assert review_count(path) == 0
    finally:
        service.close()


def test_batch_stops_when_scheduler_removes_card(collection, monkeypatch):
    path, deck = collection
    service = ReviewService(path)
    try:
        batch = service.prepare_batch(deck)
        original = service.rate_card
        def save_and_suspend(token, rating):
            receipt = original(token, rating)
            remaining = [c["card_id"] for c in batch["cards"][1:]]
            service.col.sched.suspend_cards(remaining)
            return receipt
        monkeypatch.setattr(service, "rate_card", save_and_suspend)
        submitted = ratings(batch)
        receipt = service.commit_batch(batch["batch_token"], submitted)
        assert receipt["status"] == "partial"
        assert len(receipt["receipts"]) == 1
        assert len(receipt["unrecorded_card_ids"]) == 2
        assert review_count(path) == 1
        assert service.commit_batch(batch["batch_token"], submitted) == receipt
        assert review_count(path) == 1
    finally:
        service.close()


def test_batch_uncertain_write_is_never_replayed(collection, monkeypatch):
    path, deck = collection
    service = ReviewService(path)
    try:
        batch = service.prepare_batch(deck)
        def fail(*args):
            raise OSError("simulated storage failure")
        monkeypatch.setattr(service.col.sched, "answer_card", fail)
        submitted = ratings(batch)
        receipt = service.commit_batch(batch["batch_token"], submitted)
        assert receipt["status"] == "partial"
        assert receipt["receipts"][0]["recorded"] is None
        assert receipt["uncertain_card_ids"] == [batch["cards"][0]["card_id"]]
        assert batch["cards"][0]["card_id"] not in receipt["unrecorded_card_ids"]
        assert len(receipt["receipts"]) == 1
        assert service.commit_batch(batch["batch_token"], submitted) == receipt
        assert review_count(path) == 0
    finally:
        service.close()


def test_spanish_batch_has_ten_distinct_notes(tmp_path):
    path = tmp_path / "spanish.anki2"
    deck = create_demo(path, spanish=True)["deck_id"]
    service = ReviewService(path)
    try:
        batch = service.prepare_batch(deck)
        assert len(batch["cards"]) == 10
        assert len({service.col.get_card(c["card_id"]).nid for c in batch["cards"]}) == 10
        receipt = service.commit_batch(batch["batch_token"], ratings(batch))
        assert receipt["status"] == "recorded"
        assert review_count(path) == 10
    finally:
        service.close()


def test_batch_write_then_raise_is_marked_uncertain_not_unrecorded(collection, monkeypatch):
    path, deck = collection
    service = ReviewService(path)
    try:
        batch = service.prepare_batch(deck)
        original = service.col.sched.answer_card
        def save_then_fail(answer):
            original(answer)
            service.col.close()
            raise OSError("response lost after write")
        monkeypatch.setattr(service.col.sched, "answer_card", save_then_fail)
        submitted = ratings(batch)
        receipt = service.commit_batch(batch["batch_token"], submitted)
        assert review_count(path) == 1
        assert receipt["uncertain_card_ids"] == [batch["cards"][0]["card_id"]]
        assert batch["cards"][0]["card_id"] not in receipt["unrecorded_card_ids"]
        assert service.commit_batch(batch["batch_token"], submitted) == receipt
        assert review_count(path) == 1
    finally:
        service.close()
