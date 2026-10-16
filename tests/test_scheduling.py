import pytest

from anki_review.review import ReviewService
from conftest import read_rows


@pytest.mark.parametrize("rating,ease", [("again", 1), ("hard", 2), ("good", 3), ("easy", 4)])
def test_each_rating_writes_one_persistent_review(collection, rating, ease):
    path, deck = collection
    service = ReviewService(path)
    try:
        front = service.next_card(deck)
        token = front["review_token"]
        service.reveal_answer(token)
        receipt = service.rate_card(token, rating)
        assert receipt["reps"] == 1
        rows = read_rows(path, "select cid, ease from revlog")
        assert rows == [(front["card_id"], ease)]
        assert service.col.db.scalar("pragma integrity_check") == "ok"
    finally:
        service.close()


def test_empty_deck_and_invalid_rating_do_not_record_reviews(collection):
    path, deck = collection
    service = ReviewService(path)
    try:
        assert service.next_card(1)["done"]
        front = service.next_card(deck)
        with pytest.raises(ValueError, match="Rating must"):
            service.rate_card(front["review_token"], "excellent")
        assert service.next_card(deck) == front
        assert not read_rows(path, "select * from revlog")
        with pytest.raises(ValueError, match="switching decks"):
            service.next_card(1)
    finally:
        service.close()


def test_cloze_question_hides_the_deleted_answer(collection):
    path, _ = collection
    service = ReviewService(path)
    try:
        deck = service.col.decks.id("Cloze Test")
        note = service.col.new_note(service.col.models.by_name("Cloze"))
        note["Text"] = "The secret is {{c1::kumquat}}."
        service.col.add_note(note, deck)
        front = service.next_card(deck)
        assert "kumquat" not in front["question_text"]
        assert "kumquat" in service.reveal_answer(front["review_token"])["answer_text"]
    finally:
        service.close()
