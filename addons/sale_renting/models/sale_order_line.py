from datetime import UTC, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, format_datetime, format_time

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    product_id = fields.Many2one(group_expand="_read_group_expand_product_id")

    order_is_rental = fields.Boolean(
        related="order_id.is_rental_order",
        depends=["order_id"],
    )

    is_rental = fields.Boolean(
        compute="_compute_is_rental",
        precompute=True,
        store=True,
        copy=True,
        readonly=False,
    )

    qty_returned = fields.Float(
        string="Returned",
        default=0.0,
        copy=False,
    )
    start_date = fields.Datetime(
        related="order_id.rental_start_date",
        readonly=False,
    )
    return_date = fields.Datetime(
        related="order_id.rental_return_date",
        readonly=False,
    )
    reservation_begin = fields.Datetime(
        string="Pickup date - padding time",
        compute="_compute_reservation_begin",
        store=True,
    )

    is_product_rentable = fields.Boolean(
        related="product_id.rent_ok",
        depends=["product_id"],
    )

    is_late = fields.Boolean(related="order_id.is_late")
    team_id = fields.Many2one(related="order_id.team_id")
    country_id = fields.Many2one(related="order_id.partner_id.country_id")
    rental_status = fields.Selection(
        selection=[
            ("pickup", "Booked"),
            ("return", "Picked-Up"),
            ("returned", "Returned"),
        ],
        compute="_compute_rental_status",
        search="_search_rental_status",
    )
    rental_color = fields.Integer(compute="_compute_rental_color")

    def _domain_product_id(self):
        super_part = ",".join(str(leaf) for leaf in super()._domain_product_id())
        rent_part = "'&', ('rent_ok', '=', True), ('rent_ok', '=', order_is_rental)"
        return f"['|', {rent_part}, {super_part}]"

    @api.depends("partner_id.name", "order_id.name", "product_id.name")
    @api.depends_context("sale_renting_short_display_name")
    def _compute_display_name(self):
        if not self.env.context.get("sale_renting_short_display_name"):
            return super()._compute_display_name()
        for sol in self:
            descriptions = []
            group_by = self.env.context.get("group_by", [])

            if "partner_id" not in group_by:
                descriptions.append(sol.partner_id.display_name)
            if "product_id" not in group_by:
                descriptions.append(sol.product_id.name)
            descriptions.append(sol.order_id.name)

            sol.display_name = ", ".join(descriptions)
        return None

    @api.depends("order_id.rental_start_date")
    def _compute_reservation_begin(self) -> None:
        lines = self.filtered("is_rental")
        for line in lines:
            line.reservation_begin = line.order_id.rental_start_date
        (self - lines).reservation_begin = None

    @api.onchange("qty_transferred")
    def _onchange_qty_transferred(self) -> None:
        self.product_qty = max(self.product_qty, self.qty_transferred)

    @api.depends("is_rental")
    def _compute_qty_transferred_method(self) -> None:
        rental_lines = self.filtered("is_rental")
        super(SaleOrderLine, self - rental_lines)._compute_qty_transferred_method()
        rental_lines.qty_transferred_method = "manual"

    @api.depends("is_rental")
    def _compute_name(self):
        super()._compute_name()

    @api.depends("product_id")
    def _compute_is_rental(self) -> None:
        for line in self:
            line.is_rental = line.is_product_rentable and line.env.context.get(
                "in_rental_app"
            )

    @api.depends("is_rental")
    def _compute_product_readonly(self) -> None:
        rental_lines = self.filtered("is_rental")
        super(SaleOrderLine, self - rental_lines)._compute_product_readonly()
        rental_lines.product_readonly = False

    def _compute_pricelist_item_id(self) -> None:
        rental_lines = self.filtered("is_rental")
        super(SaleOrderLine, self - rental_lines)._compute_pricelist_item_id()
        rental_lines.pricelist_item_id = False

    @api.depends("product_qty", "qty_transferred", "qty_returned")
    def _compute_rental_status(self) -> None:
        self.rental_status = False
        for sol in self.filtered("order_is_rental"):
            if sol.qty_transferred < sol.product_qty:
                sol.rental_status = "pickup"
            elif (
                sol.qty_returned >= sol.qty_transferred
                and sol.qty_transferred >= sol.product_qty
            ):
                sol.rental_status = "returned"
            else:
                sol.rental_status = "return"

    @api.depends("order_is_rental", "state", "rental_status", "is_late")
    def _compute_rental_color(self) -> None:
        self.rental_color = 0
        for sol in self.filtered("order_is_rental"):
            if sol.state in ("draft", "sent"):
                sol.rental_color = 5
                continue
            match sol.rental_status:
                case "pickup":
                    sol.rental_color = 3 if sol.is_late else 4
                case "return":
                    sol.rental_color = 6 if sol.is_late else 2
                case "returned":
                    sol.rental_color = 7

    def _search_rental_status(self, operator, values):
        if operator != "in":
            return NotImplemented

        return (
            Domain("order_is_rental", "=", False) if False in values else Domain.FALSE
        ) | (
            Domain([("order_is_rental", "=", True)])
            & Domain.custom(
                to_sql=lambda model, alias, query: SQL(
                    """
                    CASE
                        WHEN %(qty_transferred)s < %(product_qty)s THEN 'pickup'
                        WHEN (
                            %(qty_returned)s >= %(qty_transferred)s
                            AND %(qty_transferred)s >= %(product_qty)s
                        ) THEN 'returned'
                        ELSE 'return'
                    END IN %(values)s
                    """,
                    product_qty=model._field_to_sql(alias, "product_qty", query),
                    qty_transferred=model._field_to_sql(
                        alias, "qty_transferred", query
                    ),
                    qty_returned=model._field_to_sql(alias, "qty_returned", query),
                    values=tuple(values),
                )
            )
        )

    def _read_group_expand_product_id(self, products, domain):
        if not self.env.context.get("in_rental_schedule"):
            return self.env["product.product"]

        expanded_products = self.env["product.product"].search(
            Domain(
                [
                    ("id", "not in", products.ids),
                    ("rent_ok", "=", True),
                    ("type", "!=", "combo"),
                ]
            ),
            limit=80 - len(products),
        )
        return products + expanded_products

    def web_gantt_write(self, vals):
        self.check_singleton()
        result = {"notifications": [], "actions": []}

        if (
            self.order_id.rental_status in ("return", "returned")
            and "start_date" in vals
        ):
            _debug.logic("gantt_write_refused", line=self, reason="already_picked_up")
            raise UserError(self.env._("The order is already picked-up."))
        if self.order_id.rental_status == "returned" and "return_date" in vals:
            _debug.logic("gantt_write_refused", line=self, reason="already_returned")
            raise UserError(self.env._("The order is already returned."))

        updating_duration = "start_date" in vals or "return_date" in vals
        old_duration = self.return_date - self.start_date if updating_duration else None

        if not self.write(vals):
            raise UserError(self.env._("An error occured. Please try again."))

        if updating_duration:
            new_duration = self.return_date - self.start_date
            if old_duration != new_duration:
                _debug.lifecycle(
                    "rental_duration_changed", line=self, order=self.order_id
                )
                self.order_id.line_ids.filtered("is_rental")._compute_name()
                self.order_id.action_update_rental_prices()
                result["notifications"].append(
                    {
                        "type": "success",
                        "message": self.env._("The rental prices have been updated."),
                        "code": "rental_price_update",
                    }
                )

        return result

    def _get_line_multiline_description_sale(self):
        res = super()._get_line_multiline_description_sale()
        if self.is_rental:
            self.order_id._rental_set_dates()
            res += self._get_rental_order_line_description()
        return res

    def _get_rental_order_line_description(self):
        tz = self._get_tz()
        start_date = self.order_id.rental_start_date
        return_date = self.order_id.rental_return_date
        env = self.with_context(use_babel=True).env

        if (
            start_date
            and return_date
            and start_date.replace(tzinfo=UTC).astimezone(timezone(tz)).date()
            == return_date.replace(tzinfo=UTC).astimezone(timezone(tz)).date()
        ):
            return_date_part = format_time(env, return_date, tz=tz, time_format="short")
        else:
            return_date_part = format_datetime(
                env, return_date, tz=tz, dt_format="short"
            )
        start_date_part = format_datetime(env, start_date, tz=tz, dt_format="short")
        return self.env._(
            "\n%(from_date)s to %(to_date)s",
            from_date=start_date_part,
            to_date=return_date_part,
        )

    def _use_template_name(self):
        if self.is_rental:
            return False
        return super()._use_template_name()

    def _create_delay_line(self, qty_returned) -> None:
        self.check_singleton()

        self = self.with_company(self.company_id)
        now = fields.Datetime.now()

        if self.return_date + timedelta(hours=self.company_id.min_extra_hour) >= now:
            _debug.logic("delay_line_skipped", line=self, reason="within_grace")
            return

        duration = now - self.return_date
        delay_price = self.product_id._get_delay_price(duration)
        if delay_price <= 0.0:
            _debug.logic("delay_line_skipped", line=self, reason="no_delay_price")
            return

        delay_product = self.company_id.extra_product
        if not delay_product:
            delay_product = (
                self.env["product.product"]
                .with_context(active_test=False)
                .search(
                    [("default_code", "=", "RENTAL"), ("type", "=", "service")], limit=1
                )
            )
            if not delay_product:
                delay_product = self.env["product.product"].create(
                    {
                        "name": "Rental Delay Cost",
                        "standard_price": 0.0,
                        "type": "service",
                        "default_code": "RENTAL",
                        "purchase_ok": False,
                    }
                )
            _debug.lifecycle(
                "delay_product_resolved",
                company=self.company_id,
                product=delay_product,
            )
            self.company_id.extra_product = delay_product

        if not delay_product.active:
            _debug.logic("delay_line_skipped", line=self, reason="product_archived")
            return

        delay_price = self._convert_to_sol_currency(
            delay_price, self.product_id.currency_id
        )

        order_line_vals = self._prepare_delay_line_vals(
            delay_product, delay_price * qty_returned
        )

        _debug.lifecycle(
            "delay_line_created",
            line=self,
            product=delay_product,
            price=delay_price,
            returned=qty_returned,
        )
        self.order_id.write(
            {
                "line_ids": [Command.create(order_line_vals)],
            }
        )

    def _prepare_delay_line_vals(self, delay_product, delay_price) -> dict:
        delay_line_description = self._get_delay_line_description()
        return {
            "name": delay_line_description,
            "product_id": delay_product.id,
            "product_qty": 1,
            "qty_transferred": 1,
            "price_unit": delay_price,
        }

    def _get_delay_line_description(self) -> str:
        tz = self._get_tz()
        env = self.with_context(use_babel=True).env
        expected_date = format_datetime(env, self.return_date, tz=tz, dt_format=False)
        now = format_datetime(env, fields.Datetime.now(), tz=tz, dt_format=False)
        return "%s\n%s\n%s" % (
            self.product_id.name,
            self.env._("Expected: %(date)s", date=expected_date),
            self.env._("Returned: %(date)s", date=now),
        )

    def _get_tz(self):
        return self.env.context.get("tz") or self.env.user.tz or "UTC"

    def _get_pricelist_price(self):
        self.check_singleton()
        if self.is_rental:
            self.order_id._rental_set_dates()
            return self.order_id.pricelist_id._get_product_price(
                self.product_id.with_context(**self._prepare_product_price_context()),
                self.product_qty or 1.0,
                currency=self.currency_id,
                uom=self.product_uom_id,
                date=self.order_id.date_order or fields.Date.today(),
                start_date=self.start_date,
                end_date=self.return_date,
            )
        return super()._get_pricelist_price()
