"""An interactive MCP client, also usable by the assistant through a terminal."""
import json
import sys
from datetime import timedelta
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def server_parameters(path: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "anki_review", "server", "--collection", str(path)],
        cwd=Path(__file__).resolve().parents[1])


async def console(path: Path):
    async with stdio_client(server_parameters(path)) as streams:
        async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as session:
            await session.initialize()
            print("Commands: decks | next DECK_ID | reveal | rate RATING | cancel | batch DECK_ID [LIMIT] | commit JSON_LIST | quit", flush=True)
            token = None
            batch_token = None
            while True:
                try:
                    line = await anyio.to_thread.run_sync(lambda: input("anki> "))
                except EOFError:
                    break
                words = line.strip().split()
                if not words:
                    continue
                if words == ["quit"]:
                    break
                try:
                    if line.strip().startswith("commit ") and batch_token:
                        name = "commit_batch"
                        args = {"batch_token": batch_token,
                                "ratings": json.loads(line.strip().split(" ", 1)[1])}
                    else:
                        name, args = parse_command(words, token)
                    if name is None:
                        print("Unknown command, or fetch a card first.", flush=True)
                        continue
                    result = await session.call_tool(name, args)
                    payload = result.structuredContent
                    if payload:
                        token = payload.get("review_token", token)
                        batch_token = payload.get("batch_token", batch_token)
                        print(json.dumps(payload, indent=2), flush=True)
                    else:
                        print(result.model_dump_json(), flush=True)
                except ValueError as exc:
                    print(str(exc), flush=True)


def parse_command(words, token):
    match words:
        case ["decks"]:
            name, args = "list_decks", {}
        case ["next", deck_id]:
            name, args = "next_card", {"deck_id": int(deck_id)}
        case ["reveal"] if token:
            name, args = "reveal_answer", {"review_token": token}
        case ["rate", rating] if token:
            name, args = "rate_card", {"review_token": token, "rating": rating}
        case ["cancel"] if token:
            name, args = "cancel_review", {"review_token": token}
        case ["batch", deck_id]:
            name, args = "prepare_batch", {"deck_id": int(deck_id), "limit": 10}
        case ["batch", deck_id, limit]:
            name, args = "prepare_batch", {"deck_id": int(deck_id), "limit": int(limit)}
        case _:
            return None, {}
    return name, args
