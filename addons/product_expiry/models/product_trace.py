from collections import defaultdict

from odoo import SUPERUSER_ID, api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTrace(models.Model):
    _inherit = "product.trace"

    @api.model
    def _alert_lots_past_alert_date(self, company_id=False) -> None:
        _debug.pipeline("expiry_alert_scan", company=company_id)
        domain = Domain(
            [
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
                ("trace_id.alert_date", "<=", fields.Datetime.now()),
                ("trace_id.product_expiry_reminded", "=", False),
            ]
        )
        if company_id:
            domain &= Domain("company_id", "=", company_id)
        alert_lots = self.browse(
            lot.id
            for [lot] in self.env["stock.quant"]._read_group(domain, ["trace_id"])
            if lot
        )
        if not alert_lots:
            return
        alert_lots._schedule_expiry_activity()
        alert_lots.product_expiry_reminded = True

    def _schedule_expiry_activity(self) -> None:
        _debug.lifecycle("expiry_activity_schedule", lots=self)
        lots_by_user = defaultdict(self.browse)
        for lot in self:
            product = lot.product_id
            responsible = (
                product.with_company(lot.company_id).responsible_id
                or product.responsible_id
            )
            lots_by_user[responsible.id or SUPERUSER_ID] |= lot
        for user_id, lots in lots_by_user.items():
            lots.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user_id,
                note=self.env._(
                    "The alert date has been reached for this lot/serial number"
                ),
                summary=self.env._("Alert Date Reached"),
            )
