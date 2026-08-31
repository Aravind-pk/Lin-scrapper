"""One live fetch through our own client, reporting field coverage.

Checks the extractor mappings that unit tests cannot: the synthetic fixture is
shaped from documentation, so only a real response proves the field names are
right.

    ./.venv/bin/python tools/verify_live.py <slug> [--dump path.json]

Makes exactly one request. Prints a coverage table, not the profile contents.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import (  # noqa: E402
    csrf_token_for,
    get_settings,
    parse_cookie_header,
)
from app.linkedin.client import LinkedInClient  # noqa: E402
from app.linkedin.constants import EXAMPLE_USER_AGENT  # noqa: E402
from app.linkedin.profile import extract_profile  # noqa: E402


def summarise(value) -> str:
    if value is None or value == [] or value == "":
        return "EMPTY"
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    text = str(value)
    return f"{len(text)} chars" if len(text) > 60 else repr(text)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--dump", help="write the raw response here")
    ap.add_argument("--show", action="store_true", help="print extracted values")
    ap.add_argument(
        "--user-agent",
        default=EXAMPLE_USER_AGENT,
        help="the browser the cookies came from; a mismatch kills the session",
    )
    args = ap.parse_args()

    settings = get_settings()
    cookies = parse_cookie_header(os.environ.get("LI_COOKIE_HEADER", ""))
    if not cookies.get("li_at"):
        print("Set LI_COOKIE_HEADER in the environment.", file=sys.stderr)
        return 1
    client = LinkedInClient(
        cookies=cookies,
        csrf_token=csrf_token_for(cookies),
        user_agent=args.user_agent,
        timeout=settings.request_timeout,
    )
    try:
        started = perf_counter()
        payload = await client.get_profile(args.slug)
        elapsed = int((perf_counter() - started) * 1000)
    finally:
        await client.aclose()

    included = payload.get("included") or []
    print(f"\nHTTP 200 in {elapsed} ms, {len(json.dumps(payload))} bytes, "
          f"{len(included)} entities\n")

    types = Counter(
        str(e.get("$type", "?")).rsplit(".", 1)[-1] for e in included
    )
    print("Entity types present:")
    for name, count in types.most_common():
        print(f"  {count:>4}  {name}")

    profile = extract_profile(payload)
    print("\nField coverage:")
    missing = []
    for field, value in profile.model_dump().items():
        state = summarise(value)
        flag = "  " if state != "EMPTY" else "->"
        print(f" {flag} {field:<18} {state}")
        if state == "EMPTY":
            missing.append(field)

    if args.show:
        print("\n" + profile.model_dump_json(indent=2))

    if args.dump:
        Path(args.dump).write_text(json.dumps(payload, indent=2))
        print(f"\nRaw response written to {args.dump}")

    print(
        f"\n{len(missing)} empty field(s): {', '.join(missing) or 'none'}"
        "\nEmpty may mean the profile lacks it, or the mapping is wrong — "
        "check against the entity types above."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
