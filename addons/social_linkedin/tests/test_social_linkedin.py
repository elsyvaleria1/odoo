import base64
from unittest.mock import patch

import requests

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tools.misc import mute_logger

from odoo.addons.html_editor.tools import link_preview
from odoo.addons.social.tests.common import SocialCase
from odoo.addons.social.tests.tools import mock_void_external_calls
from odoo.addons.social_linkedin.models.social_account import SocialAccount
from odoo.addons.social_linkedin.utils import id_to_urn, urn_to_id


class SocialLinkedinCase(SocialCase):
    @classmethod
    def setUpClass(cls):
        with mock_void_external_calls():
            super().setUpClass()
            cls.social_accounts.write({"linkedin_access_token": "ABCD"})

    def test_post_success(self):
        self._test_post()

    def test_post_failure(self):
        self._test_post(False)

    @mute_logger("odoo.addons.social.models.social_account")
    def _test_post(self, success=True):
        self.assertEqual(self.social_post.state, "draft")

        def _patched_request(method, *args, **kwargs):
            response = requests.Response()
            if success:
                response._content = b'{"id": "42"}'
                response.status_code = 200
                response.headers = {"x-restli-id": "fake_created_post_urn"}
            else:
                response._content = b'{"serviceErrorCode": 65600}'
                response.status_code = 404
            return response

        with (
            patch.object(requests, "request", _patched_request),
            patch.object(
                SocialAccount,
                "_linkedin_upload_image",
                lambda *a, **kw: "fake_image_urn",
            ),
        ):
            self.social_post._action_post()

        self._checkPostedStatus(success)

        if success:
            linkedin_post_id = self.social_post.live_post_ids.mapped("linkedin_post_id")
            self.assertEqual(linkedin_post_id, ["fake_created_post_urn"] * 2)
            self.assertTrue(
                all(
                    not account.is_media_disconnected
                    for account in self.social_post.account_ids
                ),
                "Accounts should not be marked disconnected if post is successful",
            )
        else:
            self.assertTrue(
                all(
                    account.is_media_disconnected
                    for account in self.social_post.account_ids
                ),
                "Accounts should be marked disconnected if post has failed",
            )

    def test_post_image(self):
        self.social_post.message = "A message https://example.com"
        self.assertTrue(self.social_post.image_ids)
        self._test_post_type("multiImage")

    def test_post_urls(self):
        self.social_post.message = "A message https://example.com"
        self.social_post.image_ids = False
        return self._test_post_type("article")

    def test_post_urls_metadata(self):

        def _patched_get_link_preview_from_url(*args, **kwargs):
            return {
                "og_image": "https://example.com/thumbnail",
                "og_mimetype": "text/html",
                "og_title": "Super Article",
            }

        def _patched_get(url, *args, **kwargs):
            response = requests.Response()
            response.status_code = 200
            if url == "https://example.com/thumbnail":
                response._content = base64.b64decode(
                    b"R0lGODlhAQABAIAAANvf7wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
                )
                response.headers["Content-Type"] = "image/gif"
            return response

        with (
            patch.object(
                link_preview,
                "get_link_preview_from_url",
                side_effect=_patched_get_link_preview_from_url,
            ),
            patch.object(
                requests.Session,
                "request",
                autospec=True,
                side_effect=lambda session, method, url, **kwargs: _patched_get(url),
            ),
        ):
            posts_values = self.test_post_urls()
        self.assertEqual(
            posts_values[0].get("content", {}).get("article", {}).get("thumbnail", {}),
            "fake_image_urn",
        )

    def test_post_text(self):
        self.social_post.message = "A message without URL"
        self.social_post.image_ids = False
        self._test_post_type(None)

    def _test_post_type(self, expected_post_type):
        self.assertEqual(self.social_post.state, "draft")

        def _patched_request(method, *args, **kwargs):
            response = requests.Response()
            response._content = b'{"id": "42"}'
            response.status_code = 200
            post_values = kwargs.get("json", {})
            post_types = post_values.get("content", {}).keys()
            posts_types.extend(post_types or [None])
            posts_values.append(post_values)
            return response

        posts_types = []
        posts_values = []
        with (
            patch.object(requests, "request", _patched_request),
            patch.object(
                SocialAccount,
                "_linkedin_upload_image",
                lambda *a, **kw: "fake_image_urn",
            ),
        ):
            self.social_post._action_post()

        self.assertTrue(posts_types)
        self.assertTrue(
            all(response == expected_post_type for response in posts_types),
            "The post type must be [%s]" % expected_post_type,
        )
        return posts_values

    @classmethod
    def _get_social_media(cls):
        return cls.env.ref("social_linkedin.social_media_linkedin")

    def _get_commentary_after_post(self):
        commentaries = []

        def _patched_post(*args, **kwargs):
            commentaries.append(kwargs.get("json", {}).get("commentary", None))

        with patch.object(requests, "post", _patched_post):
            self.social_post._action_post()

        return commentaries

    def test_post_with_special_char(self):
        self.social_post.message = "(This) <is> {a} [test] string <3"
        self.social_post.image_ids = False
        commentaries = self._get_commentary_after_post()
        expected_output = "\\(This\\) \\<is\\> \\{a\\} \\[test\\] string \\<3"
        self.assertTrue(
            all(commentary == expected_output for commentary in commentaries)
        )

    def test_urn_id_conversion(self):
        self.assertEqual(id_to_urn("1337", "li:image"), "urn:li:image:1337")
        self.assertEqual(
            id_to_urn("urn:li:random:1337", "li:image"), "urn:li:image:1337"
        )
        self.assertEqual(urn_to_id("urn:li:image:1337"), "1337")
        self.assertEqual(
            urn_to_id("urn:li:comment:(urn:li:activity:1234,5678)"), "5678"
        )

    def test_fetch_media_urns(self):

        def _patched_linkedin_request(endpoint, *args, **kwargs):
            response = requests.Response()
            response.status_code = 200
            content = {}
            if "image" in endpoint:
                content = {
                    "results": {
                        "urn:li:image:456": {"downloadUrl": "https://example.com/456"},
                        "urn:li:image:789": {"downloadUrl": "https://example.com/789"},
                    }
                }
            elif "video" in endpoint:
                content = {
                    "results": {
                        "urn:li:video:123": {"downloadUrl": "https://example.com/123"},
                    }
                }
            response._content = json_dumps_bytes(content)
            return response

        fake_post_data = [
            {"content": {"media": {"id": "urn:li:video:123"}}},
            {"content": {"media": {"id": "urn:li:image:456"}}},
            {"content": {"multiImage": {"images": [{"id": "urn:li:image:789"}]}}},
        ]
        with patch.object(
            type(self.env["social.account"]),
            "_linkedin_request",
            side_effect=_patched_linkedin_request,
        ):
            self.env["social.stream"]._update_linkedin_stream_post_images(
                fake_post_data
            )

        self.assertTrue(fake_post_data)
        video_data, image_data, multi_data = fake_post_data
        self.assertTrue("downloadUrl" not in video_data["content"]["media"])
        self.assertEqual(video_data["commentary"], "https://example.com/123")
        self.assertEqual(
            image_data["content"]["media"]["downloadUrl"], "https://example.com/456"
        )
        self.assertEqual(
            multi_data["content"]["multiImage"]["images"][0]["downloadUrl"],
            "https://example.com/789",
        )
