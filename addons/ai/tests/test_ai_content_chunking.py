from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ai.models.ir_attachment import IrAttachment


@tagged("post_install", "-at_install")
class TestAiContentChunking(TransactionCase):
    def _attachment(self, text_content, mimetype="text/plain"):
        # index_content is storage-backed in the fork (direct writes don't
        # stick) — feed the text through raw so _get_index_content produces it for real
        return self.env["ir.attachment"].create(
            {"name": "doc.txt", "mimetype": mimetype, "raw": text_content.encode()}
        )

    def test_clean_text_normalizes_structure(self):
        """Check that NUL bytes and CRLF are stripped and wrapped lines join
        into a single paragraph."""
        raw = "First\x00 part\r\nof the paragraph\n\nSecond paragraph."
        cleaned = IrAttachment._clean_text(raw)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertIn("First part of the paragraph", cleaned)
        self.assertIn("Second paragraph.", cleaned)

    def test_clean_text_tightens_punctuation_spacing(self):
        """Check that whitespace before punctuation is removed."""
        cleaned = IrAttachment._clean_text("Hello , world !")
        self.assertEqual(cleaned, "Hello, world!")

    def test_chunk_text_short_input_single_chunk(self):
        """Check that a short text yields exactly one cleaned chunk."""
        chunks = IrAttachment._chunk_text("A short paragraph about nothing.")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "A short paragraph about nothing.")

    def test_chunk_text_respects_hard_maximum(self):
        """Check that a stream without sentence breaks is force-split by
        words under the hard max_chunk_size limit."""
        text = " ".join(f"word{i}" for i in range(3000))
        chunks = IrAttachment._chunk_text(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 5000)
        rejoined = " ".join(chunks)
        self.assertIn("word0", rejoined)
        self.assertIn("word2999", rejoined)

    def test_chunk_text_splits_an_oversized_paragraph_by_sentences(self):
        """Check that a paragraph over the target size splits on sentences."""
        # NOTE: the paragraph-merge branch of _chunk_text is unreachable —
        # _clean_text's final `\s+` collapse erases the newlines it just
        # inserted between paragraphs, so split("\n") always yields one
        # paragraph. Everything routes through the oversized-paragraph
        # sentence split asserted here; cover the merge branch once the
        # model defect is fixed (tracked under task t24776).
        paragraph = "Sentence with some words. " * 120  # ~3100 chars
        chunks = IrAttachment._chunk_text(paragraph)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(
                len(chunk), 1500, "sentence chunks honor the target size"
            )
        self.assertEqual(" ".join(chunks), paragraph.strip())

    def test_attachment_content_short_text_is_discarded(self):
        """Check that content of exactly 10 characters is still noise."""
        attachment = self._attachment("ten chars!")
        self.assertIsNone(attachment._get_attachment_content())

    def test_attachment_content_needs_word_variety(self):
        """Check that content with fewer than two distinct words is discarded
        even when long enough."""
        attachment = self._attachment("data data data data data data")
        self.assertIsNone(attachment._get_attachment_content())

    def test_attachment_content_rejects_multi_record(self):
        """Check that reading the content of several attachments at once is
        refused by the singleton guard."""
        attachments = self._attachment("First document body.") | self._attachment(
            "Second document body."
        )
        with self.assertRaisesRegex(ValueError, "Expected singleton"):
            attachments._get_attachment_content()

    def test_attachment_content_returns_plain_text(self):
        """Check that regular indexed text is returned untouched for
        non-tabular mimetypes."""
        attachment = self._attachment("A perfectly valid indexed document body.")
        self.assertEqual(
            attachment._get_attachment_content(),
            "A perfectly valid indexed document body.",
        )
