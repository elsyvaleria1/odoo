from odoo.fields import Command
from odoo.tests import Form, tagged

from odoo.addons.crm.tests.common import TestCrmCommon


@tagged("post_install", "-at_install")
class TestSaleOrderLossCrm(TestCrmCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason_price = cls.env.ref("loss_reason.loss_reason_price")
        cls.product = cls.env["product.product"].create({"name": "Tomato"})

    def _quotation(self):
        return self.env["sale.order"].create(
            {
                "partner_id": self.env.user.partner_id.id,
                "opportunity_id": self.lead_1.id,
                "line_ids": [Command.create({"product_id": self.product.id})],
            }
        )

    def _wizard(self, orders):
        wizard = Form(
            self.env["wizard.sale.order.mark.lost"].with_context(active_ids=orders.ids)
        )
        wizard.loss_reason_id = self.reason_price
        return wizard

    def test_losing_the_last_open_quotation_loses_the_opportunity(self):
        quotation = self._quotation()
        wizard = self._wizard(quotation)
        self.assertTrue(wizard.close_opportunities)

        wizard.save().action_close()

        self.assertFalse(self.lead_1.active)
        self.assertEqual(self.lead_1.lost_reason_id, self.reason_price)

    def test_an_opportunity_with_another_open_quotation_stays_open(self):
        quotation = self._quotation()
        self._quotation()
        wizard = self._wizard(quotation)
        self.assertFalse(wizard.close_opportunities)

        wizard.save().action_close()

        self.assertEqual(quotation.outcome, "lost")
        self.assertTrue(self.lead_1.active)

    def test_the_salesperson_may_keep_the_opportunity_open(self):
        quotation = self._quotation()
        wizard = self._wizard(quotation)
        wizard.close_opportunities = False

        wizard.save().action_close()

        self.assertTrue(self.lead_1.active)
