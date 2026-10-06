from odoo.tests import tagged

from odoo.addons.sign.tests.sign_controller_common import TestSignControllerCommon


@tagged("post_install", "-at_install")
class TestSignFiling(TestSignControllerCommon):
    def test_a_replayed_signature_files_nothing_again(self):
        self.env.company.documents_hr_settings = True
        employee = self.env["hr.employee"].create(
            {"name": "Signer", "partner_id": self.partner_1.id}
        )
        self.assertTrue(employee.hr_employee_folder_id)
        sign_request = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        employee.sign_request_ids = sign_request
        item = sign_request.request_item_ids
        url = f"/sign/sign/{sign_request.id}/{item.access_token}"
        values = {
            "signature": self.create_sign_values(
                sign_request.template_id.sign_item_ids, item.role_id.id
            )
        }
        Documents = self.env["document.document"].with_context(active_test=False)
        filed = [("res_model", "=", "hr.employee"), ("res_id", "=", employee.id)]

        first = self._json_url_open(url, data=values).json()["result"]
        self.assertTrue(first.get("success"))
        count = Documents.search_count(filed)
        self.assertTrue(count)

        replay = self._json_url_open(url, data=values).json()["result"]
        self.assertFalse(replay.get("success"))
        self.assertEqual(Documents.search_count(filed), count)
