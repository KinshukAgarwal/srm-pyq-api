#!/usr/bin/env python3
"""CLI client for SRM PYQ API endpoints."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.parse import quote

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SRM PYQ API client")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")

    courses = subparsers.add_parser("courses")
    courses.add_argument("--q", default="")
    courses.add_argument("--cursor", default="")
    courses.add_argument("--limit", type=int, default=20)

    course = subparsers.add_parser("course")
    course.add_argument("course_code")

    papers = subparsers.add_parser("papers")
    papers.add_argument("course_code")
    papers.add_argument("--year", type=int)
    papers.add_argument("--term", default="")
    papers.add_argument("--cursor", default="")
    papers.add_argument("--limit", type=int, default=20)

    paper = subparsers.add_parser("paper")
    paper.add_argument("paper_id")

    files = subparsers.add_parser("files")
    files.add_argument("paper_id")

    download = subparsers.add_parser("download")
    download.add_argument("file_id")
    download.add_argument("--ttl", type=int, default=900)

    return parser.parse_args()


def api_get(base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.get(url, params=params, timeout=30)

    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = {"raw": response.text}

    if response.status_code >= 400:
        print(json.dumps({"status": response.status_code, "error": payload}, indent=2))
        sys.exit(1)

    return payload


def path_part(raw: str) -> str:
    """Encode path arguments so special course codes stay valid in URLs."""
    return quote(raw, safe="")


def main() -> None:
    args = parse_args()

    if args.command == "health":
        result = api_get(args.base_url, "/health")
    elif args.command == "courses":
        result = api_get(
            args.base_url,
            "/v1/courses",
            params={
                "q": args.q,
                "cursor": args.cursor,
                "limit": args.limit,
            },
        )
    elif args.command == "course":
        result = api_get(args.base_url, f"/v1/courses/{path_part(args.course_code)}")
    elif args.command == "papers":
        params: dict[str, Any] = {
            "term": args.term,
            "cursor": args.cursor,
            "limit": args.limit,
        }
        if args.year is not None:
            params["year"] = args.year
        result = api_get(
            args.base_url,
            f"/v1/courses/{path_part(args.course_code)}/papers",
            params=params,
        )
    elif args.command == "paper":
        result = api_get(args.base_url, f"/v1/papers/{path_part(args.paper_id)}")
    elif args.command == "files":
        result = api_get(args.base_url, f"/v1/papers/{path_part(args.paper_id)}/files")
    elif args.command == "download":
        result = api_get(
            args.base_url,
            f"/v1/files/{path_part(args.file_id)}/download",
            params={"ttl_seconds": args.ttl},
        )
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
