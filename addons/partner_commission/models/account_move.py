from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.tools import format_date, formatLang


class AccountMove(models.Model):
    _inherit = "account.move"

    referrer_id = fields.Many2one(
        comodel_name="res.partner",
        domain=[("grade_id", "!=", False)],
        tracking=True,
    )
    commission_po_line_id = fields.Many2one(
        comodel_name="purchase.order.line",
        string="Referrer Purchase Order line",
        copy=False,
    )

    def _get_sales_representative(self):
        self.check_singleton()

        sub = self.invoice_line_ids.mapped("subscription_id")[:1]
        sales_rep = (sub and sub.user_id) or False

        if not sales_rep:
            so = self.invoice_line_ids.mapped("sale_line_ids.order_id")[:1]
            sales_rep = (so and so.user_id) or False

        return sales_rep

    def _get_domain_commission_purchase_order(self) -> list:
        self.check_singleton()

        return [
            ("partner_id", "=", self.referrer_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "=", "draft"),
            ("currency_id", "=", self.currency_id.id),
            ("purchase_type", "=", "commission"),
        ]

    def _get_or_create_commission_purchase_order(self):
        self.check_singleton()
        purchase = (
            self.env["purchase.order"]
            .sudo()
            .search(self._get_domain_commission_purchase_order(), limit=1)
        )

        if not purchase:
            purchase = (
                self.env["purchase.order"]
                .with_context(mail_create_nosubscribe=True)
                .sudo()
                .create(
                    {
                        "partner_id": self.referrer_id.id,
                        "currency_id": self.currency_id.id,
                        "company_id": self.company_id.id,
                        "fiscal_position_id": self.env["account.fiscal.position"]
                        .with_company(self.company_id)
                        ._get_fiscal_position(self.referrer_id)
                        .id,
                        "payment_term_id": self.referrer_id.with_company(
                            self.company_id
                        ).property_supplier_payment_term_id.id,
                        "user_id": False,
                        "dest_address_id": self.referrer_id.id,
                        "origin": self.name,
                        "purchase_type": "commission",
                    }
                )
            )

        return purchase

    def _create_commission(self) -> None:
        for move in self.filtered(
            lambda m: m.move_type in ["out_invoice", "in_invoice", "out_refund"]
        ):
            if move.commission_po_line_id or not move.referrer_id:
                continue
            sign = 1 if move.move_type in ["out_invoice", "in_invoice"] else -1
            comm_by_rule = defaultdict(float)

            product = None
            order = None
            desc_lines = ""
            for line in move.invoice_line_ids:
                rule = line._get_commission_rule()
                if rule:
                    if not product:
                        product = rule.plan_id.product_id
                    if not order:
                        order = line.subscription_id
                        desc_lines += self.env._(
                            "\n%(product)s: from %(start_date)s to %(end_date)s",
                            product=line.product_id.name,
                            start_date=format_date(self.env, line.deferred_start_date),
                            end_date=format_date(self.env, line.deferred_end_date),
                        )
                    commission = move.currency_id.round(
                        line.price_subtotal * rule.rate / 100.0
                    )
                    comm_by_rule[rule] += commission

            for r, amount in comm_by_rule.items():
                if r.is_capped:
                    amount = min(amount, r.max_commission)
                    comm_by_rule[r] = amount

            total = sum(comm_by_rule.values())
            if not total:
                continue

            desc = self.env._(
                "Commission on %(invoice)s, %(partner)s, %(amount)s",
                invoice=move.name,
                partner=move.partner_id.name,
                amount=formatLang(
                    self.env, move.amount_untaxed, currency_obj=move.currency_id
                ),
            )
            if order:
                desc += f"\n{order.name}, {desc_lines}"
                end_date_list = move.invoice_line_ids.mapped("deferred_end_date")
                start_date_list = move.invoice_line_ids.mapped("deferred_start_date")
                if any(start_date_list) and any(end_date_list):
                    date_to = max(ed for ed in end_date_list if ed)
                    date_from = min(sd for sd in start_date_list if sd)
                    delta = relativedelta(date_to + relativedelta(days=1), date_from)
                    n_months = delta.years * 12 + delta.months + delta.days // 30
                    if n_months:
                        desc += self.env._(" (%d month(s))", n_months)

            purchase = move._get_or_create_commission_purchase_order()
            purchase.message_subscribe(
                partner_ids=(
                    move._get_sales_representative() or purchase
                ).partner_id.ids
            )

            line = (
                self.env["purchase.order.line"]
                .sudo()
                .create(
                    {
                        "name": desc,
                        "product_id": product.id,
                        "product_qty": 1,
                        "price_unit": total * sign,
                        "product_uom_id": product.uom_id.id,
                        "date_commitment": fields.Datetime.now(),
                        "order_id": purchase.id,
                        "qty_transferred": 1,
                    }
                )
            )

            if move.move_type in ["out_invoice", "in_invoice"]:
                move.commission_po_line_id = line
                msg_body = self.env._(
                    "New commission. Invoice: %(link)s. Amount: %(amount)s.",
                    link=move._get_html_link(),
                    amount=formatLang(self.env, total, currency_obj=move.currency_id),
                )
            else:
                move.commission_po_line_id = line
                msg_body = self.env._(
                    "Commission refunded. Invoice: %(link)s. Amount: %(amount)s.",
                    link=move._get_html_link(),
                    amount=formatLang(self.env, total, currency_obj=move.currency_id),
                )
            purchase.message_post(body=msg_body)

    def _refund_commission(self):
        return self._create_commission()

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if not default_values_list:
            default_values_list = [{} for move in self]
        for move, default_values in zip(self, default_values_list, strict=False):
            default_values.update(
                {
                    "referrer_id": move.referrer_id.id,
                }
            )
        return super()._reverse_moves(
            default_values_list=default_values_list, cancel=cancel
        )

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        self.filtered(lambda move: move.move_type == "out_invoice")._create_commission()
        self.filtered(
            lambda m: (
                m.move_type == "out_refund"
                and m.reversed_entry_id
                and m.reversed_entry_id.commission_po_line_id
            )
        )._create_commission()
        return res

    def action_draft(self):
        res = super().action_draft()
        for move in self:
            cpo = (
                self.env["purchase.order"]
                .sudo()
                .search(move._get_domain_commission_purchase_order(), limit=1)
            )
            if cpo and move.move_type == "out_refund" and cpo.state == "draft":
                message_body = self.env._(
                    "The commission partner order %s must be checked manually (especially refund lines which can be duplicated).",
                    cpo._get_html_link(),
                )
                move.message_post(body=message_body)
        return res


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _get_commission_rule(self):
        self.check_singleton()
        template = self.env["sale.order.template"]
        sale_order = self.subscription_id or self.sale_line_ids.order_id
        if len(sale_order) == 1:
            template = sale_order.template_id
        template_products = template.line_ids.product_id.mapped("product_tmpl_id")
        template_id = (
            template.id
            if template and self.product_id.product_tmpl_id.id in template_products.ids
            else None
        )
        sub_pricelist = self.subscription_id.pricelist_id
        pricelist_id = (
            sub_pricelist and sub_pricelist.id
        ) or self.sale_line_ids.mapped("order_id.pricelist_id")[:1].id

        plan = (
            self.sale_line_ids.order_id.commission_plan_id
            or self.move_id.referrer_id.commission_plan_id
        )
        if self.subscription_id:
            plan = self.subscription_id.commission_plan_id

        if not plan:
            return self.env["commission.rule"]

        return plan._match_rules(self.product_id, template_id, pricelist_id)
