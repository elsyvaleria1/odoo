from odoo.tests import Form, tagged

from odoo.addons.purchase.tests.test_purchase_invoice import TestPurchaseToInvoiceCommon


@tagged("post_install", "-at_install")
class TestPurchaseOrderLoss(TestPurchaseToInvoiceCommon):
    def test_a_lost_rfq_is_cancelled_with_its_reason(self):
        rfq = self.init_purchase(confirm=False, products=[self.product_order])
        reason = self.env.ref("loss_reason.loss_reason_delivery")
        wizard = Form(
            self.env["wizard.purchase.order.mark.lost"].with_context(active_ids=rfq.ids)
        )
        wizard.loss_reason_id = reason

        wizard.save().action_close()

        self.assertRecordValues(
            rfq,
            [{"state": "cancel", "outcome": "lost", "loss_reason_id": reason.id}],
        )

    def test_sale_only_reasons_are_not_offered(self):
        sale_only = self.env["loss.reason"].create(
            {"name": "Customer chose a rival", "scope": "sale"}
        )
        wizard = self.env["wizard.purchase.order.mark.lost"]

        allowed = self.env["loss.reason"].search(
            wizard._fields["loss_reason_id"]._description_domain(self.env)
        )

        self.assertNotIn(sale_only, allowed)
        self.assertIn(self.env.ref("loss_reason.loss_reason_price"), allowed)
