import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from odoo import SUPERUSER_ID, Command, http
from odoo.exceptions import AccessError, UserError
from odoo.libs import pdf_raster
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from ..models import document_document_thumbnail
from .test_document_common import TransactionCaseDocuments
from odoo.addons.base.tests.test_pdf_raster import make_pdf


def _png(color):
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), color).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestDocumentsThumbnail(TransactionCaseDocuments):
    def test_thumbnail_survives_a_web_save(self):
        document = self.env["document.document"].create(
            {"name": "pic.png", "type": "binary", "datas": _png((10, 200, 10))}
        )
        self.env.cr.flush()
        self.assertEqual(document.thumbnail_status, "present")
        first = document.thumbnail
        self.assertTrue(first)

        result = document.web_save(
            {"datas": _png((10, 10, 200))}, {"thumbnail_status": {}}
        )

        self.assertEqual(
            result[0]["thumbnail_status"],
            "pending",
            "the new content is rendered before the save commits, after it answers",
        )
        self.env.cr.flush()
        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(document.thumbnail)
        self.assertNotEqual(document.thumbnail, first)

    def test_thumbnail_read_under_bin_size(self):
        document = self.env["document.document"].create(
            {"name": "pic.png", "type": "binary", "datas": _png((200, 30, 30))}
        )
        self.env.cr.flush()
        self.env.invalidate_all()

        self.assertEqual(
            document.with_context(bin_size=True).thumbnail_status, "present"
        )
        document.invalidate_recordset()
        self.assertTrue(base64.b64decode(document.thumbnail).startswith(b"\x89PNG"))

    def test_thumbnail_status_error_for_undecodable_content(self):
        document = self.env["document.document"].create(
            {
                "name": "not-an-image.png",
                "type": "binary",
                "datas": base64.b64encode(b"certainly not a png"),
            }
        )
        document.attachment_id.sudo().mimetype = "image/png"
        self.env.cr.flush()
        self.assertEqual(document.thumbnail_status, "error")
        self.assertFalse(document.thumbnail)


@tagged("post_install", "-at_install")
class TestDocumentsThumbnailRoutes(HttpCase, TransactionCaseDocuments):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = [
            cls.env.ref("base.group_user").id,
            cls.env.ref("document.group_documents_user").id,
        ]
        cls.manager = cls.env["res.users"].create(
            {
                "name": "audit_mgr",
                "login": "audit_mgr",
                "password": "audit_mgr",
                "email": "audit_mgr@t.test",
                "group_ids": [
                    Command.set(
                        groups + [cls.env.ref("document.group_documents_manager").id]
                    )
                ],
            }
        )
        cls.uploader = cls.env["res.users"].create(
            {
                "name": "audit_up",
                "login": "audit_up",
                "password": "audit_up",
                "email": "audit_up@t.test",
                "group_ids": [Command.set(groups)],
            }
        )
        cls.victim = cls.env["res.users"].create(
            {
                "name": "audit_vic",
                "login": "audit_vic",
                "password": "audit_vic",
                "email": "audit_vic@t.test",
                "group_ids": [Command.set(groups)],
            }
        )
        cls.viewer = cls.env["res.users"].create(
            {
                "name": "audit_view",
                "login": "audit_view",
                "password": "audit_view",
                "email": "audit_view@t.test",
                "group_ids": [Command.set(groups)],
            }
        )
        Doc = cls.env["document.document"]
        cls.folder = Doc.with_user(cls.manager).create(
            {"type": "folder", "name": "audit_folder", "user_folder_id": "COMPANY"}
        )
        cls.folder.action_update_access_rights(
            access_via_link="edit", partners={cls.uploader.partner_id: ("edit", False)}
        )
        cls.pdf = Doc.with_user(cls.manager).create(
            {
                "type": "binary",
                "name": "audit.pdf",
                "user_folder_id": "COMPANY",
                "datas": base64.b64encode(make_pdf()),
                "mimetype": "application/pdf",
            }
        )
        cls.pdf.action_update_access_rights(
            partners={cls.viewer.partner_id: ("view", False)}
        )

    def setUp(self):
        super().setUp()
        self.patch(pdf_raster, "available", lambda: False)

    def _post_thumbnail(self, payload):
        return self.url_open(
            f"/documents/document/{self.pdf.id}/update_thumbnail",
            headers={"Content-Type": "application/json"},
            data=json_dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {"document_id": self.pdf.id, "thumbnail": payload},
                }
            ),
        ).json()

    def test_s3_thumbnail_rejects_non_image(self):
        self.authenticate("audit_mgr", "audit_mgr")
        garbage = base64.b64encode(b"<svg onload=alert(1)>NOTIMAGE").decode()
        body = self._post_thumbnail(garbage)
        self.assertIn("error", body)
        self.pdf.invalidate_recordset()
        self.assertFalse(self.pdf.thumbnail)
        buffer = io.BytesIO()
        Image.new("RGB", (48, 48)).save(buffer, format="PNG")
        body = self._post_thumbnail(base64.b64encode(buffer.getvalue()).decode())
        self.assertNotIn("error", body)
        self.pdf.invalidate_recordset()
        self.assertEqual(self.pdf.thumbnail_status, "present")
        self.assertTrue(self.pdf.thumbnail)
        self.assertTrue(base64.b64decode(self.pdf.thumbnail).startswith(b"\x89PNG"))

    def test_a_viewer_cannot_store_a_thumbnail(self):
        self.authenticate("audit_view", "audit_view")
        buffer = io.BytesIO()
        Image.new("RGB", (48, 48)).save(buffer, format="PNG")

        body = self._post_thumbnail(base64.b64encode(buffer.getvalue()).decode())

        self.assertEqual(
            body.get("error", {}).get("data", {}).get("name"),
            "odoo.exceptions.AccessError",
        )
        self.pdf.invalidate_recordset()
        self.assertFalse(self.pdf.thumbnail)
        self.assertEqual(
            self.pdf.thumbnail_status,
            "client_generated",
            "and the document stays open for someone who may store one",
        )


