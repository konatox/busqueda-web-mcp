"""Opt-in live check; never imported by the offline test suite."""

import argparse
import asyncio
import json

from busqueda_web_mcp.server import fetch_url, web_search


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="latest ComfyUI release")
    parser.add_argument("--read", action="store_true", help="Read only the first result")
    args = parser.parse_args()
    result = await web_search(args.query, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("error") or not result.get("results"):
        return 1
    if args.read:
        page = await fetch_url(result["results"][0]["url"], 4000)
        print(json.dumps(page, ensure_ascii=False, indent=2))
        if page.get("error"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
