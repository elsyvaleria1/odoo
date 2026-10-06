from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestMoveApproverReach(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.decider = new_test_user(
            cls.env, login="move_decider", groups="base.group_user"
        )
        category = cls.env["approval.category"].create(
            {
                "name": "Invoice Reach",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_amount_min": 1000.0,
                "move_amount_max": 10000.0,
                "has_amount": "required",
                "has_partner": "required",
            }
        )
        add_category_approver(category, cls.decider, required=True)
        cls.bystander = new_test_user(
            cls.env, login="move_decider_other", groups="base.group_user"
        )
        elsewhere = cls.env["approval.category"].create(
            {
                "name": "Bystander Invoices",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_amount_min": 50000.0,
                "move_amount_max": 60000.0,
                "has_amount": "required",
                "has_partner": "required",
            }
        )
        add_category_approver(elsewhere, cls.bystander, required=True)
        cls.env.cr.flush()
        cls.invoice, cls.sibling = (cls._make_invoice(), cls._make_invoice())

    @classmethod
    def _make_invoice(cls):
        return cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "reach",
                            "quantity": 30.0,
                            "price_unit": 100.0,
                            "account_id": cls.account_revenue.id,
                        },
                    ),
                ],
            }
        )

    def _reads(self, move):
        as_decider = move.with_user(self.decider)
        return bool(as_decider.search([("id", "=", move.id)])) and bool(
            as_decider.line_ids.search([("move_id", "=", move.id)])
        )

    def test_the_decider_reads_the_entry_while_they_decide(self):
        self.assertTrue(self.decider.has_group("approval.group_approval_decider"))
        self.assertFalse(self._reads(self.invoice))
        self.invoice.action_post()
        request = self.invoice.approval_request_id
        self.assertEqual(request.state, "pending")
        self.assertTrue(self._reads(self.invoice))
        self.invoice.with_user(self.decider).check_access("read")
        self.assertFalse(self._reads(self.sibling))
        with self.assertRaises(AccessError):
            self.sibling.with_user(self.decider).check_access("read")

        request.with_user(self.decider).action_approve()
        self.assertFalse(self._reads(self.invoice))

    def test_a_decider_with_nothing_pending_searches_nothing(self):
        self.assertTrue(
            self.env["account.move"].with_user(self.decider)._search([]).is_empty()
        )

    def test_the_reach_is_read_per_user_and_per_query(self):
        self.assertTrue(self.bystander.has_group("approval.group_approval_decider"))
        as_decider = self.env["account.move"].with_user(self.decider)
        as_bystander = self.env["account.move"].with_user(self.bystander)
        self.assertFalse(as_decider.search([]))
        self.assertFalse(as_bystander.search([]))
        with self.assertRaises(AccessError):
            self.invoice.with_user(self.decider).check_access("read")

        self.invoice.action_post()
        self.assertEqual(self.invoice.approval_request_id.state, "pending")
        self.assertEqual(as_decider.search([]), self.invoice)
        self.invoice.with_user(self.decider).check_access("read")
        self.assertFalse(as_bystander.search([]))
        with self.assertRaises(AccessError):
            self.invoice.with_user(self.bystander).check_access("read")
        self.assertEqual(as_decider.search([]), self.invoice)
