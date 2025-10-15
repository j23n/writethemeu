# ABOUTME: Tests for Django template filters
# ABOUTME: Tests markdown rendering and HTML sanitization

from django.test import TestCase

from letters.templatetags import markdown_extras


class MarkdownFilterTests(TestCase):
    """Ensure Markdown rendering converts safely and strips disallowed markup."""

    def test_markdown_bold_rendering(self):
        rendered = markdown_extras.markdownify('**Hallo Welt**')
        self.assertIn('<strong>Hallo Welt</strong>', rendered)

    def test_markdown_strips_scripts(self):
        rendered = markdown_extras.markdownify('Test <script>alert(1)</script>')
        self.assertIn('Test', rendered)
        self.assertNotIn('<script>', rendered)

    def test_markdown_ordered_list(self):
        rendered = markdown_extras.markdownify('1. Eins\n2. Zwei')
        self.assertIn('<ol', rendered)
        self.assertIn('<li>Eins</li>', rendered)
        self.assertIn('<li>Zwei</li>', rendered)
