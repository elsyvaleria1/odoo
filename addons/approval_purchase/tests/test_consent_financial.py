from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestConsentOnPurchases(TransactionCase):
    def _category(self, name, **values):
        return self.env["approval.category"].create(
            {"name": name, "approval_minimum": 1, **values}
        )

    def test_consent_is_refused_on_a_category_that_buys(self):
        for name, values in [
            ("Confirming", {"approval_type": "purchase"}),
            (
                "Ordering",
                {"approval_type": "general", "target_model": "purchase.order"},
            ),
        ]:
            with self.subTest(name), self.assertRaises(ValidationError):
                self._category(name, consent_approval_hours=24, **values)
        self.assertTrue(
            self._category(
                "Errand", approval_type="general", consent_approval_hours=24
            ),
            "a category that spends nothing keeps consent approval",
        )
