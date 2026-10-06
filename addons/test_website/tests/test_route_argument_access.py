from unittest.mock import patch

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestRouteArgumentAccess(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        visitor_access = cls.env.ref(
            "test_website.access_test_model_multi_website_public"
        )
        visitor_access.domain = "[('website_id', 'in', [False, website.id])]"
        cls.record = cls.env.ref("test_website.test_model_multi_website_1")

    def _url(self, record):
        return f"/test_website/multi_website/{self.env['ir.http']._slug(record)}"

    def test_a_visitor_opens_a_record_of_the_website_the_route_serves(self):
        response = self.url_open(self._url(self.record))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, self.record.name)

    @mute_logger("odoo.http")
    def test_a_visitor_does_not_open_a_record_of_another_website(self):
        other_website = self.env["website"].create({"name": "Other Website"})
        record = self.record.copy({"website_id": other_website.id})

        response = self.url_open(self._url(record))

        self.assertEqual(response.status_code, 404)

    def test_a_route_argument_is_checked_under_the_signature_its_body_reads_with(
        self,
    ):
        Model = type(self.env["test.model.multi.website"])
        check_access = Model.check_access
        signatures = []

        def recording_check_access(records, operation):
            signatures.append(records.env["ir.access"]._policy_signature())
            return check_access(records, operation)

        generic = self.env.ref("test_website.test_model_multi_generic")
        with patch.object(Model, "check_access", recording_check_access):
            response = self.url_open(self._url(generic))

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(signatures), 2)
        self.assertEqual(len(set(signatures)), 1, signatures)
