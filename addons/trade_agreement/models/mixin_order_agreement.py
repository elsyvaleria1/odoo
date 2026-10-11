from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

from odoo.addons.trade.tools import direction_of

_debug = DebugLog(__name__)


class MixinOrderAgreement(models.AbstractModel):
    _name = "mixin.order.agreement"
    _description = "Order Placed Against an Agreement"

    @api.onchange("agreement_id")
    def _onchange_agreement_id(self) -> None:
        agreement = self.agreement_id
        if not agreement:
            return
        self = self.with_company(self.company_id)
        direction = direction_of(self)
        partner = self.partner_id or agreement.partner_id
        fiscal_position = (
            self.env["account.fiscal.position"]
            .with_company(self.company_id)
            ._get_fiscal_position(partner)
        )
        self.partner_id = partner.id
        self.fiscal_position_id = fiscal_position.id
        self.payment_term_id = partner[direction.partner_payment_term_field].id
        self.company_id = agreement.company_id.id
        self.currency_id = agreement.currency_id.id
        origins = self.origin.split(", ") if self.origin else []
        if agreement.name not in origins:
            self.origin = ", ".join([*origins, agreement.name])
        self.notes = agreement.description
        self.date_order = (
            max(
                fields.Datetime.now(), fields.Datetime.to_datetime(agreement.date_start)
            )
            if agreement.date_start
            else fields.Datetime.now()
        )
        if self.state != "draft":
            return
        _debug.logic(
            "order_filled_from_agreement",
            agreement=agreement,
            lines=len(agreement.line_ids),
        )
        self.line_ids = [
            Command.create(
                line._prepare_order_line_values(
                    product_qty=(
                        0.0
                        if agreement.agreement_type == "blanket_order"
                        else line.product_qty
                    ),
                    tax_ids=fiscal_position.map_tax(
                        line.product_id[direction.product_taxes_field].filtered(
                            lambda tax: any(
                                tax._serves_company(company)
                                for company in agreement.company_id.parent_ids
                            )
                        )
                    ).ids,
                )
            )
            for line in agreement.line_ids.filtered("product_id")
        ]

    agreement_warning = fields.Text(compute="_compute_agreement_warning")

    @api.depends(
        "agreement_id.overrelease_policy",
        "date_order",
        "line_ids.agreement_line_id",
        "line_ids.product_qty",
        "line_ids.price_subtotal",
    )
    def _compute_agreement_warning(self) -> None:
        for order in self:
            breaches = (
                order._get_agreement_breaches()
                if order.agreement_id.overrelease_policy != "allow"
                else []
            )
            order.agreement_warning = "\n".join(breaches) if breaches else False

    def _get_agreement_breaches(self):
        self.check_singleton()
        agreement = self.agreement_id
        if not agreement or self.state != "draft":
            return []
        breaches = []
        party = agreement.partner_id.commercial_partner_id
        if party and self.partner_id.commercial_partner_id != party:
            breaches.append(
                self.env._(
                    "%(partner)s is not a party to %(agreement)s.",
                    partner=self.partner_id.display_name,
                    agreement=agreement.name,
                )
            )
        date = fields.Date.to_date(self.date_order)
        if date and (
            (agreement.date_start and date < agreement.date_start)
            or (agreement.date_end and date > agreement.date_end)
        ):
            breaches.append(
                self.env._(
                    "The order date is outside %(agreement)s's validity.",
                    agreement=agreement.name,
                )
            )
        lines = self.line_ids.filtered(
            lambda line: (
                line.agreement_line_id.product_qty
                and line.agreement_line_id.product_uom_id
                and line.product_uom_id._has_common_reference(
                    line.agreement_line_id.product_uom_id
                )
            )
        )
        if agreement.commitment == "quantity":
            for agreement_line, order_lines in lines.grouped(
                "agreement_line_id"
            ).items():
                wanted = sum(
                    order_line.product_uom_id._get_quantity_in_unit(
                        order_line.product_qty, agreement_line.product_uom_id
                    )
                    for order_line in order_lines
                )
                if (
                    agreement_line.product_uom_id.compare(
                        wanted, agreement_line.qty_remaining
                    )
                    > 0
                ):
                    breaches.append(
                        self.env._(
                            "%(product)s: %(wanted)s ordered, %(remaining)s left on "
                            "%(agreement)s.",
                            product=agreement_line.product_id.display_name,
                            wanted=wanted,
                            remaining=agreement_line.qty_remaining,
                            agreement=agreement.name,
                        )
                    )
        elif agreement.commitment == "value":
            amount = sum(
                self.currency_id._convert(
                    line.price_subtotal,
                    agreement.currency_id,
                    agreement.company_id,
                    self.date_order or fields.Date.context_today(self),
                )
                for line in lines
            )
            if (
                agreement.currency_id.compare_amounts(
                    amount, agreement.amount_remaining
                )
                > 0
            ):
                breaches.append(
                    self.env._(
                        "This order spends %(amount)s, %(remaining)s left on "
                        "%(agreement)s.",
                        amount=agreement.currency_id.format(amount),
                        remaining=agreement.currency_id.format(
                            agreement.amount_remaining
                        ),
                        agreement=agreement.name,
                    )
                )
        return breaches

    def _get_confirm_validation_methods(self):
        return [
            *super()._get_confirm_validation_methods(),
            "_check_confirm_agreement",
        ]

    def _check_confirm_agreement(self) -> None:
        blocked = {
            order: breaches
            for order in self.filtered(
                lambda order: order.agreement_id.overrelease_policy == "block"
            )
            if (breaches := order._get_agreement_breaches())
        }
        if not blocked:
            return
        _debug.logic("confirm_refused", orders=list(blocked), reason="agreement")
        raise UserError(
            "\n\n".join(
                self.env._(
                    "%(order)s goes beyond its agreement:\n%(breaches)s",
                    order=order.display_name,
                    breaches="\n".join(breaches),
                )
                for order, breaches in blocked.items()
            )
        )

    def _post_agreement_link(self, edit=False) -> None:
        for order in self.filtered("agreement_id"):
            order.message_post_with_source(
                "mail.message_origin_link",
                render_values={
                    "self": order,
                    "origin": order.agreement_id,
                    "edit": edit,
                },
                subtype_xmlid="mail.mt_note",
            )

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._post_agreement_link()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if vals.get("agreement_id"):
            self._post_agreement_link(edit=True)
        return result


