from odoo import api, fields, models
from odoo.libs.numbers import float_compare

from odoo.addons.account.tools.display_types import NON_ACCOUNTABLE_DISPLAY_TYPES

_release_to_pay_status_list = [("yes", "Yes"), ("no", "No"), ("exception", "Exception")]

_release_to_pay_help = (
    "  * Yes: you should pay the bill, you have received the products\n"
    "  * No, you should not pay the bill, you have not received the products\n"
    "  * Exception, there is a difference between received and billed quantities\n"
    "Changing this status forces it, and 'Force Status' is ticked to say so. "
    "Clear that box to go back to the automatic verdict."
)


class AccountMove(models.Model):
    _inherit = "account.move"

    release_to_pay = fields.Selection(
        selection=_release_to_pay_status_list,
        string="Release to Pay",
        compute="_compute_release_to_pay",
        recursive=True,
        store=True,
        copy=False,
        help="This field can take the following values :\n" + _release_to_pay_help,
    )
    release_to_pay_manual = fields.Selection(
        selection=_release_to_pay_status_list,
        string="Should Be Paid",
        compute="_compute_release_to_pay_manual",
        recursive=True,
        store=True,
        copy=False,
        readonly=False,
        help=_release_to_pay_help,
    )
    force_release_to_pay = fields.Boolean(
        string="Force Status",
        copy=False,
        help="Indicates whether the 'Should Be Paid' status is defined automatically or manually.",
    )

    @api.model
    def _release_to_pay_move_types(self):
        return self.get_purchase_types(include_receipts=True)

    @api.model
    def _release_to_pay_refund_types(self) -> list:
        return [
            move_type
            for move_type in self._release_to_pay_move_types()
            if move_type in ("in_refund", "out_refund")
        ]

    @api.depends(
        "invoice_line_ids.can_be_paid",
        "force_release_to_pay",
        "release_to_pay_manual",
        "payment_state",
    )
    def _compute_release_to_pay(self) -> None:
        release_to_pay_types = self._release_to_pay_move_types()
        for invoice in self:
            if invoice.move_type not in release_to_pay_types:
                invoice.release_to_pay = False
            elif invoice.payment_state == "paid":
                invoice.release_to_pay = "no"
            elif invoice.force_release_to_pay:
                invoice.release_to_pay = invoice.release_to_pay_manual or "exception"
            else:
                result = None
                for invoice_line in invoice.invoice_line_ids.filtered(
                    lambda l: l.display_type not in NON_ACCOUNTABLE_DISPLAY_TYPES
                ):
                    line_status = invoice_line.can_be_paid
                    if line_status == "exception":
                        result = "exception"
                        break
                    if not result:
                        result = line_status
                    elif line_status != result:
                        result = "exception"
                        break

                invoice.release_to_pay = result or "no"

    @api.depends("release_to_pay", "force_release_to_pay")
    def _compute_release_to_pay_manual(self) -> None:
        for invoice in self:
            if invoice.force_release_to_pay:
                invoice.release_to_pay_manual = invoice.release_to_pay_manual
            else:
                invoice.release_to_pay_manual = invoice.release_to_pay

    @api.onchange("release_to_pay_manual")
    def _onchange_release_to_pay_manual(self) -> None:
        if self.release_to_pay and self.release_to_pay_manual != self.release_to_pay:
            self.force_release_to_pay = True


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    can_be_paid = fields.Selection(
        selection=_release_to_pay_status_list,
        string="Line Release to Pay",
        compute="_compute_can_be_paid",
        store=True,
        copy=False,
    )

    @api.depends(
        "purchase_line_ids",
        "purchase_line_ids.qty_transferred",
        "purchase_line_ids.product_qty",
        "purchase_line_ids.invoice_line_ids.quantity",
        "purchase_line_ids.invoice_line_ids.product_uom_id",
        "purchase_line_ids.invoice_line_ids.parent_state",
        "purchase_line_ids.invoice_line_ids.move_id.move_type",
        "purchase_line_ids.invoice_line_ids.move_id.payment_state",
        "purchase_line_ids.price_unit",
        "purchase_line_ids.discount",
        "purchase_line_ids.currency_id",
        "purchase_line_ids.product_uom_id",
        "purchase_line_ids.product_id",
        "purchase_line_ids.product_id.bill_policy",
        "price_unit",
        "discount",
        "product_uom_id",
        "currency_id",
        "move_id.move_type",
        "move_id.invoice_date",
    )
    def _compute_can_be_paid(self) -> None:
        precision = self.env["decimal.precision"].get_precision("Product Unit")
        price_precision = self.env["decimal.precision"].get_precision("Product Price")
        release_to_pay_types = self.env["account.move"]._release_to_pay_move_types()
        refund_types = self.env["account.move"]._release_to_pay_refund_types()
        for invoice_line in self:
            if invoice_line.move_id.move_type not in release_to_pay_types:
                invoice_line.can_be_paid = False
                continue

            po_lines = invoice_line.purchase_line_ids
            if po_lines:
                uom = po_lines[0].product_uom_id
                if not self._release_to_pay_uoms_comparable(
                    invoice_line, po_lines, uom
                ):
                    invoice_line.can_be_paid = "exception"
                    continue

                invoiced_qty = self._billed_qty_for_order_lines(po_lines, uom)
                received_qty = sum(
                    line.product_uom_id._get_quantity_in_unit(line.qty_transferred, uom)
                    for line in po_lines
                )
                ordered_qty = sum(
                    line.product_uom_id._get_quantity_in_unit(line.product_qty, uom)
                    for line in po_lines
                )
                own_qty = invoice_line.product_uom_id._get_quantity_in_unit(
                    invoice_line.quantity, uom
                )
                if invoice_line.move_id.move_type in refund_types:
                    own_qty = -own_qty

                invoice_currency = invoice_line.currency_id
                rate_date = (
                    invoice_line.move_id.invoice_date
                    or fields.Date.context_today(invoice_line)
                )
                invoice_price = invoice_line.product_uom_id._get_price_in_unit(
                    invoice_line.price_unit
                    * (1.0 - (invoice_line.discount or 0.0) / 100.0),
                    uom,
                )
                has_price_exception = False

                for po_line in po_lines:
                    order_currency = po_line.currency_id
                    order_price = po_line.product_uom_id._get_price_in_unit(
                        po_line.price_unit * (1.0 - (po_line.discount or 0.0) / 100.0),
                        uom,
                    )
                    invoice_converted_price = invoice_currency._convert(
                        invoice_price,
                        order_currency,
                        invoice_line.company_id,
                        rate_date,
                        round=False,
                    )
                    if (
                        float_compare(
                            order_price,
                            invoice_converted_price,
                            precision_digits=price_precision,
                        )
                        != 0
                    ):
                        has_price_exception = True
                        break

                if has_price_exception:
                    invoice_line.can_be_paid = "exception"
                    continue

                if len(po_lines.product_id) > 1 or (
                    invoice_line.product_id
                    and invoice_line.product_id != po_lines.product_id
                ):
                    invoice_line.can_be_paid = "exception"
                    continue

                if po_lines[0].product_id.bill_policy == "ordered":
                    invoice_line.can_be_paid = self._release_to_pay_for_ordered(
                        own_qty, invoiced_qty, ordered_qty, precision
                    )
                else:
                    invoice_line.can_be_paid = self._release_to_pay_for_transferred(
                        invoiced_qty, received_qty, ordered_qty, precision
                    )

            else:
                invoice_line.can_be_paid = "exception"

    @staticmethod
    def _release_to_pay_uoms_comparable(invoice_line, po_lines, uom) -> bool:
        units = (
            invoice_line.product_uom_id
            | po_lines.product_uom_id
            | po_lines.invoice_line_ids.product_uom_id
        )
        return all(unit._has_common_reference(uom) for unit in units)

    @staticmethod
    def _billed_qty_for_order_lines(po_lines, uom):
        AccountMove = po_lines.env["account.move"]
        judged_types = AccountMove._release_to_pay_move_types()
        refund_types = AccountMove._release_to_pay_refund_types()
        billed = 0.0
        for line in po_lines.invoice_line_ids:
            move = line.move_id
            if move.move_type not in judged_types:
                continue
            if move.state == "cancel" and move.payment_state != "invoicing_legacy":
                continue
            qty = line.product_uom_id._get_quantity_in_unit(line.quantity, uom)
            if move.move_type in refund_types:
                billed -= qty
            else:
                billed += qty
        return billed

    @staticmethod
    def _release_to_pay_for_ordered(
        own_qty, invoiced_qty, ordered_qty, precision
    ) -> str:
        if (
            float_compare(
                invoiced_qty - own_qty, ordered_qty, precision_digits=precision
            )
            >= 0
        ):
            return "no"
        if float_compare(invoiced_qty, ordered_qty, precision_digits=precision) <= 0:
            return "yes"
        return "exception"

    @staticmethod
    def _release_to_pay_for_transferred(
        invoiced_qty, received_qty, ordered_qty, precision
    ) -> str:
        if float_compare(invoiced_qty, received_qty, precision_digits=precision) <= 0:
            return "yes"
        if (
            float_compare(received_qty, 0.0, precision_digits=precision) == 0
            and float_compare(invoiced_qty, ordered_qty, precision_digits=precision)
            <= 0
        ):
            return "no"
        return "exception"
