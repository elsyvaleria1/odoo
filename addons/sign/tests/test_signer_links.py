from datetime import datetime, time, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .sign_controller_common import TestSignControllerCommon
from odoo.addons.base.models.access_link import hash_token


@tagged("post_install", "-at_install", "access_link")
class TestSignerLinks(TestSignControllerCommon):
    def _links(self, item):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", item._name), ("res_id", "=", item.id)])
        )

    def _document(self, sign_request, token):
        return self.url_open(f"/sign/document/{sign_request.id}/{token}")

    def test_a_signer_signs_through_a_link_in_their_name_until_the_validity(self):
        sign_request = self.create_sign_request_1_role(self.partner_1, self.partner_4)
        sign_request.validity = fields.Date.today() + timedelta(days=20)
        item = sign_request.request_item_ids
        link = self._links(item).filtered(lambda link: not link.revoked_at)
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.cause),
            (1, self.partner_1, "comment", "notification"),
        )
        self.assertEqual(
            link.date_to, datetime.combine(sign_request.validity, time(23, 59, 59))
        )
        self.assertEqual(link.token_hash, hash_token(item.sudo().access_token))
        self.env.cr.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'sign_request_item' AND column_name = 'access_token'"
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0, "no token is kept in clear")

    @mute_logger("odoo.http")
    def test_a_signer_token_opens_its_own_request_only_and_not_once_cancelled(self):
        sign_request = self.create_sign_request_1_role(self.partner_1, self.partner_4)
        other = self.create_sign_request_1_role(self.partner_2, self.partner_4)
        token = sign_request.request_item_ids.sudo().access_token
        self.authenticate(None, None)
        self.assertEqual(self._document(sign_request, token).status_code, 200)
        self.assertEqual(self._document(other, token).status_code, 404)
        sign_request.cancel()
        self.assertEqual(self._document(sign_request, token).status_code, 404)

    def test_the_token_holder_does_not_choose_the_sms_number(self):
        sign_request = self.create_sign_request_1_role_sms_auth(
            self.partner_1, self.partner_4
        )
        item = sign_request.request_item_ids
        item.sms_number = "+15550100"
        token = item.sudo().access_token
        self.authenticate(None, None)
        with patch(
            "odoo.addons.sign.models.sign_request_item.SignRequestItem._send_sms_code",
            lambda self: True,
        ):
            self._json_url_open(
                f"/sign/send-sms/{sign_request.id}/{token}/+15559999", data={}
            )
        self.assertEqual(item.sms_number, "+15550100")


@tagged("post_install", "-at_install", "access_link")
class TestRequestLinks(TestSignControllerCommon):
    def _links(self, sign_request):
        return (
            self.env["access.link"]
            .sudo()
            .search(
                [("res_model", "=", "sign.request"), ("res_id", "=", sign_request.id)]
            )
        )

    def _state(self, sign_request, token):
        payload = self._json_url_open(
            f"/sign/sign_request_state/{sign_request.id}/{token}", data={}
        ).json()
        if "error" in payload:
            return payload["error"]["code"]
        return payload["result"]

    def test_a_request_is_viewed_through_a_link_in_its_requesters_name(self):
        sign_request = self.create_sign_request_1_role(self.partner_1, self.partner_4)
        link = self._links(sign_request)
        self.assertEqual(
            (len(link), link.partner_id, link.role),
            (1, sign_request.create_uid.partner_id, "view"),
        )
        self.assertEqual(link.token_hash, hash_token(sign_request.access_token))
        self.authenticate(None, None)
        self.assertEqual(self._state(sign_request, sign_request.access_token), "sent")
        other = self.create_sign_request_1_role(self.partner_2, self.partner_4)
        self.assertEqual(
            self._state(other, sign_request.access_token), 404, "its own only"
        )

    def test_cancelling_a_request_retires_its_link(self):
        sign_request = self.create_sign_request_1_role(self.partner_1, self.partner_4)
        token = sign_request.access_token
        sign_request.cancel()
        self.assertNotEqual(sign_request.access_token, token)
        self.authenticate(None, None)
        self.assertEqual(self._state(sign_request, token), 404)
        self.assertEqual(
            self._state(sign_request, sign_request.access_token),
            "canceled",
        )
