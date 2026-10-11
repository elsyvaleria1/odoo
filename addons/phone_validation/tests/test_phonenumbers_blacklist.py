from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("phone_blacklist")
class TestPhonenumbersBlacklist(TransactionCase):
    def test_sanitize_search(self):
        blacklist = self.env["phone.blacklist"]
        bl_entry = blacklist.create({"number": "+917589632587"})
        self.env.company.country_id = False

        for user_country in [
            self.env.ref("base.be"),
            self.env.ref("base.in"),
            self.env["res.country"],
        ]:
            with self.subTest(country_name=user_country.name or "No country"):
                self.env.user.country_id = user_country

                res = blacklist.search([("number", "in", ["+917 5896 32587"])])
                self.assertEqual(res, bl_entry)

                res = blacklist.search([("number", "=", "+917 5896 32587")])
                self.assertEqual(res, bl_entry)

                res = blacklist.search([("number", "=", "+917589632587")])
                self.assertEqual(res, bl_entry)
