"""Offline classification tests: no model service required."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_embedding_classifier as classifier
from core import discovery_fts


class ClassificationTests(unittest.TestCase):
    def test_prefixes_and_similarity(self):
        self.assertEqual(classifier._prefix("example", "classification"),
                         "task: classification | query: example")
        self.assertEqual(classifier._prefix("example", "clustering"),
                         "task: clustering | query: example")
        self.assertAlmostEqual(classifier._cosine([1, 0], [1, 0]), 1.0)

    def test_every_unit_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.sqlite"
            db = sqlite3.connect(str(path))
            discovery_fts._init(db)
            for index, body in enumerate(("", "A product provides capabilities.")):
                discovery_fts._put(db, "jira:issue:APS-{}".format(index),
                                   "APS-{}".format(index), "APS", "issue",
                                   None, None, "Example title", body,
                                   "jira:APS-{}".format(index))
            db.commit()
            db.close()

            calls = []
            def fake_embeddings(endpoint, model, values, timeout):
                calls.append(values)
                return [[1.0, float(i + 1) / 100] for i in range(len(values))]
            with patch.object(classifier, "_embeddings", side_effect=fake_embeddings):
                first = classifier.classify(path, "APS", batch_size=1)
                second = classifier.classify(path, "APS", batch_size=1)
            self.assertEqual(first["total"], 2)
            self.assertEqual(first["classified"], 2)
            self.assertEqual(second["classified"], 0)
            self.assertEqual(second["cached"], 2)
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(text.startswith("task: clustering | query:")
                                for batch in calls for text in batch))
            db = sqlite3.connect(str(path))
            results = [json.loads(row[0]) for row in db.execute(
                "SELECT categories_json FROM discovery_classifications ORDER BY doc_id")]
            db.close()
            self.assertEqual(len(results), 2)
            self.assertTrue(results[0]["title_only"])
            self.assertFalse(results[1]["title_only"])
            self.assertEqual(len(results[0]["top_categories"]), 2)

    def test_embedding_requests_are_single_input(self):
        seen = []
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
        def send(endpoint, json, timeout):
            seen.append(json["input"])
            self.assertIsInstance(json["input"], str)
            return Response()
        with patch.object(classifier.requests, "post", side_effect=send):
            vectors = classifier._embeddings("http://127.0.0.1:13305/v1/embeddings",
                                             "embed-gemma-300m-FLM",
                                             ["first", "second"], 240)
        self.assertEqual(seen, ["first", "second"])
        self.assertEqual(len(vectors), 2)

    def test_remote_endpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            classifier.classify("unused.sqlite", "APS",
                                endpoint="https://example.com/v1/embeddings")


if __name__ == "__main__":
    unittest.main()
