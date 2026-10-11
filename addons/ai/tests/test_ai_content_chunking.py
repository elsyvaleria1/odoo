from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ai.models.ir_attachment import IrAttachment


@tagged("post_install", "-at_install")
class TestAiContentChunking(TransactionCase):
    def _attachment(self, text_content, mimetype="text/plain"):
        return self.env["ir.attachment"].create(
            {"name": "doc.txt", "mimetype": mimetype, "raw": text_content.encode()}
        )

    def test_clean_text_normalizes_structure(self):
        raw = "First\x00 part\r\nof the paragraph\n\nSecond paragraph."
        cleaned = IrAttachment._clean_text(raw)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertIn("First part of the paragraph", cleaned)
        self.assertIn("Second paragraph.", cleaned)

    def test_clean_text_tightens_punctuation_spacing(self):
        cleaned = IrAttachment._clean_text("Hello , world !")
        self.assertEqual(cleaned, "Hello, world!")

    def test_chunk_text_short_input_single_chunk(self):
        chunks = IrAttachment._chunk_text("A short paragraph about nothing.")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "A short paragraph about nothing.")

    def test_chunk_text_respects_hard_maximum(self):
        text = " ".join(f"word{i}" for i in range(3000))
        chunks = IrAttachment._chunk_text(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 5000)
        rejoined = " ".join(chunks)
        self.assertIn("word0", rejoined)
        self.assertIn("word2999", rejoined)

    def test_chunk_text_splits_an_oversized_paragraph_by_sentences(self):
        paragraph = "Sentence with some words. " * 120
        chunks = IrAttachment._chunk_text(paragraph)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(
                len(chunk), 1500, "sentence chunks honor the target size"
            )
        self.assertEqual(" ".join(chunks), paragraph.strip())

    def test_attachment_content_short_text_is_discarded(self):
        attachment = self._attachment("ten chars!")
        self.assertIsNone(attachment._get_attachment_content())

    def test_attachment_content_needs_word_variety(self):
        attachment = self._attachment("data data data data data data")
        self.assertIsNone(attachment._get_attachment_content())

    def test_attachment_content_rejects_multi_record(self):
        attachments = self._attachment("First document body.") | self._attachment(
            "Second document body."
        )
        with self.assertRaisesRegex(ValueError, "Expected singleton"):
            attachments._get_attachment_content()

    def test_attachment_content_returns_plain_text(self):
        attachment = self._attachment("A perfectly valid indexed document body.")
        self.assertEqual(
            attachment._get_attachment_content(),
            "A perfectly valid indexed document body.",
        )
