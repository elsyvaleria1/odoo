import base64
import io
import uuid
from unittest.mock import patch

from PIL import Image

from odoo.exceptions import MissingError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.pdf import to_pdf_stream


@tagged("post_install", "-at_install")
class TestCloudStorage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attachment = cls.env["ir.attachment"].create(
            {"name": "cloud.txt", "raw": b"payload"}
        )

    def _cloud_attachment(self, name, mimetype):
        remote = self.env["ir.attachment"].create({"name": name, "mimetype": mimetype})
        remote.write({"type": "cloud_storage", "url": "https://bucket/blob"})
        return remote

    def _configured(self, content):
        def fake_request(egress, method, url, *, purpose, headers=None, **kwargs):
            class Response:
                def raise_for_status(self):
                    return None

            Response.content = content
            return Response()

        return (
            patch.object(
                type(self.env["res.config.settings"]),
                "_get_cloud_storage_configuration",
                lambda self: {"provider": "fake"},
            ),
            patch.object(
                type(self.env["ir.attachment"]),
                "_generate_cloud_storage_download_info",
                lambda self, content_disposition=None: {
                    "url": "https://bucket/blob?signed",
                    "time_to_expiry": 300,
                },
            ),
            patch.object(type(self.env["ir.egress"]), "request", fake_request),
        )

    def test_generate_url_is_abstract(self):
        """The provider-agnostic base leaves blob URL generation unimplemented."""
        with self.assertRaises(NotImplementedError):
            self.attachment._generate_cloud_storage_url()

    def test_generate_download_info_is_abstract(self):
        """The base module has no download-info implementation."""
        with self.assertRaises(NotImplementedError):
            self.attachment._generate_cloud_storage_download_info()

    def test_generate_upload_info_is_abstract(self):
        """The base module has no upload-info implementation."""
        with self.assertRaises(NotImplementedError):
            self.attachment._generate_cloud_storage_upload_info()

    def test_post_add_create_without_provider_raises(self):
        """Flagging an attachment as cloud storage needs an enabled provider."""
        self.env["ir.config_parameter"].sudo().set_param("cloud_storage_provider", "")
        with self.assertRaises(UserError):
            self.attachment._post_add_create(cloud_storage=True)

    def test_blob_name_is_scoped_to_attachment(self):
        """The blob name embeds the attachment id, a uuid4, and the file name."""
        blob_name = self.attachment._generate_cloud_storage_blob_name()
        prefix, token, name = blob_name.split("/")
        self.assertEqual(prefix, str(self.attachment.id))
        self.assertEqual(name, self.attachment.name)
        # a malformed token would raise ValueError and fail the test
        self.assertEqual(str(uuid.UUID(token)), token)

    def test_get_values_reports_min_file_size_in_mb(self):
        """Settings expose the byte threshold converted to megabytes."""
        self.env["ir.config_parameter"].sudo().set_param(
            "cloud_storage_min_file_size", "30000000"
        )
        values = self.env["res.config.settings"].get_values()
        self.assertEqual(values["cloud_storage_min_file_size_mb"], 30)

    def test_documents_are_not_excluded_from_the_cloud(self):
        """Only main-attachment models keep their bytes on the server."""
        unsupported = self.env["ir.attachment"]._get_cloud_storage_unsupported_models()
        self.assertNotIn("document.document", unsupported)

    def test_get_content_downloads_the_blob_a_provider_holds(self):
        """A cloud attachment has no local bytes: the fetch goes and gets them."""
        remote = self.env["ir.attachment"].create({"name": "remote.pdf"})
        remote.type = "cloud_storage"
        self.assertFalse(remote.raw, "the blob is not in this database")
        self.assertEqual(remote._get_content_prefix(), b"", "nothing is stored here")

        calls = []

        class Response:
            content = b"%PDF-1.7 fetched"

            def raise_for_status(self):
                return None

        def fake_request(egress, method, url, *, purpose, headers=None, **kwargs):
            calls.append((method, url, purpose, headers, kwargs.get("max_bytes")))
            return Response()

        with (
            patch.object(
                type(self.env["res.config.settings"]),
                "_get_cloud_storage_configuration",
                lambda self: {"provider": "fake"},
            ),
            patch.object(
                type(remote),
                "_generate_cloud_storage_download_info",
                lambda self: {"url": "https://bucket/blob", "time_to_expiry": 300},
            ),
            patch.object(type(self.env["ir.egress"]), "request", fake_request),
        ):
            self.assertEqual(remote._get_content(), b"%PDF-1.7 fetched")
            remote._get_content(64)

        self.assertEqual(
            [call[:3] for call in calls],
            [("GET", "https://bucket/blob", "cloud_storage")] * 2,
            "the download goes through ir.egress under the module's purpose",
        )
        self.assertEqual(calls[0][3], {}, "a whole blob asks for no range")
        self.assertIsNone(calls[0][4], "a whole blob is not size-capped")
        self.assertEqual(
            calls[1][3],
            {"Range": "bytes=0-63"},
            "a sized read asks the provider for a prefix instead of the file",
        )
        self.assertEqual(calls[1][4], 64, "a sized read never accepts more")

    def test_get_content_of_a_local_blob_stays_local(self):
        """An attachment this database stores is never fetched over the network."""

        def explode(*args, **kwargs):
            raise AssertionError("a local blob must not reach the provider")

        with patch.object(type(self.env["ir.egress"]), "request", explode):
            self.assertEqual(self.attachment._get_content(), b"payload")
            self.assertEqual(self.attachment._get_content(3), b"pay")

    def test_unconfigured_cloud_content_is_missing_to_every_reader(self):
        """Without a configured provider the blob is unreachable: each reader says so."""
        remote = self._cloud_attachment("statement.pdf", "application/pdf")

        def explode(*args, **kwargs):
            raise AssertionError("an unconfigured provider must not be called")

        with patch.object(type(self.env["ir.egress"]), "request", explode):
            for reader in (
                remote._to_http_stream,
                remote._get_content,
                remote._get_pdf_raw,
                remote._migrate_remote_to_local,
                remote._get_zip_detached_reader,
                lambda: to_pdf_stream(remote),
            ):
                with self.subTest(reader=reader), self.assertRaises(MissingError):
                    reader()

    def test_unconfigured_cloud_content_is_never_redirected_to_its_blob(self):
        """The unsigned blob URL is an identifier, not a download link."""
        remote = self._cloud_attachment("statement.pdf", "application/pdf")
        with self.assertRaises(MissingError):
            remote._to_http_stream()
        configured, signed, egress = self._configured(b"")
        with configured, signed, egress:
            stream = remote._to_http_stream()
        self.assertEqual(stream.type, "url")
        self.assertEqual(stream.url, "https://bucket/blob?signed")

    def test_a_reader_of_a_cloud_stream_gets_the_blob(self):
        """Code that reads a stream (a zip, an export) is handed the bytes."""
        remote = self._cloud_attachment("statement.pdf", "application/pdf")
        configured, signed, egress = self._configured(b"%PDF-1.7 blob")
        with configured, signed, egress:
            stream = remote._to_http_stream()
            self.assertEqual(stream.type, "url")
            self.assertEqual(stream.mimetype, "application/pdf")
            self.assertEqual(stream.read(), b"%PDF-1.7 blob")

    def test_an_inline_stream_carries_the_blob(self):
        """A caller that asks for the bytes gets a data stream, not a redirect."""
        remote = self._cloud_attachment("statement.pdf", "application/pdf")
        configured, signed, egress = self._configured(b"%PDF-1.7 blob")
        with configured, signed, egress:
            stream = remote.with_context(binary_stream_inline=True)._to_http_stream()
        self.assertEqual(stream.type, "data")
        self.assertEqual(stream.data, b"%PDF-1.7 blob")
        self.assertEqual(stream.size, len(b"%PDF-1.7 blob"))
        self.assertEqual(stream.mimetype, "application/pdf")

    def _cloud_image_field(self, size=256):
        image = io.BytesIO()
        Image.new("RGB", (size, size), "green").save(image, "PNG")
        partner = self.env["res.partner"].create(
            {"name": "Cloud image", "image_1920": base64.b64encode(image.getvalue())}
        )
        field = (
            self.env["ir.attachment"]
            ._with_field_rows()
            .search(
                [
                    ("res_model", "=", "res.partner"),
                    ("res_id", "=", partner.id),
                    ("res_field", "=", "image_1920"),
                ]
            )
        )
        field.write({"type": "cloud_storage", "url": "https://bucket/blob"})
        return partner, image.getvalue()

    def test_a_cloud_image_field_is_resized_like_a_local_one(self):
        """/web/image sizes come from the blob instead of a full-size redirect."""
        partner, png = self._cloud_image_field()
        configured, signed, egress = self._configured(png)
        with configured, signed, egress:
            stream = self.env["ir.binary"]._get_stream_image_from_record(
                partner, "image_1920", width=64, height=64
            )
        self.assertEqual(stream.type, "data")
        self.assertEqual(Image.open(io.BytesIO(stream.data)).size, (64, 64))

    def test_a_cloud_field_download_is_named_after_the_record(self):
        """The signed URL carries the requested name, not the field's."""
        partner, png = self._cloud_image_field()
        configured, signed, egress = self._configured(png)
        with configured, signed, egress:
            stream = self.env["ir.binary"]._get_stream_from_record(
                partner, "image_1920", filename="logo.png"
            )
        self.assertEqual(stream.type, "url")
        self.assertEqual(stream.download_name, "logo.png")

    def test_a_cloud_pdf_reaches_the_pdf_tools(self):
        """A PDF the provider holds is read like a local one, page extraction included."""
        pdf = (
            b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 10 10]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF"
        )
        remote = self._cloud_attachment("statement.pdf", "application/pdf")
        configured, signed, egress = self._configured(pdf)
        with configured, signed, egress:
            self.assertEqual(remote._get_pdf_raw(), pdf)
            self.assertEqual(to_pdf_stream(remote).getvalue(), pdf)

    def _sized_cloud_attachment(self):
        remote = self._cloud_attachment("statement.pdf", "application/pdf")
        remote.file_size = 7
        remote.invalidate_recordset(["raw", "datas"])
        return remote

    def test_raw_of_a_cloud_blob_is_fetched_from_the_provider(self):
        """Code that reads raw or datas gets the blob, not empty bytes."""
        remote = self._sized_cloud_attachment()
        configured, signed, egress = self._configured(b"payload")
        with configured, signed, egress:
            self.assertEqual(remote.raw, b"payload")
            self.assertEqual(remote.datas, b"cGF5bG9hZA==")

    def test_raw_of_a_cloud_blob_is_empty_without_a_provider(self):
        """A neutralized copy keeps answering empty bytes, never calling out."""
        remote = self._sized_cloud_attachment()

        def explode(*args, **kwargs):
            raise AssertionError("an unconfigured provider must not be called")

        with patch.object(type(self.env["ir.egress"]), "request", explode):
            self.assertFalse(remote.raw)

    def test_writing_bytes_on_a_cloud_attachment_stores_them_here(self):
        """New content no longer belongs to the blob the attachment pointed at."""
        remote = self._sized_cloud_attachment()

        def explode(*args, **kwargs):
            raise AssertionError("the new bytes are local, nothing is fetched")

        with patch.object(type(self.env["ir.egress"]), "request", explode):
            remote.write({"raw": b"rewritten"})
            self.assertEqual(remote.type, "binary")
            self.assertFalse(remote.url)
            self.assertEqual(remote.raw, b"rewritten")
            self.assertTrue(remote.store_fname)

    def test_an_explicit_type_keeps_the_attachment_in_the_cloud(self):
        """_post_add_create empties the bytes and names the type itself."""
        local = self.env["ir.attachment"].create({"name": "up.txt", "raw": b"x"})
        local.write({"raw": False, "type": "cloud_storage", "url": "https://bucket/b"})
        self.assertEqual(local.type, "cloud_storage")
        self.assertEqual(local.url, "https://bucket/b")
