"""Citation tags become links, and unknown tags are removed."""

import unittest

from core import citations


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.cmap = {
            "APS-10": ("APS-10", "https://example/browse/APS-10"),
            "D1": ("Decision: certificate rotation cadence", "https://example/pages/1001"),
        }

    def test_a_key_becomes_a_link(self):
        text, removed = citations.resolve("Shipped. [APS-10]", self.cmap)
        self.assertEqual(text, "Shipped. [APS-10](https://example/browse/APS-10)")
        self.assertEqual(removed, 0)

    def test_a_doc_tag_uses_the_title(self):
        text, removed = citations.resolve("Decided. [D1]", self.cmap)
        self.assertIn("[Decision: certificate rotation cadence](https://example/pages/1001)", text)
        self.assertEqual(removed, 0)

    def test_a_comma_list_becomes_two_links(self):
        text, _removed = citations.resolve("Both. [APS-10, D1]", self.cmap)
        self.assertIn("[APS-10](https://example/browse/APS-10)", text)
        self.assertIn("[Decision: certificate rotation cadence](https://example/pages/1001)", text)

    def test_an_unknown_tag_is_removed_and_counted(self):
        text, removed = citations.resolve("Nope. [APS-99]", self.cmap)
        self.assertEqual(text, "Nope. ")
        self.assertEqual(removed, 1)

    def test_a_key_outside_brackets_stays(self):
        text, removed = citations.resolve("See APS-10 for the work.", self.cmap)
        self.assertEqual(text, "See APS-10 for the work.")
        self.assertEqual(removed, 0)

    def test_doc_tags_are_numbered_by_page_id(self):
        docs = [{"uid": "confluence:20", "source": "Confluence"},
                {"uid": "confluence:3", "source": "Confluence"}]
        citations.assign_doc_tags(docs)
        by_uid = {doc["uid"]: doc["ref"] for doc in docs}
        self.assertEqual(by_uid["confluence:3"], "D1")
        self.assertEqual(by_uid["confluence:20"], "D2")


if __name__ == "__main__":
    unittest.main()