def _oversized_png(side):
    buffer = io.BytesIO()
    Image.new("L", (side, side)).save(buffer, "PNG")
    return buffer.getvalue()


@tagged("post_install", "-at_install")
class TestDocumentsThumbnailUndecodable(TransactionCaseDocuments):
    def _create_with_content(self, name, raw, mimetype):
        attachment = (
            self.env["ir.attachment"]
            .with_context(no_document=True)
            .create({"name": name, "raw": raw, "mimetype": mimetype})
        )
        return self.env["document.document"].create(
            {"name": name, "type": "binary", "attachment_id": attachment.id}
        )

    def test_a_decompression_bomb_is_an_error_thumbnail_not_a_traceback(self):
        document = self._create_with_content(
            "bomb.png", _oversized_png(16000), "image/png"
        )
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "error")
        self.assertFalse(document.thumbnail)
        self.assertTrue(
            document.attachment_id,
            "the file is still stored; only its preview failed",
        )

    def test_undecodable_bytes_claiming_to_be_an_image(self):
        document = self._create_with_content(
            "claims.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 512, "image/png"
        )
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "error")
        self.assertFalse(document.thumbnail)

    def test_a_decodable_image_still_gets_its_thumbnail(self):
        document = self._create_with_content(
            "fine.png", base64.b64decode(_png((10, 200, 10))), "image/png"
        )
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(document.thumbnail)


