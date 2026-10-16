import anyio
from datetime import timedelta
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

from anki_review.console import server_parameters
from anki_review.review import ReviewService, create_demo
from conftest import review_count


def test_rating_requires_reveal_and_retries_do_not_duplicate(collection):
    path, deck = collection
    service = ReviewService(path)
    try:
        front = service.next_card(deck)
        token = front["review_token"]
        assert "answer_text" not in front
        assert service.next_card(deck) == front
        with pytest.raises(ValueError, match="Reveal"):
            service.rate_card(token, "good")
        assert review_count(path) == 0
        answer = service.reveal_answer(token)
        assert set(answer["ratings"]) == {"again", "hard", "good", "easy"}
        receipt = service.rate_card(token, "good")
        assert service.rate_card(token, "good") == receipt
        with pytest.raises(ValueError, match="another rating"):
            service.rate_card(token, "easy")
        assert review_count(path) == 1
    finally:
        service.close()
    reopened = ReviewService(path)
    try:
        assert reopened.col.get_card(front["card_id"]).reps == 1
        with pytest.raises(ValueError, match="expired"):
            reopened.rate_card(token, "good")
        assert review_count(path) == 1
    finally:
        reopened.close()


def test_cancel_invalid_tokens_and_exclusive_access(collection):
    path, deck = collection
    service = ReviewService(path)
    try:
        with pytest.raises(BlockingIOError):
            ReviewService(path)
        with pytest.raises(ValueError, match="Unknown deck"):
            service.next_card(-1)
        front = service.next_card(deck)
        with pytest.raises(ValueError, match="expired"):
            service.reveal_answer("incorrect")
        assert service.cancel_review(front["review_token"])["review_recorded"] is False
        with pytest.raises(ValueError, match="expired"):
            service.reveal_answer(front["review_token"])
        assert review_count(path) == 0
    finally:
        service.close()


def test_backup_contains_previous_reviews(collection):
    path, deck = collection
    service = ReviewService(path)
    token = service.next_card(deck)["review_token"]
    service.reveal_answer(token)
    service.rate_card(token, "easy")
    service.close()
    service = ReviewService(path)
    service.close()
    backups = sorted((path.parent / "backups").glob("*.anki2"))
    assert review_count(backups[-1]) == 1
    with pytest.raises(ValueError, match="overwrite"):
        create_demo(path)
    assert review_count(path) == 1


def test_missing_collection_is_not_created(tmp_path):
    path = tmp_path / "missing.anki2"
    with pytest.raises(ValueError, match="does not exist"):
        ReviewService(path)
    assert not path.exists()


def test_real_mcp_round_trip(collection):
    path, deck = collection

    async def run():
        async with stdio_client(server_parameters(path)) as streams:
            async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=10)) as client:
                await client.initialize()
                listing = await client.list_tools()
                assert {tool.name for tool in listing.tools} == {
                    "list_decks", "next_card", "reveal_answer", "rate_card", "cancel_review",
                    "prepare_batch", "commit_batch"}
                result = await client.call_tool("next_card", {"deck_id": deck})
                assert not result.isError
                token = result.structuredContent["review_token"]
                rejected = await client.call_tool("rate_card", {"review_token": token, "rating": "good"})
                assert rejected.isError
                revealed = await client.call_tool("reveal_answer", {"review_token": token})
                assert not revealed.isError
                assert "answer_text" in revealed.structuredContent
                recorded = await client.call_tool("rate_card", {"review_token": token, "rating": "easy"})
                assert not recorded.isError
                assert recorded.structuredContent["recorded"]
                retry = await client.call_tool("rate_card", {"review_token": token, "rating": "easy"})
                assert retry.structuredContent == recorded.structuredContent

    anyio.run(run)
    assert review_count(path) == 1
