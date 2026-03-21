#!/usr/bin/env python3
"""Integration smoke test for SRM PYQ API."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.parse import quote

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test SRM PYQ API endpoints")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    session = requests.Session()
    failures: list[tuple[str, str]] = []

    def record(ok: bool, name: str, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}")
        if not ok:
            failures.append((name, detail))

    def get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
        response = session.get(f"{base_url}{path}", params=params, timeout=args.timeout)
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = {"raw": response.text}
        return response.status_code, payload

    status, payload = get("/health")
    record(status == 200 and payload.get("ok") is True, "/health", json.dumps(payload)[:250])

    status, payload = get("/v1/courses", params={"limit": 5})
    courses = payload.get("data", []) if status == 200 else []
    record(status == 200, "/v1/courses status", json.dumps(payload)[:250])
    record(isinstance(courses, list) and len(courses) > 0, "/v1/courses data", json.dumps(payload)[:250])
    record(isinstance(payload.get("page"), dict), "/v1/courses page", json.dumps(payload)[:250])

    if payload.get("page", {}).get("has_more") and payload.get("page", {}).get("next_cursor"):
        status2, payload2 = get(
            "/v1/courses",
            params={"limit": 5, "cursor": payload["page"]["next_cursor"]},
        )
        record(status2 == 200, "/v1/courses cursor", json.dumps(payload2)[:250])

    status, payload = get("/v1/courses", params={"q": "18AIC208J", "limit": 5})
    search_rows = payload.get("data", []) if status == 200 else []
    record(status == 200, "/v1/courses?q= status", json.dumps(payload)[:250])
    record(len(search_rows) > 0, "/v1/courses?q= data", json.dumps(payload)[:250])

    course_rows = courses or search_rows
    if not course_rows:
        print("\nTOTAL FAILURES:", len(failures) + 1)
        print("- Could not locate any course rows to continue the test")
        sys.exit(1)

    course_code = course_rows[0]["course_code"]
    encoded_course = quote(course_code, safe="")

    status, payload = get(f"/v1/courses/{encoded_course}")
    record(status == 200, "/v1/courses/{course_code} status", json.dumps(payload)[:250])
    if status == 200:
        record(
            payload.get("data", {}).get("course_code") == course_code,
            "/v1/courses/{course_code} match",
            json.dumps(payload)[:250],
        )

    status, payload = get("/v1/courses/NO_SUCH_COURSE_XYZ")
    record(status == 404, "/v1/courses/{course_code} 404", json.dumps(payload)[:250])

    special_course: str | None = None
    cursor = ""
    for _ in range(30):
        status, payload = get("/v1/courses", params={"limit": 200, "cursor": cursor})
        if status != 200:
            break
        rows = payload.get("data", [])
        for row in rows:
            code = row.get("course_code", "")
            if "/" in code:
                special_course = code
                break
        if special_course or not payload.get("page", {}).get("has_more"):
            break
        cursor = payload["page"]["next_cursor"]

    if special_course:
        encoded_special = quote(special_course, safe="")
        status, payload = get(f"/v1/courses/{encoded_special}")
        record(status == 200, "special course lookup with /", json.dumps(payload)[:250])
        status, payload = get(f"/v1/courses/{encoded_special}/papers", params={"limit": 1})
        record(status == 200, "special course papers with /", json.dumps(payload)[:250])
    else:
        print("INFO special course test skipped (no slash code found in scan)")

    paper_id: str | None = None
    selected_course: str | None = None
    cursor = ""
    for _ in range(10):
        status, payload = get("/v1/courses", params={"limit": 100, "cursor": cursor})
        if status != 200:
            break
        rows = payload.get("data", [])
        if not rows:
            break
        for row in rows:
            code = row.get("course_code", "")
            status2, payload2 = get(f"/v1/courses/{quote(code, safe='')}/papers", params={"limit": 1})
            if status2 == 200 and payload2.get("data"):
                selected_course = code
                paper_id = payload2["data"][0]["id"]
                break
        if paper_id or not payload.get("page", {}).get("has_more"):
            break
        cursor = payload["page"]["next_cursor"]

    record(paper_id is not None, "course with papers found", selected_course or "none")
    if not paper_id:
        print("\nTOTAL FAILURES:", len(failures))
        for name, detail in failures:
            print(f"- {name}: {detail}")
        sys.exit(1 if failures else 0)

    status, payload = get(f"/v1/courses/{quote(selected_course or '', safe='')}/papers", params={"limit": 5})
    record(status == 200, "/v1/courses/{course_code}/papers status", json.dumps(payload)[:250])
    record(isinstance(payload.get("data"), list), "/v1/courses/{course_code}/papers list", json.dumps(payload)[:250])

    status, payload = get(f"/v1/papers/{paper_id}")
    record(status == 200, "/v1/papers/{paper_id} status", json.dumps(payload)[:250])
    if status == 200:
        record(payload.get("data", {}).get("id") == paper_id, "/v1/papers/{paper_id} match", json.dumps(payload)[:250])

    status, payload = get("/v1/papers/00000000-0000-0000-0000-000000000000")
    record(status == 404, "/v1/papers/{paper_id} 404", json.dumps(payload)[:250])

    status, payload = get(f"/v1/papers/{paper_id}/files")
    files = payload.get("data", []) if status == 200 else []
    record(status == 200, "/v1/papers/{paper_id}/files status", json.dumps(payload)[:250])
    record(isinstance(files, list) and len(files) > 0, "/v1/papers/{paper_id}/files data", json.dumps(payload)[:250])

    file_id = files[0]["id"] if files else None
    if file_id:
        status, payload = get(f"/v1/files/{quote(file_id, safe='')}/download", params={"ttl_seconds": 900})
        record(status == 200, "/v1/files/{file_id}/download status", json.dumps(payload)[:250])
        if status == 200:
            data = payload.get("data", {})
            record(
                isinstance(data.get("download_url"), str) and data["download_url"].startswith("http"),
                "/v1/files/{file_id}/download url",
                json.dumps(payload)[:250],
            )
            record(
                data.get("url_type") in {"signed", "public"},
                "/v1/files/{file_id}/download type",
                json.dumps(payload)[:250],
            )

        status, payload = get(f"/v1/files/{quote(file_id, safe='')}/download", params={"ttl_seconds": 30})
        record(status == 422, "/v1/files/{file_id}/download ttl validation", json.dumps(payload)[:250])

    status, payload = get("/v1/files/00000000-0000-0000-0000-000000000000/download")
    record(status == 404, "/v1/files/{file_id}/download 404", json.dumps(payload)[:250])

    print(f"\nTOTAL FAILURES: {len(failures)}")
    if failures:
        for name, detail in failures:
            print(f"- {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
