# SRM PYQ API — Integration Contract for AI + App Developers

Purpose: this file is an API consumer reference.
Use it when building your own product, chatbot, website, or agent that needs SRM paper metadata and PDF access.

Base URL (production):
- https://srm-pyq-api.onrender.com

API style:
- Read-only HTTP JSON API
- No auth currently required
- Cursor-based pagination on list endpoints

---

## 1) Endpoint index

1. Health
- GET /health

2. Courses
- GET /v1/courses?q=&cursor=&limit=
- GET /v1/courses/{course_code}

3. Papers
- GET /v1/courses/{course_code}/papers?year=&term=&cursor=&limit=
- GET /v1/papers/{paper_id}

4. Files
- GET /v1/papers/{paper_id}/files
- GET /v1/files/{file_id}/download?ttl_seconds=900

---

## 2) Data models

### 2.1 Course

```json
{
   "id": "uuid",
   "course_code": "string",
   "course_name": "string",
   "department": "string|null",
   "program": "string|null",
   "semester": "number|null",
   "is_active": true
}
```

### 2.2 Paper

```json
{
   "id": "uuid",
   "course_id": "uuid",
   "title": "string",
   "exam_year": "number|null",
   "exam_month": "number|null",
   "exam_term": "string|null",
   "session_label": "string|null",
   "source_subject_url": "string|null",
   "source_item_url": "string",
   "publisher": "string|null",
   "created_at": "iso-datetime"
}
```

### 2.3 File

```json
{
   "id": "uuid",
   "paper_id": "uuid",
   "storage_provider": "r2",
   "bucket": "string",
   "object_key": "string",
   "source_pdf_url": "string|null",
   "public_url": "string|null",
   "mime_type": "application/pdf",
   "size_bytes": "number|null",
   "sha256": "string|null",
   "is_primary": true,
   "created_at": "iso-datetime"
}
```

### 2.4 Download response

```json
{
   "data": {
      "file_id": "uuid",
      "download_url": "https://...",
      "url_type": "signed|public",
      "expires_in": 900
   }
}
```

Notes:
- If url_type=public, expires_in can be null.
- If url_type=signed, expires_in is usually the ttl_seconds used.

---

## 3) Endpoint details

### GET /health

Purpose:
- Service liveness check

Response:
```json
{ "ok": true }
```

---

### GET /v1/courses

Query params:
- q (optional, string): search by course_code or course_name
- cursor (optional, string): last seen course_code
- limit (optional, int): 1 to 200, default 50

Response shape:
```json
{
   "data": ["Course", "..."],
   "page": {
      "has_more": true,
      "next_cursor": "string|null",
      "limit": 50
   }
}
```

---

### GET /v1/courses/{course_code}

Path param:
- course_code (string, URL-encode when needed)

Response shape:
```json
{
   "data": "Course"
}
```

404 when course is not found.

---

### GET /v1/courses/{course_code}/papers

Path param:
- course_code (string, URL-encode when needed)

Query params:
- year (optional, int)
- term (optional, string)
- cursor (optional, string): last seen source_item_url
- limit (optional, int): 1 to 200, default 50

Response shape:
```json
{
   "data": ["Paper", "..."],
   "course": {
      "id": "uuid",
      "course_code": "string",
      "course_name": "string"
   },
   "page": {
      "has_more": true,
      "next_cursor": "string|null",
      "limit": 50
   }
}
```

---

### GET /v1/papers/{paper_id}

Path param:
- paper_id (uuid)

Response shape:
```json
{
   "data": {
      "id": "uuid",
      "course_id": "uuid",
      "title": "string",
      "exam_year": "number|null",
      "exam_month": "number|null",
      "exam_term": "string|null",
      "session_label": "string|null",
      "source_subject_url": "string|null",
      "source_item_url": "string",
      "publisher": "string|null",
      "metadata_json": {
         "authors": "string",
         "keywords": "string",
         "series_report_no": "string",
         "issue_date": "string"
      },
      "created_at": "iso-datetime",
      "course": {
         "id": "uuid",
         "course_code": "string",
         "course_name": "string"
      }
   }
}
```

404 when paper is not found.

---

### GET /v1/papers/{paper_id}/files

Path param:
- paper_id (uuid)

Response shape:
```json
{
   "data": ["File", "..."]
}
```

Behavior note:
- For `storage_provider = r2`, `public_url` may be computed at response time using `R2_PUBLIC_BASE_URL + object_key` when DB `public_url` is null.

---

### GET /v1/files/{file_id}/download

Path param:
- file_id (uuid)

Query params:
- ttl_seconds (optional, int): 60 to 3600, default 900

Response shape:
```json
{
   "data": {
      "file_id": "uuid",
      "download_url": "https://...",
      "url_type": "signed|public",
      "expires_in": "number|null"
   }
}
```

Errors:
- 404 if file_id not found
- 422 if ttl_seconds is out of allowed range

Public URL priority:
- If `public_url` is available (stored or computed), response returns `url_type = public` and `expires_in = null`.
- Otherwise API falls back to signed URL flow (`url_type = signed`).

---

## 4) Integration patterns for AI agents

Pattern A: search courses, then drill down
1. Call /v1/courses?q=<user_query>&limit=20
2. Pick best course_code
3. Call /v1/courses/{course_code}/papers?limit=20
4. For each paper, call /v1/papers/{paper_id}/files
5. Get downloadable link from /v1/files/{file_id}/download

Pattern B: infinite list sync with cursor
1. Start with cursor empty
2. Call list endpoint with limit N
3. Process data
4. If has_more=true, continue with next_cursor
5. Stop when has_more=false

Pattern C: safe download handling
1. Always request a fresh /download URL before fetching PDF
2. Treat signed URLs as short-lived
3. Re-request /download URL on expiry

---

## 5) Error model and retry behavior

Common statuses:
- 200 success
- 404 resource not found
- 422 validation error (for example invalid ttl_seconds)
- 500 transient server issue

Retry guidance:
- Retry 500/timeout with exponential backoff
- Do not retry 404/422 without fixing request

---

## 6) Example requests (production)

Health:
- https://srm-pyq-api.onrender.com/health

List courses:
- https://srm-pyq-api.onrender.com/v1/courses?limit=5

Course with special chars (URL-encoded):
- https://srm-pyq-api.onrender.com/v1/courses/%2C20PCSE85J

Papers for a course:
- https://srm-pyq-api.onrender.com/v1/courses/%2C20PCSE85J/papers?limit=5

Files for a paper:
- https://srm-pyq-api.onrender.com/v1/papers/5aebb8f3-2946-4442-81ce-af1a64efad42/files

Get downloadable PDF link:
- https://srm-pyq-api.onrender.com/v1/files/603c3731-865a-43eb-96c1-d46da96f5814/download?ttl_seconds=900

---

## 7) AI prompt snippet (copy for agents)

You can give this to any coding AI:

"Use SRM PYQ API at https://srm-pyq-api.onrender.com. Discover course using /v1/courses with q. Fetch papers via /v1/courses/{course_code}/papers. Fetch files via /v1/papers/{paper_id}/files. Fetch download URLs via /v1/files/{file_id}/download. Respect pagination via page.has_more and page.next_cursor. URL-encode path params. Handle 404 and 422 gracefully."

---

## 8) Stability expectations

- Existing endpoint paths are intended for integration use.
- JSON response fields documented here should be treated as the contract.
- If new fields are added in future, consumers should ignore unknown keys safely.
