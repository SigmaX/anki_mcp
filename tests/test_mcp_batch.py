from datetime import timedelta

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

from anki_review.console import server_parameters
from anki_review.review import create_demo
from conftest import review_count


def test_ten_reviews_through_mcp_are_staged_then_saved_once(tmp_path):
    path = tmp_path / "collection.anki2"
    info = create_demo(path, spanish=True)

    async def run():
        async with stdio_client(server_parameters(path)) as streams:
            async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
                await client.initialize()
                prepared = await client.call_tool("prepare_batch", {"deck_id": info["deck_id"], "limit": 10})
                assert not prepared.isError
                batch = prepared.structuredContent
                assert len(batch["cards"]) == 10
                assert batch["recorded"] is False
                assert review_count(path) == 0
                ratings = [{"card_id": card["card_id"], "rating": "good"} for card in batch["cards"]]
                args = {"batch_token": batch["batch_token"], "ratings": ratings}
                saved = await client.call_tool("commit_batch", args)
                assert not saved.isError
                assert saved.structuredContent["status"] == "recorded"
                assert len(saved.structuredContent["receipts"]) == 10
                retried = await client.call_tool("commit_batch", args)
                assert retried.structuredContent == saved.structuredContent

    anyio.run(run)
    # Inspect durable storage after Anki releases its database lock on shutdown.
    assert review_count(path) == 10
