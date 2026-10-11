import time
import unittest
from unittest.mock import patch

from odoo.libs import pdf_raster
from odoo.tests.common import BaseCase

PNG = b"\x89PNG\r\n\x1a\n"


def make_pdf(pages: int = 1, operators: int = 0) -> bytes:
    content = b"0.1 w 0 0 m 600 800 l 600 0 l 0 800 l S\n" * operators
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(b"%d 0 R" % (4 + n) for n in range(pages))
        + b"] /Count %d >>" % pages,
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    objects += [
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 3 0 R >>"
    ] * pages
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


@unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
class TestPdfRaster(BaseCase):
    def test_renders_the_first_page_as_a_png(self):
        rendering = pdf_raster.render_first_page(make_pdf(pages=3), 400, 280)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.RENDERED)
        self.assertTrue(rendering.png.startswith(PNG))
        self.assertEqual(rendering.pages, 3)

    def test_malformed_and_empty_input_fail(self):
        for content in (b"", b"certainly not a pdf", b"%PDF-1.4\n" + b"\x00" * 64):
            with self.subTest(content=content[:16]):
                rendering = pdf_raster.render_first_page(content, 400, 280)
                self.assertEqual(rendering.outcome, pdf_raster.Outcome.FAILED)
                self.assertEqual(rendering.png, b"")

    def test_a_pdf_without_pages_is_refused(self):
        rendering = pdf_raster.render_first_page(make_pdf(pages=0), 400, 280)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.REFUSED)

    def test_an_encrypted_pdf_is_refused(self):
        import pymupdf

        with pymupdf.open(stream=make_pdf(), filetype="pdf") as pdf:
            encrypted = pdf.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner",
                user_pw="user",
            )

        rendering = pdf_raster.render_first_page(encrypted, 400, 280)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.REFUSED)

    def test_the_cpu_limit_ends_the_render(self):
        heavy = make_pdf(operators=20_000)
        limits = pdf_raster.Limits(cpu_seconds=1)

        started = time.monotonic()
        rendering = pdf_raster.render_first_page(heavy, 400, 280, limits)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.FAILED)
        self.assertLess(time.monotonic() - started, 5)

    def test_the_wall_limit_ends_the_render(self):
        heavy = make_pdf(operators=20_000)
        limits = pdf_raster.Limits(wall_seconds=0.5)

        started = time.monotonic()
        rendering = pdf_raster.render_first_page(heavy, 400, 280, limits)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.TIMED_OUT)
        self.assertLess(time.monotonic() - started, 3)

    def test_the_memory_limit_fails_the_pdf_not_the_renderer(self):
        limits = pdf_raster.Limits(memory_bytes=1)

        rendering = pdf_raster.render_first_page(make_pdf(), 400, 280, limits)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.FAILED)

    def test_an_oversized_output_fails(self):
        limits = pdf_raster.Limits(output_bytes=16)

        rendering = pdf_raster.render_first_page(make_pdf(), 400, 280, limits)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.FAILED)


class TestPdfRasterUnavailable(BaseCase):
    def test_no_renderer_spawns_nothing(self):
        with (
            patch.object(pdf_raster, "available", return_value=False),
            patch.object(pdf_raster.subprocess, "run") as run,
        ):
            rendering = pdf_raster.render_first_page(make_pdf(), 400, 280)

        self.assertEqual(rendering.outcome, pdf_raster.Outcome.UNAVAILABLE)
        run.assert_not_called()
