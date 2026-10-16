import pytest

import anki_review.review as review
from conftest import review_count


def test_reopen_failure_returns_saved_receipt_and_never_repeats_review(collection, monkeypatch):
    path, deck = collection
    service = review.ReviewService(path)
    token = service.next_card(deck)["review_token"]
    service.reveal_answer(token)

    def failed_open(*args, **kwargs):
        raise OSError("simulated reopening failure")

    with monkeypatch.context() as patch:
        patch.setattr(review, "Collection", failed_open)
        receipt = service.rate_card(token, "good")
        assert receipt["recorded"] is True
        assert receipt["status"] == "recorded"
        assert receipt["service_available"] is False
        assert review_count(path) == 1
        assert service.rate_card(token, "good") == receipt
        with pytest.raises(ValueError, match="storage error"):
            service.list_decks()
    service.close()
    reopened = review.ReviewService(path)
    try:
        assert reopened.list_decks()["decks"]
        assert review_count(path) == 1
    finally:
        reopened.close()


def test_answer_error_is_uncertain_and_cannot_be_retried(collection, monkeypatch):
    path, deck = collection
    service = review.ReviewService(path)
    try:
        token = service.next_card(deck)["review_token"]
        service.reveal_answer(token)
        def fail(*args):
            raise OSError("simulated write failure")
        monkeypatch.setattr(service.col.sched, "answer_card", fail)
        receipt = service.rate_card(token, "good")
        assert receipt["recorded"] is None
        assert receipt["status"] == "uncertain"
        assert service.rate_card(token, "good") == receipt
        with pytest.raises(ValueError, match="storage error"):
            service.next_card(deck)
        assert review_count(path) == 0
    finally:
        service.close()
