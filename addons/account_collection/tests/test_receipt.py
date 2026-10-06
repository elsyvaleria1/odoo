from odoo.tests import HttpCase, tagged

from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCollectionReceipt(CollectionCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a.email = "sauce@example.com"
        cls.supervisor = cls.treasurer
        cls.company_data[
            "company"
        ].account_config_id.collection_supervisor_id = cls.supervisor

    def _receipt(self):
        payment = self._collect(self._post_invoice(1000.0), 1000.0)
        url = payment.get_collection_receipt_url()
        return payment, url[url.index("/collection/") :]

    def test_the_customer_is_emailed_the_receipt_with_its_link(self):
        payment = self._collect(self._post_invoice(1000.0), 1000.0)

        message = payment.message_ids.filtered(
            lambda message: message.subtype_id == self.env.ref("mail.mt_comment")
        )[:1]
        self.assertIn(self.partner_a, message.partner_ids)
        self.assertIn("/collection/receipt/", message.body)
        self.assertTrue(message.attachment_ids)

    def test_no_receipt_when_the_company_sends_none(self):
        self.company_data["company"].account_config_id.collection_send_receipt = False
        payment = self._collect(self._post_invoice(1000.0), 1000.0)
        self.assertFalse(
            payment.message_ids.filtered(
                lambda message: message.subtype_id == self.env.ref("mail.mt_comment")
            )
        )

    def test_the_link_shows_the_receipt(self):
        payment, path = self._receipt()
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn(payment.name, response.text)
        self.assertIn(self.collector.name, response.text)

    def test_a_wrong_token_shows_nothing(self):
        payment, _path = self._receipt()
        response = self.url_open(
            f"/collection/receipt/{payment.id}?access_token=wrongtokenwrongtoken"
        )
        self.assertEqual(response.status_code, 404)

    def test_the_token_opens_only_its_own_receipt(self):
        _payment, path = self._receipt()
        other, _other_path = self._receipt()
        token = path.split("access_token=")[1]
        response = self.url_open(f"/collection/receipt/{other.id}?access_token={token}")
        self.assertEqual(response.status_code, 404)

    def test_the_customer_reports_a_problem_to_the_supervisor(self):
        payment, path = self._receipt()
        token = path.split("access_token=")[1]
        page = self.url_open(path)
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]

        response = self.url_open(
            f"/collection/receipt/{payment.id}/report",
            data={
                "csrf_token": csrf,
                "access_token": token,
                "description": "I paid 1,200, not 1,000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("received your report", response.text)
        activity = payment.activity_ids.filtered(
            lambda activity: activity.user_id == self.supervisor
        )
        self.assertEqual(len(activity), 1)
        self.assertIn("I paid 1,200", payment.message_ids[0].body)

    def test_the_receipt_downloads_as_pdf(self):
        _payment, path = self._receipt()
        base, query = path.split("?")
        response = self.url_open(f"{base}/pdf?{query}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
