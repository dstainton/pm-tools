import unittest

from commands import publish


class MarkdownTests(unittest.TestCase):
    def test_headings_lists_and_paragraphs(self):
        html = publish.markdown_to_storage(
            "# Title\n\n## Section\n\n- one\n- two\n\nA paragraph.\n")
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<h2>Section</h2>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<p>A paragraph.</p>", html)

    def test_escapes_html(self):
        html = publish.markdown_to_storage("# <script>")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
