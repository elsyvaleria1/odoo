from datetime import UTC, timedelta

from odoo import fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _is_cart_ready(self):
        res = super()._is_cart_ready()
        return res and (not self.is_rental_order or self._available_dates_for_renting())

    def _check_cart_is_ready_to_be_paid(self):
        self.check_singleton()
        if not self._available_dates_for_renting():
            _debug.logic(
                "rental_cart_refused", reason="dates_unavailable", order=self.id
            )
            raise ValidationError(
                self.env._(
                    "Some of your rental products cannot be rented during the selected period and your"
                    " cart must be updated. We're sorry for the inconvenience."
                )
            )
        return super()._check_cart_is_ready_to_be_paid()

    def _get_updated_quantity(
        self, order_line, product_id, new_qty, uom_id, **kwargs
    ) -> tuple:
        new_qty, warning = super()._get_updated_quantity(
            order_line, product_id, new_qty, uom_id, **kwargs
        )
        product = self.env["product.product"].browse(product_id)
        if new_qty > 0 and product.rent_ok and not self._is_valid_renting_dates():
            self.shop_warning = self._prepare_warning_renting(product)
            return 0, self.shop_warning

        return new_qty, warning

    def convert_to_website_tz(self, value):
        return (
            value.replace(tzinfo=UTC)
            .astimezone(timezone(self.website_id.tz))
            .replace(tzinfo=None)
        )

    def _is_valid_renting_dates(self) -> bool:
        self.check_singleton()
        if not self.has_rented_products:
            return True
        if not (self.rental_start_date and self.rental_return_date):
            _debug.logic("rental_dates_missing", order=self.id)
            return False
        days_forbidden = self.company_id._get_renting_forbidden_days()
        converted_rental_start_date = self.convert_to_website_tz(self.rental_start_date)
        converted_rental_return_date = self.convert_to_website_tz(
            self.rental_return_date
        )
        converted_current_datetime = self.convert_to_website_tz(fields.Datetime.now())
        return (
            converted_rental_start_date
            >= converted_current_datetime - timedelta(minutes=15)
            and converted_rental_start_date.isoweekday() not in days_forbidden
            and converted_rental_return_date.isoweekday() not in days_forbidden
            and self._get_renting_duration()
            >= self.company_id.renting_minimal_time_duration
        )

    def _cart_add(self, product_id, *args, start_date=None, end_date=None, **kwargs):
        product = self.env["product.product"].browse(product_id)
        if product.rent_ok:
            if not start_date or not end_date:
                first_pricing = self.env["product.pricing"]._get_first_suitable_pricing(
                    product, pricelist=self.pricelist_id
                )
                if first_pricing:
                    rec = first_pricing.recurrence_id
                    start_date, end_date = (
                        product.product_tmpl_id._get_default_renting_dates(
                            start_date,
                            end_date,
                            rec.duration,
                            rec.unit,
                            rec.pickup_time,
                            rec.return_time,
                        )
                    )
                else:
                    start_date = fields.Datetime.now().replace(
                        minute=0, second=0
                    ) + timedelta(hours=1)
                    end_date = start_date + timedelta(days=1)

            if (
                self.rental_start_date
                and self.rental_return_date
                and (
                    self.rental_start_date != start_date
                    or self.rental_return_date != end_date
                )
            ):
                _debug.logic(
                    "rental_dates_conflict",
                    order=self.id,
                    start=str(self.rental_start_date),
                    end=str(self.rental_return_date),
                )
                raise UserError(
                    self.env._(
                        "You cannot mix different rental periods in the same order."
                    )
                )
            self.update(
                {
                    "rental_start_date": start_date.replace(tzinfo=None),
                    "rental_return_date": end_date.replace(tzinfo=None),
                }
            )

        return super()._cart_add(
            product_id, *args, start_date=start_date, end_date=end_date, **kwargs
        )

    def _create_new_cart_line(self, *args, **kwargs):
        return super(
            SaleOrder, self.with_context(in_rental_app=True)
        )._create_new_cart_line(*args, **kwargs)

    def _sync_cart_after_update(self, *args, **kwargs) -> None:
        super()._sync_cart_after_update(*args, **kwargs)
        if self.is_rental_order and not self.has_rented_products:
            self.write(
                {
                    "is_rental_order": False,
                    "rental_start_date": False,
                    "rental_return_date": False,
                }
            )

    def _prepare_warning_renting(self, product):
        self.check_singleton()
        if not (self.rental_start_date and self.rental_return_date):
            return self.env._("No dates were specified on your rental order.")
        company = self.company_id
        days_forbidden = company._get_renting_forbidden_days()
        pickup_forbidden = self.rental_start_date.isoweekday() in days_forbidden
        return_forbidden = self.rental_return_date.isoweekday() in days_forbidden
        message = self.env._(
            """
            Some of your rental products (%(product)s) cannot be rented during the
            selected period and your cart must be updated. We're sorry for the
            inconvenience.
        """,
            product=product.name,
        )
        if self.rental_start_date < fields.Datetime.now():
            message += self.env._(
                """Your rental product cannot be pickedup in the past."""
            )
        elif pickup_forbidden and return_forbidden:
            message += self.env._(
                """
                Your rental product had invalid dates of pickup (%(start_date)s) and
                return (%(end_date)s). Unfortunately, we do not process pickups nor
                returns on those weekdays.
            """,
                start_date=self.rental_start_date,
                end_date=self.rental_return_date,
            )
        elif pickup_forbidden:
            message += self.env._(
                """
                Your rental product had invalid date of pickup (%(start_date)s).
                Unfortunately, we do not process pickups on that weekday.
            """,
                start_date=self.rental_start_date,
            )
        elif return_forbidden:
            message += self.env._(
                """
                Your rental product had invalid date of return (%(end_date)s).
                Unfortunately, we do not process returns on that weekday.
            """,
                end_date=self.rental_return_date,
            )
        minimal_duration = company.renting_minimal_time_duration
        if self._get_renting_duration() < minimal_duration:
            message += self.env._(
                """
                Your rental duration was too short. Unfortunately, we do not process
                rentals that last less than %(duration)s %(unit)s.
            """,
                duration=minimal_duration,
                unit=company.renting_minimal_time_unit,
            )

        return message

    def _get_renting_duration(self):
        return self.env["product.pricing"]._get_duration_vals(
            self.rental_start_date, self.rental_return_date
        )[self.company_id.renting_minimal_time_unit]

    def _is_renting_possible_in_hours(self) -> bool:
        rental_order_lines = self.line_ids.filtered("is_rental")
        return all(
            "hour" in line.product_id.product_pricing_ids.mapped("recurrence_id.unit")
            for line in rental_order_lines
        )

    def _all_hourly_periods_are_overnight(self) -> bool:
        rental_order_lines = self.line_ids.filtered("is_rental")
        for line in rental_order_lines:
            for pricing in line.product_id.product_pricing_ids:
                if (
                    pricing.recurrence_id.unit != "hour"
                    or not pricing.recurrence_id.overnight
                ):
                    return False
        return True

    def _cart_update_renting_period(self, start_date, end_date) -> None:
        self.check_singleton()
        current_start_date = self.rental_start_date
        current_end_date = self.rental_return_date
        self.write(
            {
                "rental_start_date": start_date,
                "rental_return_date": end_date,
            }
        )
        if not self._available_dates_for_renting():
            self.shop_warning = self.shop_warning or self.env._(
                "The new period is not valid for some products of your cart."
                " Your changes on the rental period are not taken into account."
            )
            self.write(
                {
                    "rental_start_date": current_start_date,
                    "rental_return_date": current_end_date,
                }
            )
        else:
            rental_lines = self.line_ids.filtered("is_rental")
            self.env.add_to_compute(rental_lines._fields["name"], rental_lines)
            self._recompute_rental_prices()
            rental_lines = self.line_ids.filtered("is_rental")
            rental_lines._compute_name()

    def _available_dates_for_renting(self):
        return self._is_valid_renting_dates()
