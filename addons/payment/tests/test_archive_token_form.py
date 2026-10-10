from lxml import html

from odoo import http
from odoo.tests import tagged

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestArchiveTokenForm(PaymentHttpCommon):
    def _archive(self, token, fragments=False, **values):
        return self.url_open(
            self._build_url("/payment/archive_token"),
            data={
                "token_id": token.id,
                "csrf_token": http.Request.csrf_token(self),
                **values,
            },
            headers={FRAGMENTS_HEADER: "1"} if fragments else None,
            allow_redirects=False,
        )

    def test_a_user_s_own_token_is_archived_and_the_form_comes_back(self):
        token = self._create_token(partner_id=self.portal_partner.id)
        self.authenticate(self.portal_user.login, self.portal_user.login)

        response = self._archive(token, redirect="/my/payment_method?x=1")

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/my/payment_method?x=1"))
        self.assertFalse(token.active)

    def test_asked_for_fragments_it_says_where_to_go(self):
        token = self._create_token(partner_id=self.portal_partner.id)
        self.authenticate(self.portal_user.login, self.portal_user.login)

        response = self._archive(token, fragments=True)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["redirect"], "/my/payment_method")
        self.assertFalse(token.active)

    def test_someone_else_s_token_is_left_alone(self):
        token = self._create_token(partner_id=self.partner.id)
        self.authenticate(self.portal_user.login, self.portal_user.login)

        self._archive(token)

        self.assertTrue(token.active)

    def test_the_payment_methods_page_holds_the_archive_form_outside_the_payment_form(
        self,
    ):
        self._create_token(partner_id=self.portal_partner.id)
        self.authenticate(self.portal_user.login, self.portal_user.login)

        page = html.fromstring(self._portal_payment_method().content)

        (form,) = page.xpath("//form[@id='o_payment_archive_token_form']")
        self.assertEqual(form.get("action"), "/payment/archive_token")
        self.assertFalse(form.xpath("ancestor::form"))
        self.assertTrue(page.xpath("//form[@id='o_payment_form']"))
        self.assertFalse(page.xpath("//form//form"))