@tagged("post_install", "-at_install")
class TestDocumentsThumbnailPublicUpload(HttpCase):
    def _request_document(self):
        return self.env["document.document"].create(
            {
                "name": "please-upload-here.txt",
                "type": "binary",
                "access_via_link": "edit",
            }
        )

    def _upload(self, document, filename, payload):
        return self.url_open(
            f"/documents/upload/{document.access_token}",
            data={"csrf_token": http.Request.csrf_token(self)},
            files={"ufile": (filename, io.BytesIO(payload), "image/png")},
        )

    @mute_logger(
        "odoo.http",
        "odoo.sql_db",
        "odoo.addons.document.models.document_document_thumbnail",
    )
    def test_an_unauthenticated_visitor_may_upload_an_undecodable_image(self):
        self.authenticate(None, None)
        document = self._request_document()
        buffer = io.BytesIO()
        Image.new("L", (16000, 16000)).save(buffer, "PNG")
        payload = buffer.getvalue()
        self.assertLess(
            len(payload),
            300 * 1024,
            "small on the wire is the point: no upload size limit bounds the "
            "pixel count",
        )

        response = self._upload(document, "bomb.png", payload)

        self.assertEqual(response.status_code, 200)
        document.invalidate_recordset()
        self.assertTrue(document.attachment_id, "the file is stored")
        self.assertEqual(document.mimetype, "image/png")
        self.assertEqual(document.thumbnail_status, "error")

    def test_the_same_route_with_a_decodable_image(self):
        self.authenticate(None, None)
        document = self._request_document()
        buffer = io.BytesIO()
        Image.new("RGB", (400, 300), (10, 200, 10)).save(buffer, "PNG")

        response = self._upload(document, "fine.png", buffer.getvalue())

        self.assertEqual(response.status_code, 200)
        document.invalidate_recordset()
        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(document.thumbnail)


@tagged("post_install", "-at_install")
class TestDocumentsThumbnailResolutionBound(TransactionCaseDocuments):
    def _upload_shaped_attachment(self, name, side, mode="RGB"):
        buffer = io.BytesIO()
        Image.new(mode, (side, side)).save(buffer, "PNG")
        return (
            self.env["ir.attachment"]
            .with_context(no_document=True, image_no_postprocess=True)
            .create({"name": name, "raw": buffer.getvalue(), "mimetype": "image/png"})
        )

    def test_an_image_past_the_resolution_bound_is_stored_but_not_previewed(self):
        attachment = self._upload_shaped_attachment("huge.png", 8000)
        self.assertLess(
            len(attachment.raw),
            1024 * 1024,
            "small on the wire, which is why a size limit does not catch it",
        )

        document = self.env["document.document"].create(
            {"name": "huge.png", "type": "binary", "attachment_id": attachment.id}
        )
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "error")
        self.assertFalse(document.thumbnail)
        self.assertEqual(
            document.attachment_id.raw,
            attachment.raw,
            "the file itself is untouched; only its preview is skipped",
        )

    def test_an_ordinary_image_on_the_same_path_still_gets_a_thumbnail(self):
        attachment = self._upload_shaped_attachment("normal.png", 2000)

        document = self.env["document.document"].create(
            {"name": "normal.png", "type": "binary", "attachment_id": attachment.id}
        )
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(document.thumbnail)


