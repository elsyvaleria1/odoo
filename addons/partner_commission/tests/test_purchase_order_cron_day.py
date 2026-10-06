from datetime import datetime

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.partner_commission.tests.setup import Line, Spec, TestCommissionsSetup


@tagged("commission_purchase", "post_install", "-at_install")
class TestPurchaseOrderCronDay(TestCommissionsSetup):
    def test_a_purchase_ordered_before_the_run_day_is_confirmed_east_of_utc(self):
        self.company.commission_automatic_po_frequency = "weekly"
        self.referrer.grade_id = self.learning
        self.referrer._onchange_grade_id()
        self.crm.recurring_invoice = False
        cron = self.env.ref("partner_commission.cron_confirm_purchase_orders")
        cron.user_id.tz = "Pacific/Auckland"
        with freeze_time("2020-01-06 12:00:00"):
            invoice = self.purchase(Spec(self.gold, [Line(self.crm, 1)]))
            po = invoice.commission_po_line_id.order_id
            po.date_order = datetime(2020, 1, 5, 20, 0)
            with self.sync_env_with_side_cursors():
                cron.method_direct_trigger()
        self.assertEqual(po.state, "done")