class MixinOrderLineAgreement(models.AbstractModel):
    _name = "mixin.order.line.agreement"
    _description = "Order Line Placed Against an Agreement Line"

    agreement_line_id = fields.Many2one(
        comodel_name="mixin.agreement.line",
        string="Agreement Line",
        compute="_compute_agreement_line_id",
        store=True,
        index="btree_not_null",
        copy=False,
        readonly=False,
    )

    @api.depends("order_id.agreement_id", "product_id", "product_uom_id")
    def _compute_agreement_line_id(self) -> None:
        for line in self:
            line.agreement_line_id = line._find_agreement_line()

    def _find_agreement_line(self):
        self.check_singleton()
        product, uom = self.product_id, self.product_uom_id
        lines = self.order_id.agreement_id.line_ids
        candidates = lines.filtered(
            lambda agreement_line: agreement_line.product_id == product
        )
        if candidates:
            return (
                candidates.filtered(
                    lambda agreement_line: agreement_line.product_uom_id == uom
                )[:1]
                or candidates[:1]
            )
        category = product.categ_id
        covering = lines.filtered(
            lambda agreement_line: (
                (
                    agreement_line.product_category_id
                    and category.parent_path.startswith(
                        agreement_line.product_category_id.parent_path
                    )
                )
                if category
                else False
            )
        )
        return covering.sorted(
            lambda agreement_line: len(agreement_line.product_category_id.parent_path),
            reverse=True,
        )[:1]

    def _get_auto_price_and_discount(self):
        price, discount = super()._get_auto_price_and_discount()
        agreement_line = self._find_agreement_line()
        if agreement_line.product_category_id:
            discount = agreement_line.discount
        return price, discount

    def _get_released_qty(self):
        self.check_singleton()
        taken_back = self._get_returned_qty()
        if "qty_invoiced" in self._fields:
            taken_back = max(taken_back, self._get_refunded_qty())
        return max(self.product_qty - taken_back, 0.0)