@tagged("post_install", "-at_install")
class TestDocumentsThumbnailStore(TransactionCaseDocuments):
    def _create(self, name, raw, mimetype, **values):
        return self.env["document.document"].create(
            {
                "name": name,
                "type": "binary",
                "folder_id": self.folder_a.id,
                "datas": base64.b64encode(raw),
                "mimetype": mimetype,
                **values,
            }
        )

    def _rows(self, checksum):
        return self.env["document.thumbnail"].search(
            [("document_id", "=", False), ("checksum", "=", checksum)]
        )

    def _jobs(self, checksum):
        return self.env["ir.job"].search(
            [("identity_key", "=", f"document.thumbnail:{checksum}")]
        )

    def _png_bytes(self, color):
        return base64.b64decode(_png(color))

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_a_pdf_is_rendered_by_a_job_as_the_system(self):
        document = self._create("report.pdf", make_pdf(), "application/pdf")
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "pending")
        job = self._jobs(document.checksum)
        self.assertEqual(len(job), 1)
        self.assertEqual(job.channel, "document_thumbnail")
        self.assertEqual(list(job.record_ids), [document.id])
        self.assertEqual(job.user_id.id, SUPERUSER_ID)

        document._job_render_thumbnails()

        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(base64.b64decode(document.thumbnail).startswith(b"\x89PNG"))

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_a_pdf_without_a_page_is_an_error_thumbnail(self):
        document = self._create("empty.pdf", make_pdf(pages=0), "application/pdf")
        self.env.cr.flush()

        document._job_render_thumbnails()

        self.assertEqual(document.thumbnail_status, "error")
        self.assertFalse(document.thumbnail)

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_a_render_out_of_time_is_asked_again_not_failed(self):
        document = self._create("report.pdf", make_pdf(), "application/pdf")
        self.env.cr.flush()
        timed_out = pdf_raster.Rendering(pdf_raster.Outcome.TIMED_OUT)
        self.patch(pdf_raster, "render_first_page", lambda *args: timed_out)

        document._job_render_thumbnails()

        self.assertFalse(self._rows(document.checksum))
        self.assertEqual(document.thumbnail_status, "pending")

    def _cloud_document(self, name, mimetype):
        types = dict(self.env["ir.attachment"]._fields["type"].selection)
        if "cloud_storage" not in types:
            self.skipTest("cloud_storage is not installed")
        attachment = (
            self.env["ir.attachment"]
            .with_context(no_document=True)
            .create(
                {
                    "name": name,
                    "type": "cloud_storage",
                    "url": f"https://bucket.test/{name}",
                    "mimetype": mimetype,
                }
            )
        )
        return self.env["document.document"].create(
            {
                "name": name,
                "type": "binary",
                "folder_id": self.folder_a.id,
                "attachment_id": attachment.id,
            }
        )

    def test_a_file_a_provider_holds_is_rendered_by_a_job(self):
        raw = self._png_bytes((1, 2, 3))
        document = self._cloud_document("cloud.png", "image/png")
        self.env.cr.flush()

        key = document.thumbnail_source_checksum
        self.assertFalse(document.checksum, "the database keeps no checksum of it")
        self.assertTrue(key.startswith("url:"), "its address names it")
        self.assertEqual(
            document.thumbnail_status,
            "pending",
            "a provider's blob is never fetched before the upload commits",
        )
        self.assertEqual(len(self._jobs(key)), 1)

        with patch.object(
            type(self.env["ir.attachment"]), "_get_content", lambda att, size=None: raw
        ):
            document._job_render_thumbnails()

        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(base64.b64decode(document.thumbnail).startswith(b"\x89PNG"))

    def test_a_preview_is_cached_under_what_it_shows(self):
        raw = self._png_bytes((4, 5, 6))
        document = self._cloud_document("cached.png", "image/png")
        self.env.cr.flush()
        before = document.thumbnail_unique
        self.assertTrue(
            before, "a provider's blob has no checksum, yet its preview a key"
        )

        with patch.object(
            type(self.env["ir.attachment"]), "_get_content", lambda att, size=None: raw
        ):
            document._job_render_thumbnails()

        self.assertTrue(document.thumbnail_unique)
        self.assertNotEqual(
            document.thumbnail_unique, before, "the rendering is a new answer"
        )
        shortcut = document.action_create_shortcut(self.folder_b.id)
        self.assertEqual(shortcut.thumbnail_unique, document.thumbnail_unique)

    def test_filing_a_pdf_a_provider_holds_downloads_nothing(self):
        self.env.cr.flush()
        Attachment = type(self.env["ir.attachment"])
        read = Attachment._get_content

        def download(attachment, size=None):
            if attachment.type == "cloud_storage":
                raise AssertionError("downloaded while filing")
            return read(attachment, size)

        with patch.object(Attachment, "_get_content", download):
            document = self._cloud_document("filed.pdf", "application/pdf")
            self.env.cr.flush()

        self.assertFalse(document.is_multipage)
        self.assertEqual(document.thumbnail_status, "pending")

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_the_render_tells_a_providers_pdf_page_count(self):
        document = self._cloud_document("pages.pdf", "application/pdf")
        self.env.cr.flush()
        self.assertFalse(document.is_multipage, "not downloaded to count, filed")
        written = document.write_date

        with patch.object(
            type(self.env["ir.attachment"]),
            "_get_content",
            lambda att, size=None: make_pdf(pages=3),
        ):
            document._job_render_thumbnails()

        self.assertTrue(document.is_multipage)
        self.assertEqual(document.thumbnail_status, "present")
        self.assertEqual(document.write_date, written)

    def test_a_provider_out_of_reach_leaves_the_file_for_later(self):
        document = self._cloud_document("cloud.jpg", "image/jpeg")
        self.env.cr.flush()

        def unreachable(attachment, size=None):
            raise UserError("no provider is configured")

        with (
            mute_logger("odoo.addons.document.models.document_document_thumbnail"),
            patch.object(type(self.env["ir.attachment"]), "_get_content", unreachable),
        ):
            document._job_render_thumbnails()

        self.assertFalse(self._rows(document.thumbnail_source_checksum))
        self.assertEqual(document.thumbnail_status, "pending")

    def test_no_renderer_leaves_the_pdf_to_the_browser(self):
        self.patch(pdf_raster, "available", lambda: False)
        document = self._create("report.pdf", make_pdf(), "application/pdf")
        self.env.cr.flush()

        self.assertEqual(document.thumbnail_status, "client_generated")
        self.assertFalse(self._jobs(document.checksum))
        self.assertEqual(
            document.thumbnail_source_checksum,
            document.checksum,
            "the content stays named, for the renderer installed later",
        )

    def test_documents_holding_one_content_share_one_rendering(self):
        raw = self._png_bytes((10, 200, 10))
        first = self._create("a.png", raw, "image/png")
        second = self._create("b.png", raw, "image/png")
        self.env.cr.flush()

        self.assertEqual(first.checksum, second.checksum)
        self.assertEqual(len(self._rows(first.checksum)), 1)
        self.assertEqual((first | second).mapped("thumbnail_status"), ["present"] * 2)
        self.assertEqual(first.thumbnail, second.thumbnail)

    def test_a_copy_shares_the_rendering(self):
        document = self._create("a.png", self._png_bytes((7, 7, 7)), "image/png")
        self.env.cr.flush()

        copy = document.copy()
        self.env.cr.flush()

        self.assertEqual(copy.thumbnail_status, "present")
        self.assertEqual(copy.thumbnail, document.thumbnail)
        self.assertEqual(len(self._rows(document.checksum)), 1)

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_documents_holding_one_pdf_queue_one_job(self):
        raw = make_pdf()
        first = self._create("a.pdf", raw, "application/pdf")
        self.env.cr.flush()
        self._create("b.pdf", raw, "application/pdf")
        self.env.cr.flush()

        self.assertEqual(len(self._jobs(first.checksum)), 1)

    def test_a_shortcut_shows_its_targets_thumbnail(self):
        target = self._create("a.png", self._png_bytes((200, 10, 10)), "image/png")
        shortcut = target.action_create_shortcut(self.folder_b.id)
        self.env.cr.flush()

        self.assertFalse(shortcut.thumbnail_source_checksum)
        self.assertEqual(shortcut.thumbnail_status, "present")
        self.assertEqual(shortcut.thumbnail, target.thumbnail)

    def test_new_content_is_rendered_and_the_old_rendering_collected(self):
        document = self._create("a.png", self._png_bytes((200, 10, 10)), "image/png")
        self.env.cr.flush()
        old_checksum = document.checksum
        old_thumbnail = document.thumbnail

        document.write({"datas": _png((10, 10, 200))})
        self.env.cr.flush()

        self.assertNotEqual(document.checksum, old_checksum)
        self.assertEqual(document.thumbnail_status, "present")
        self.assertNotEqual(document.thumbnail, old_thumbnail)
        self.assertTrue(self._rows(old_checksum))

        self.env["document.thumbnail"]._gc_unreferenced()

        self.assertFalse(self._rows(old_checksum))
        self.assertTrue(self._rows(document.checksum))

    def test_rows_are_reached_only_through_a_document(self):
        document = self._create("a.png", self._png_bytes((10, 10, 10)), "image/png")
        document.action_update_access_rights(
            partners={self.internal_user.partner_id: ("view", False)}
        )
        self.env.cr.flush()

        with self.assertRaises(AccessError):
            self.env["document.thumbnail"].with_user(self.internal_user).search([])
        as_viewer = document.with_user(self.internal_user)
        self.assertEqual(as_viewer.thumbnail_status, "present")
        self.assertTrue(as_viewer.thumbnail)

    def test_an_authored_thumbnail_wins_until_it_is_cleared(self):
        document = self._create("a.png", self._png_bytes((10, 200, 10)), "image/png")
        self.env.cr.flush()
        rendered = document.thumbnail
        authored = _png((1, 2, 3))

        document.thumbnail = authored

        self.assertEqual(document.thumbnail, authored)
        self.assertEqual(document.thumbnail_status, "present")

        document.thumbnail = False

        self.assertEqual(document.thumbnail, rendered)

    def test_a_browser_rendering_goes_stale_with_its_content(self):
        self.patch(pdf_raster, "available", lambda: False)
        document = self._create("a.pdf", make_pdf(), "application/pdf")
        document._store_own_thumbnail(_png((5, 5, 5)), "present")
        self.assertEqual(document.thumbnail_status, "present")

        document.write({"datas": base64.b64encode(make_pdf(pages=2))})

        self.assertEqual(
            document.thumbnail_status,
            "client_generated",
            "a rendering of the previous content shows nothing of this one",
        )

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_the_sweep_queues_what_the_queue_lost(self):
        document = self._create("a.pdf", make_pdf(), "application/pdf")
        self.env.cr.flush()
        self._jobs(document.checksum).unlink()

        self.env["document.document"]._cron_render_awaited_thumbnails()
        self.env["document.document"]._cron_render_awaited_thumbnails()

        self.assertEqual(len(self._jobs(document.checksum)), 1)

        document._job_render_thumbnails()
        self._jobs(document.checksum).unlink()
        self.env["document.document"]._cron_render_awaited_thumbnails()

        self.assertFalse(self._jobs(document.checksum), "rendered: nothing to sweep")

    def test_past_the_inline_cap_images_queue(self):
        self.patch(document_document_thumbnail, "INLINE_IMAGES", 2)
        self.env.cr.flush()
        documents = self.env["document.document"]
        for shade in range(4):
            documents |= self._create(
                f"{shade}.png", self._png_bytes((shade, 0, 0)), "image/png"
            )
        self.env.cr.flush()

        self.assertEqual(
            sorted(documents.mapped("thumbnail_status")),
            ["pending", "pending", "present", "present"],
        )
        queued = documents.filtered(lambda d: d.thumbnail_status == "pending")
        for document in queued:
            self.assertEqual(len(self._jobs(document.checksum)), 1)
        queued._job_render_thumbnails()
        self.assertEqual(set(documents.mapped("thumbnail_status")), {"present"})

    def test_a_rendering_raced_by_another_transaction_is_kept(self):
        document = self._create("a.png", self._png_bytes((9, 9, 9)), "image/png")
        self.env.cr.flush()

        document._store_rendered_thumbnail(document.checksum, b"\x89PNG other")

        self.assertEqual(len(self._rows(document.checksum)), 1)
        self.assertEqual(document.thumbnail_status, "present")

    def test_a_reader_of_the_document_reads_its_thumbnail_whatever_holds_the_file(self):
        cron = self.env["ir.cron"].search([], limit=1)
        attachment = self.env["ir.attachment"].create(
            {
                "name": "a.pdf",
                "raw": make_pdf(),
                "mimetype": "application/pdf",
                "res_model": "ir.cron",
                "res_id": cron.id,
            }
        )
        document = self.env["document.document"].create(
            {
                "name": "a.pdf",
                "type": "binary",
                "folder_id": self.folder_a.id,
                "attachment_id": attachment.id,
            }
        )
        document.action_update_access_rights(
            partners={self.internal_user.partner_id: ("view", False)}
        )
        self.env.cr.flush()
        as_viewer = document.with_user(self.internal_user)
        as_viewer.check_access("read")

        self.assertIn(as_viewer.thumbnail_status, ("pending", "client_generated"))
        self.assertFalse(as_viewer.thumbnail)
