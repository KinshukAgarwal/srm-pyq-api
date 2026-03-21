#!/usr/bin/env python3
"""API layer for SRM PYQ dataset.

Exposes read APIs for courses, papers, files, and download URL generation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from supabase import create_client


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""

load_env_file(Path(".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SUPABASE_URL = get_env("SUPABASE_URL", "SUPABASE_PROJECT_URL") or (
    f"https://{get_env('PROJECT_ID')}.supabase.co" if get_env("PROJECT_ID") else ""
)
SUPABASE_KEY = get_env(
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_ROLE",
    "API_KEY_SUPABASE",
)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase credentials in environment")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
COURSE_FIELDS = "id,course_code,course_name,department,program,semester,is_active"
COURSE_MIN_FIELDS = "id,course_code,course_name"


def get_r2_client() -> Any:
    endpoint = get_env("R2_ENDPOINT_URL", "CLOUDFLARER2_S3_API")
    if not endpoint:
        endpoint = get_env("CLOUDFLARE_ENDPOINTS").split("#", 1)[0].strip().strip('"')

    access_key = get_env("R2_ACCESS_KEY_ID", "CLOUDFLARE_ACCESS_KEY")
    secret_key = get_env("R2_SECRET_ACCESS_KEY", "CLOUDFLARE_SECRET_ACCESS_KEY")

    if not endpoint or not access_key or not secret_key:
        raise RuntimeError("Missing R2 credentials in environment")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=BotoConfig(signature_version="s3v4", max_pool_connections=32),
    )


app = FastAPI(title="SRM PYQ API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/v1/courses")
def list_courses(
    q: str = Query(default="", description="Search by course_code/course_name"),
    cursor: str = Query(default="", description="Cursor = last seen course_code"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    query = supabase.table("courses").select(COURSE_FIELDS)

    if q:
        escaped = q.replace(",", " ")
        query = query.or_(f"course_code.ilike.%{escaped}%,course_name.ilike.%{escaped}%")

    if cursor:
        query = query.gt("course_code", cursor)

    response = query.order("course_code").limit(limit + 1).execute()
    rows = response.data or []
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    next_cursor = rows[-1]["course_code"] if has_more and rows else None
    return {
        "data": rows,
        "page": {
            "has_more": has_more,
            "next_cursor": next_cursor,
            "limit": limit,
        },
    }


def fetch_course_by_code(course_code: str) -> dict[str, Any]:
    response = (
        supabase.table("courses")
        .select(COURSE_FIELDS)
        .eq("course_code", course_code)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=404, detail=f"Course not found: {course_code}")
    return rows[0]


@app.get("/v1/courses/{course_code:path}/papers")
def list_course_papers(
    course_code: str,
    year: int | None = Query(default=None),
    term: str = Query(default=""),
    cursor: str = Query(default="", description="Cursor = last seen source_item_url"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    course = fetch_course_by_code(course_code)
    query = supabase.table("papers").select(
        "id,course_id,title,exam_year,exam_month,exam_term,session_label,"
        "source_subject_url,source_item_url,publisher,created_at"
    )
    query = query.eq("course_id", course["id"])

    if year is not None:
        query = query.eq("exam_year", year)
    if term:
        query = query.eq("exam_term", term)
    if cursor:
        query = query.gt("source_item_url", cursor)

    response = query.order("source_item_url").limit(limit + 1).execute()
    rows = response.data or []
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    next_cursor = rows[-1]["source_item_url"] if has_more and rows else None
    return {
        "data": rows,
        "course": {
            "id": course["id"],
            "course_code": course["course_code"],
            "course_name": course["course_name"],
        },
        "page": {
            "has_more": has_more,
            "next_cursor": next_cursor,
            "limit": limit,
        },
    }


@app.get("/v1/courses/{course_code:path}")
def get_course(course_code: str) -> dict[str, Any]:
    return {"data": fetch_course_by_code(course_code)}


@app.get("/v1/papers/{paper_id}")
def get_paper(paper_id: str) -> dict[str, Any]:
    response = (
        supabase.table("papers")
        .select(
            "id,course_id,title,exam_year,exam_month,exam_term,session_label,"
            "source_subject_url,source_item_url,publisher,metadata_json,created_at"
        )
        .eq("id", paper_id)
        .limit(1)
        .execute()
    )
    papers = response.data or []
    if not papers:
        raise HTTPException(status_code=404, detail=f"Paper not found: {paper_id}")

    paper = papers[0]
    course = (
        supabase.table("courses")
        .select(COURSE_MIN_FIELDS)
        .eq("id", paper["course_id"])
        .limit(1)
        .execute()
    )
    course_rows = course.data or []

    return {
        "data": {
            **paper,
            "course": course_rows[0] if course_rows else None,
        }
    }


@app.get("/v1/papers/{paper_id}/files")
def list_paper_files(paper_id: str) -> dict[str, Any]:
    response = (
        supabase.table("paper_files")
        .select(
            "id,paper_id,storage_provider,bucket,object_key,source_pdf_url,"
            "public_url,mime_type,size_bytes,sha256,is_primary,created_at"
        )
        .eq("paper_id", paper_id)
        .order("source_pdf_url")
        .execute()
    )
    rows = response.data or []
    return {"data": rows}


@app.get("/v1/files/{file_id}/download")
def get_file_download(file_id: str, ttl_seconds: int = Query(default=900, ge=60, le=3600)) -> dict[str, Any]:
    response = (
        supabase.table("paper_files")
        .select(
            "id,bucket,object_key,public_url,mime_type,size_bytes,source_pdf_url"
        )
        .eq("id", file_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    file_row = rows[0]

    if file_row.get("public_url"):
        return {
            "data": {
                "file_id": file_row["id"],
                "download_url": file_row["public_url"],
                "url_type": "public",
                "expires_in": None,
            }
        }

    try:
        r2_client = get_r2_client()
        signed_url = r2_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": file_row["bucket"],
                "Key": file_row["object_key"],
            },
            ExpiresIn=ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not generate signed URL: {exc}") from exc

    return {
        "data": {
            "file_id": file_row["id"],
            "download_url": signed_url,
            "url_type": "signed",
            "expires_in": ttl_seconds,
        }
    }


@app.exception_handler(Exception)
def fallback_exception_handler(_: Any, exc: Exception) -> JSONResponse:
    logging.exception("Unhandled API error: %s", exc)
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": str(exc)}})
