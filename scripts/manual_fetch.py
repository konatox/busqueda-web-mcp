"""Opt-in live fetch check, with connection diagnostics on stderr."""

import argparse
import asyncio
import json
import logging

from busqueda_web_mcp.server import fetch_url


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--max-chars", type=int, default=4000)
    args = parser.parse_args()
    result = await fetch_url(args.url, args.max_chars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(asyncio.run(main()))
