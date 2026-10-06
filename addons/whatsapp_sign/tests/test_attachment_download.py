import io
import zipfile

from odoo.tests import tagged

from odoo.addons.sign.tests.sign_controller_common import TestSignControllerCommon


@tagged("post_install", "-at_install")
class TestAttachmentDownload(TestSignControllerCommon):
    def setUp(self):
        super().setUp()
        self.sign_request = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        self.first, self.second, self.foreign = self.env["ir.attachment"].create(
            [
                {"name": "first.txt", "raw": b"first"},
                {"name": "second.txt", "raw": b"second"},
                {"name": "foreign.txt", "raw": b"foreign"},
            ]
        )
        self.sign_request.attachment_ids = self.first | self.second
        self.url = (
            f"/sign/download/attachments/{self.sign_request.id}/"
            f"{self.sign_request.access_token}"
        )

    def test_the_request_s_link_downloads_every_attachment_in_a_zip(self):
        response = self.url_open(self.url)

        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(
            sorted(archive.read(name) for name in archive.namelist()),
            [b"first", b"second"],
        )

    def test_an_attachment_id_downloads_that_attachment_alone(self):
        response = self.url_open(f"{self.url}/{self.second.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"second")

    def test_an_attachment_of_no_request_is_not_found(self):
        self.assertEqual(
            self.url_open(f"{self.url}/{self.foreign.id}").status_code, 404
        )

    def test_another_token_downloads_nothing(self):
        url = f"/sign/download/attachments/{self.sign_request.id}/{'x' * 32}"

        self.assertEqual(self.url_open(url).status_code, 404)

    def test_a_canceled_request_s_link_downloads_nothing(self):
        self.sign_request.cancel()

        self.assertEqual(self.url_open(self.url).status_code, 404)
