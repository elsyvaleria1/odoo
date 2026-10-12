import base64
from datetime import datetime, time
from typing import TYPE_CHECKING, Any

import pytz
from markupsafe import Markup

from odoo import fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.telegram.tools import format as tg

if TYPE_CHECKING:
    from odoo.addons.account.models.account_journal import AccountJournal
    from odoo.addons.approval.models.approval_category import ApprovalCategory

SHEET_TIMEZONE = "America/Mexico_City"


class TelegramShipmentSheet(models.Model):
    _inherit = "telegram.shipment.sheet"

    def _on_shipment_sheet_assigned(self, content: bytes) -> list[str]:
        lines = super()._on_shipment_sheet_assigned(content)
        picking = self.picking_id
        category = self.carrier_id.freight_approval_category_id
        if picking.picking_type_code != "outgoing" or not category:
            return lines
        try:
            with self.env.cr.savepoint():
                return [*lines, self._prepare_freight(category, content)]
        except (AccessError, ValidationError) as error:
            reason = str(error.args[0] if error.args else error).split("\n", 1)[0]
            return [
                *lines,
                self.env._(
                    "%(picking)s keeps the tracking number and the sheet, but I "
                    "could not prepare the freight request %(category)s: %(reason)s",
                    picking=tg.escape(picking.name),
                    category=tg.escape(category.name),
                    reason=tg.escape(reason),
                ),
            ]

    def _prepare_freight(self, category: ApprovalCategory, content: bytes) -> str:
        picking = self.picking_id
        Request = self.env["approval.request"]
        existing = Request.search(
            [
                ("category_id", "=", category.id),
                ("reference", "=", self.tracking_ref),
                ("state", "not in", ("cancelled", "refused")),
            ],
            limit=1,
        )
        if existing:
            existing.shipment_picking_ids |= picking
            return self.env._(
                "Freight %(request)s already covers %(ref)s; %(picking)s is now on it.",
                request=tg.escape(existing.display_name),
                ref=tg.escape(self.tracking_ref),
                picking=tg.escape(picking.name),
            )
        request = Request.create(self._freight_request_values(category))
        self.env["ir.attachment"].create(
            {
                "name": self._attachment_name(),
                "datas": base64.b64encode(content),
                "res_model": "approval.request",
                "res_id": request.id,
            }
        )
        total = (self.extracted or {}).get("total")
        if total:
            return self.env._(
                "Freight request %(category)s prepared as a draft for %(amount)s: "
                "check it against the sheet and submit it.",
                category=tg.escape(category.name),
                amount=f"${total:,.2f}",
            )
        return self.env._(
            "Freight request %(category)s prepared as a draft without an "
            "amount: the total could not be read off the sheet.",
            category=tg.escape(category.name),
        )

    def _freight_request_values(self, category: ApprovalCategory) -> ValuesType:
        self.check_singleton()
        picking = self.picking_id
        values = self.extracted or {}
        total = values.get("total") or 0.0
        sale = picking.sale_id
        product = category.product_ids[:1]
        return {
            "category_id": category.id,
            "request_owner_id": self.env.user.id,
            "company_id": picking.company_id.id,
            "partner_id": self.carrier_id.freight_partner_id.id,
            "date": self._freight_date(values.get("date")),
            "quantity": 1,
            "amount": total,
            "reference": self.tracking_ref,
            "location": self.env._(
                "Destination: %(city)s – Consignee: %(customer)s",
                city=values.get("destination") or picking.partner_id.city or "-",
                customer=picking.partner_id.display_name or "-",
            ),
            "journal_id": self._freight_journal(category).id,
            "reason": self._freight_reason(values),
            "shipment_picking_ids": [fields.Command.link(picking.id)],
            "line_ids": [
                fields.Command.create(
                    {
                        "product_id": product.id,
                        "quantity": 1,
                        "price_unit": total,
                        "description": " · ".join(
                            filter(
                                None,
                                [
                                    self.env._(
                                        "Freight %(ref)s", ref=self.tracking_ref
                                    ),
                                    sale.name,
                                    picking.partner_id.display_name,
                                ],
                            )
                        ),
                    }
                )
            ]
            if product
            else [],
        }

    def _freight_journal(self, category: ApprovalCategory) -> AccountJournal:
        if len(category.journal_ids) == 1:
            return category.journal_ids
        return (
            self.env["approval.request"]
            .search(
                [
                    ("category_id", "=", category.id),
                    ("company_id", "=", self.picking_id.company_id.id),
                    ("journal_id", "!=", False),
                ],
                order="id desc",
                limit=1,
            )
            .journal_id
        )

    @staticmethod
    def _freight_date(day: str | None) -> datetime:
        if not day:
            return fields.Datetime.now()
        noon = pytz.timezone(SHEET_TIMEZONE).localize(
            datetime.combine(fields.Date.to_date(day), time(12))
        )
        return noon.astimezone(pytz.UTC).replace(tzinfo=None)

    def _freight_reason(self, values: dict[str, Any]) -> Markup:
        picking = self.picking_id
        sale = picking.sale_id
        partner = self.carrier_id.freight_partner_id
        rows = [
            (self.env._("Sales order"), sale.name),
            (self.env._("Customer"), picking.partner_id.display_name),
            (self.env._("Transfer"), picking.name),
            (self.env._("Tracking number"), self.tracking_ref),
            (self.env._("Destination"), values.get("destination")),
            (
                self.env._("Service"),
                self.env._("Ocurre") if values.get("service") == "ocurre" else "",
            ),
            (self.env._("Subtotal"), _money(values.get("subtotal"))),
            (self.env._("VAT"), _money(values.get("tax_amount"))),
            (self.env._("VAT withheld"), _money(values.get("tax_withheld"))),
            (self.env._("Total with taxes"), _money(values.get("total"))),
            (self.env._("Salesperson"), sale.user_id.name),
        ]
        rows += [
            (
                self.env._("Payment details"),
                " · ".join(filter(None, [bank.bank_name, bank.acc_number])),
            )
            for bank in partner.bank_account_ids
        ]
        items = Markup("").join(
            Markup("<li><strong>%s:</strong> %s</li>") % (label, value)
            for label, value in rows
            if value
        )
        return Markup("<ul>%s</ul>") % items if items else Markup("")


def _money(amount: float | None) -> str:
    return f"${amount:,.2f}" if amount else ""
