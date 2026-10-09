from odoo.tests import tagged

from odoo.addons.approval.tests.common import ApprovalCommon, add_rule_step


@tagged("post_install", "-at_install")
class TestCategoryFeasibility(ApprovalCommon):
    def _document(self, amount):
        return self.env["approval.test.gated"].create(
            {
                "name": "Feasibility",
                "partner_id": self.partner.id,
                "amount_total": amount,
            }
        )

    def _as_owner(self, category, document):
        return category.with_user(self.owner_user)._can_be_met_for(
            document.with_user(self.owner_user)
        )

    def test_a_step_whose_rule_the_document_does_not_meet_is_not_judged(self):
        category = self._make_category(
            name="Feasibility rules", approvers=[self.approver_1]
        )
        leaver = self.env["res.users"].create(
            {"name": "Feasibility Leaver", "login": "feasibility_leaver"}
        )
        add_rule_step(
            category,
            [leaver],
            name="Large amounts",
            condition_field="amount",
            operator="gt",
            threshold=1000,
        )
        leaver.action_archive()
        self.assertTrue(self._as_owner(category, self._document(100)))
        self.assertFalse(self._as_owner(category, self._document(5000)))

    def test_a_step_only_the_future_owner_staffs_cannot_be_met(self):
        category = self._make_category(
            name="Feasibility owner", approvers=[self.owner_user]
        )
        self.assertFalse(self._as_owner(category, self._document(100)))
