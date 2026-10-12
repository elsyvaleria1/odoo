import json
from typing import Any

from markupsafe import Markup

from odoo import api, fields, models
from odoo.libs.json import loads as json_loads


class TelegramPaymentReportLog(models.Model):
    _name = "telegram.payment.report.log"
    _description = "Telegram Payment Approval Log"
    _order = "date desc, id desc"

    date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        required=True,
    )
    chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        readonly=True,
        ondelete="set null",
    )
    telegram_chat_id = fields.Char(
        readonly=True,
        help="The Telegram chat ID where the payment was registered",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
        help="Odoo Contact linked to the internal user who registered the payment.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        help="Internal Odoo user who registered the payment via Telegram.",
    )
    payment_details = fields.Text(
        readonly=True,
        help="JSON with the payment details submitted",
    )
    payment_details_display = fields.Html(
        compute="_compute_payment_details_display",
        help="Formatted payment details for display",
    )
    approval_request_id = fields.Many2one(
        comodel_name="approval.request",
        readonly=True,
        ondelete="set null",
    )
    approval_subject = fields.Char(
        related="approval_request_id.name",
        readonly=True,
    )
    approval_state = fields.Selection(
        related="approval_request_id.state",
        readonly=True,
    )
    amount = fields.Float(readonly=True)

    @api.depends("payment_details")
    def _compute_payment_details_display(self) -> None:
        for record in self:
            if not record.payment_details:
                record.payment_details_display = ""
                continue

            try:
                data = json_loads(record.payment_details)
            except json.JSONDecodeError, TypeError:
                record.payment_details_display = record.payment_details or ""
                continue

            record.payment_details_display = self._format_payment_details_html(data)

    @staticmethod
    def _format_payment_details_html(data: dict[str, Any]) -> Markup:
        field_labels = {
            "partner_fx_name": "Invoice To",
            "product_category": "Product Category",
            "cfdi_use": "CFDI Use",
            "payment_method": "Payment Method",
            "company": "Company",
            "partner_cn_name": "Apply Payment To",
            "product_reference": "Product Reference",
            "date": "Payment Date",
            "amount": "Amount",
        }
        items = Markup()
        for key, label in field_labels.items():
            if key not in data:
                continue
            value = data[key]
            if key == "amount":
                value = f"${value:,.2f}"
            items += Markup("<li><strong>{label}:</strong> {value}</li>").format(
                label=label, value=value
            )
        return Markup("<ul>{items}</ul>").format(items=items)
