import argparse
import json
from pathlib import Path

from .review import create_demo


def main():
    parser = argparse.ArgumentParser(description="Local Anki MCP review tools")
    parser.add_argument("command", choices=["demo", "spanish-demo", "server", "console"])
    parser.add_argument("--collection", type=Path)
    args = parser.parse_args()
    if args.collection is None:
        folder = "spanish-a1" if args.command == "spanish-demo" else "demo"
        args.collection = Path(__file__).resolve().parents[1] / "data" / folder / "collection.anki2"
    if args.command in {"demo", "spanish-demo"}:
        print(json.dumps(create_demo(args.collection, spanish=args.command == "spanish-demo"), indent=2))
    elif args.command == "server":
        from .server import build_server
        build_server(args.collection).run()
    else:
        import anyio
        from .console import console
        anyio.run(console, args.collection.resolve())


if __name__ == "__main__":
    main()
