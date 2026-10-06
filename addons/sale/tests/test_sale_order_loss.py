from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleOrderLoss(SaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason_price = cls.env.ref("loss_reason.loss_reason_price")

    def _mark_lost(self, orders, **values):
        wizard = Form(
            self.env["wizard.sale.order.mark.lost"].with_context(active_ids=orders.ids)
        )
        for name, value in values.items():
            setattr(wizard, name, value)
        return wizard.save().action_close()

    def test_a_lost_quotation_is_cancelled_with_its_reason(self):
        self._mark_lost(
            self.sale_order,
            loss_reason_id=self.reason_price,
            loss_note="Rival 8% cheaper",
        )

        self.assertRecordValues(
            self.sale_order,
            [
                {
                    "state": "cancel",
                    "outcome": "lost",
                    "loss_reason_id": self.reason_price.id,
                    "loss_note": "Rival 8% cheaper",
                }
            ],
        )

    def test_several_quotations_are_marked_lost_at_once(self):
        orders = self.sale_order + self._create_so()

        self._mark_lost(orders, loss_reason_id=self.reason_price)

        self.assertEqual(set(orders.mapped("outcome")), {"lost"})

    def test_a_confirmed_order_is_won(self):
        self.sale_order.action_confirm()

        self.assertEqual(self.sale_order.outcome, "won")

    def test_purchase_only_reasons_are_not_offered(self):
        purchase_only = self.env["loss.reason"].create(
            {"name": "Grower sold elsewhere", "scope": "purchase"}
        )
        wizard = self.env["wizard.sale.order.mark.lost"].with_context(
            active_ids=self.sale_order.ids
        )

        allowed = self.env["loss.reason"].search(
            wizard._fields["loss_reason_id"]._description_domain(self.env)
        )

        self.assertIn(self.reason_price, allowed)
        self.assertNotIn(purchase_only, allowed)
