"""Confluence content is scoped, searchable and honestly coverage-accounted."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_index, discovery_fts


class ConfluenceIndexTests(unittest.TestCase):
    def test_index_search_repeat_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.sqlite"
            inventory = {"inventory": {
                "coverage": "partial",
                "scopes": [{"space": "DOC", "status": "truncated",
                            "detail": "Additional pages beyond cap"}],
                "pages": [{"id": "42", "space": "DOC", "title": "Product overview"}]}}
            page = {"id": "42", "space": {"key": "DOC"},
                    "title": "Secure Data Exchange (SDX)",
                    "version": {"when": "2026-10-01"},
                    "body": {"storage": {"value": "<h2>Introduction</h2><p>Secure Data Exchange (SDX)</p>"}}}
            def fake_build(cfg, report, cap=100):
                report.update(inventory)
                return report
            with patch.object(discovery_confluence_index.discovery_inventory,
                              "build", side_effect=fake_build):
                with patch.object(discovery_confluence_index.sources,
                                  "fetch_confluence_page", return_value=page):
                    first = discovery_confluence_index.index({}, path)
                    second = discovery_confluence_index.index({}, path)
            self.assertEqual(first["indexed"], 1)
            self.assertEqual(first["changed"], 1)
            self.assertFalse(first["complete"])
            self.assertEqual(second["changed"], 0)
            found = discovery_fts.search(path, '"Secure Data Exchange"')
            self.assertEqual(found[0]["citation"], "confluence:42")
            self.assertEqual(found[0]["kind"], "confluence_page")
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute(
                    "SELECT source FROM discovery_fts_documents").fetchone()[0],
                    "confluence")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
