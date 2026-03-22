from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResponse(self._rows)


class _FakeSupabase:
    def __init__(self, table_rows):
        self._table_rows = table_rows

    def table(self, name):
        return _FakeQuery(self._table_rows.get(name, []))


class _FakeR2Client:
    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):  # noqa: N803
        return (
            f"https://signed.example/{Params['Bucket']}/{Params['Key']}"
            f"?expires={ExpiresIn}&method={ClientMethod}"
        )


class PublicUrlBehaviorTests(unittest.TestCase):
    def _load_api_server(self):
        if "api_server" in sys.modules:
            del sys.modules["api_server"]

        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-key",
        }

        with patch.dict(os.environ, env, clear=False), patch("supabase.create_client", return_value=_FakeSupabase({})):
            return importlib.import_module("api_server")

    def test_files_endpoint_enriches_public_url_when_base_configured(self):
        api_server = self._load_api_server()

        rows = [
            {
                "id": "f1",
                "paper_id": "p1",
                "storage_provider": "r2",
                "bucket": "bucket-a",
                "object_key": "pyqs/v1/20PCSE85J/My File.pdf",
                "source_pdf_url": "https://source.example/file.pdf",
                "public_url": None,
                "mime_type": "application/pdf",
                "size_bytes": 123,
                "sha256": None,
                "is_primary": True,
                "created_at": "2026-03-22T00:00:00+00:00",
            }
        ]

        api_server.supabase = _FakeSupabase({"paper_files": rows})
        with patch.dict(os.environ, {"R2_PUBLIC_BASE_URL": "https://pub.example.r2.dev/"}, clear=False):
            payload = api_server.list_paper_files("p1")

        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(
            payload["data"][0]["public_url"],
            "https://pub.example.r2.dev/pyqs/v1/20PCSE85J/My%20File.pdf",
        )

    def test_download_endpoint_prefers_public_url_and_sets_public_metadata(self):
        api_server = self._load_api_server()

        rows = [
            {
                "id": "f1",
                "bucket": "bucket-a",
                "object_key": "pyqs/v1/20PCSE85J/File.pdf",
                "storage_provider": "r2",
                "public_url": None,
                "mime_type": "application/pdf",
                "size_bytes": 123,
                "source_pdf_url": "https://source.example/file.pdf",
            }
        ]

        api_server.supabase = _FakeSupabase({"paper_files": rows})
        with patch.dict(os.environ, {"R2_PUBLIC_BASE_URL": "https://pub.example.r2.dev"}, clear=False):
            payload = api_server.get_file_download("f1", ttl_seconds=900)

        self.assertEqual(payload["data"]["url_type"], "public")
        self.assertIsNone(payload["data"]["expires_in"])
        self.assertEqual(
            payload["data"]["download_url"],
            "https://pub.example.r2.dev/pyqs/v1/20PCSE85J/File.pdf",
        )

    def test_download_endpoint_falls_back_to_signed_url_when_public_unavailable(self):
        api_server = self._load_api_server()

        rows = [
            {
                "id": "f2",
                "bucket": "bucket-b",
                "object_key": "pyqs/v1/20PCSE85J/File.pdf",
                "storage_provider": "r2",
                "public_url": None,
                "mime_type": "application/pdf",
                "size_bytes": 222,
                "source_pdf_url": "https://source.example/file2.pdf",
            }
        ]

        api_server.supabase = _FakeSupabase({"paper_files": rows})
        api_server.get_r2_client = lambda: _FakeR2Client()

        with patch.dict(os.environ, {"R2_PUBLIC_BASE_URL": ""}, clear=False):
            payload = api_server.get_file_download("f2", ttl_seconds=900)

        self.assertEqual(payload["data"]["url_type"], "signed")
        self.assertEqual(payload["data"]["expires_in"], 900)
        self.assertTrue(payload["data"]["download_url"].startswith("https://signed.example/"))


if __name__ == "__main__":
    unittest.main()
