from odoo import fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_cash_sale = fields.Boolean(
        related="payment_term_id.is_immediate",
    )

    def action_open_cash_collect(self) -> dict:
        self.check_singleton()
        if problem := self._get_cash_sale_problem():
            raise UserError(problem)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Collect Cash Sale"),
            "res_model": "wizard.sale.order.cash.collect",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_confirm(self):
        for order in self:
            if problem := order._get_custody_hold_problem():
                raise UserError(problem)
        return super().action_confirm()

    def _get_custody_hold_problem(self) -> str | None:
        self.check_singleton()
        company = self.company_id
        if (
            not company.account_config_id.collection_hold_credit_sales
            or not self.user_id
            or not self.payment_term_id
            or self.payment_term_id.is_immediate
        ):
            return None
        status = self.user_id._get_custody_status(company)
        if not status["overdue_count"]:
            return None
        return self.env._(
            "%(salesperson)s holds %(amount)s in collections past their hand-in date: "
            "%(order)s, on credit terms, can be confirmed once they hand them in.",
            salesperson=self.user_id.name,
            amount=company.currency_id.format(status["overdue_amount"]),
            order=self.name,
        )

    def _is_cash_sale(self) -> bool:
        self.check_singleton()
        return bool(self.payment_term_id) and self.payment_term_id.is_immediate

    def _get_cash_sale_problem(self) -> str | None:
        self.check_singleton()
        if self.state != "done":
            return self.env._(
                "Confirm %(order)s before collecting it.", order=self.name
            )
        if not self._is_cash_sale():
            return self.env._(
                "%(order)s is not a cash sale: collect its invoices instead.",
                order=self.name,
            )
        if self.invoice_state != "to do":
            return self.env._(
                "%(order)s has nothing left to invoice; collect its invoices instead.",
                order=self.name,
            )
        return None

    def _settle_cash_sale(
        self,
        amount,
        date,
        collection_method,
        collector,
        check_date=None,
        hand_over=False,
    ):
        self.check_singleton()
        if problem := self._get_cash_sale_problem():
            raise UserError(problem)
        handed_over = self._reserve_cash_sale_hand_over() if hand_over else None
        invoices = (
            self.with_context(raise_if_nothing_to_invoice=True)
            ._create_invoices(final=True, date=date)
            .with_env(self.env)
        )
        invoices.write({"invoice_date": date})
        invoices._prepare_collected_invoice(collection_method)
        with invoices._exempting_posting_from_approval("payment_received"):
            invoices.action_post()
        invoices._issue_collected_invoice()
        payment = invoices._create_collection_payment(
            amount, date, collection_method, collector, check_date=check_date
        )
        if handed_over:
            handed_over._hand_over_at_sale()
        return payment

    def _reserve_cash_sale_hand_over(self):
        self.check_singleton()
        pickings = self.picking_ids.filtered(
            lambda picking: (
                picking.picking_type_code == "outgoing"
                and picking.state not in ("done", "cancel")
            )
        )
        if not pickings:
            return pickings
        pickings.is_handed_over_at_sale = True
        pickings._prepare_hand_over_at_sale()
        pickings.action_assign()
        short = pickings.move_ids.filtered(
            lambda move: move.state not in ("assigned", "done", "cancel")
        )
        if short:
            raise UserError(
                self.env._(
                    "%(products)s are not all at hand in %(location)s: leave the "
                    "delivery of %(order)s for later instead of handing it over now.",
                    products=", ".join(short.product_id.mapped("display_name")),
                    location=", ".join(short.location_id.mapped("display_name")),
                    order=self.name,
                )
            )
        return pickings
