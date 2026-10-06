from collections import defaultdict
from datetime import UTC

from odoo import fields
from odoo.http import request, route
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals

from odoo.addons.website_sale_renting.controllers.main import WebsiteSaleRenting

_debug = DebugLog(__name__)


class WebsiteSalePlanningRenting(WebsiteSaleRenting):
    @route()
    def renting_product_availabilities(self, product_id, min_date, max_date):
        product_sudo = request.env["product.product"].sudo().browse(product_id).exists()
        result = super().renting_product_availabilities(product_id, min_date, max_date)
        if (
            product_sudo.type == "service"
            and product_sudo.rent_ok
            and product_sudo.planning_enabled
            and (
                resources := product_sudo.planning_role_id.filtered(
                    "sync_shift_rental"
                ).resource_ids
            )
        ):
            min_date = fields.Datetime.to_datetime(min_date)
            max_date = fields.Datetime.to_datetime(max_date)
            slots_sudo = (
                self.env["planning.slot"]
                .sudo()
                .search(
                    [
                        ("resource_id", "in", resources.ids),
                        ("start_datetime", "<=", max_date),
                        ("end_datetime", ">=", min_date),
                    ],
                    order="start_datetime",
                )
            )
            _debug.pipeline(
                "planning_availabilities",
                product=product_sudo,
                resources=resources,
                slots=slots_sudo,
            )
            rented_quantities, slot_periods_per_resource = self._booked_periods(
                slots_sudo
            )

            if human_resources := resources.filtered(lambda r: r.type == "human"):
                min_date_in_utc = min_date.replace(tzinfo=UTC)
                max_date_in_utc = max_date.replace(tzinfo=UTC)
                unavailable_intervals_per_resource_id = (
                    human_resources._unavailable_intervals_by_resource(
                        min_date_in_utc, max_date_in_utc
                    )
                )
                for (
                    resource_id,
                    intervals,
                ) in unavailable_intervals_per_resource_id.items():
                    slot_intervals = slot_periods_per_resource.get(
                        resource_id, Intervals()
                    )
                    for start_dt, end_dt, _dummy in intervals - slot_intervals:
                        if start_dt < max_date_in_utc and end_dt > min_date_in_utc:
                            naive_start_dt = (
                                max(start_dt, min_date_in_utc)
                                .astimezone(UTC)
                                .replace(tzinfo=None)
                            )
                            naive_end_dt = (
                                min(end_dt, max_date_in_utc)
                                .astimezone(UTC)
                                .replace(tzinfo=None)
                            )
                            rented_quantities[naive_start_dt] += 1
                            rented_quantities[naive_end_dt] -= 1
            key_dates = sorted(set(rented_quantities.keys()) | {min_date, max_date})

            availabilities = self._availability_windows(
                key_dates, rented_quantities, len(resources), min_date, max_date
            )
            _debug.logic(
                "availability_windows",
                product=product_sudo,
                capacity=len(resources),
                key_dates=len(key_dates),
                windows=len(availabilities),
            )
            result["renting_availabilities"] = availabilities
        return result

    @staticmethod
    def _booked_periods(slots_sudo):
        rented_quantities = defaultdict(int)
        slot_periods_per_resource = {}
        for resource, slots in slots_sudo.grouped("resource_id").items():
            slot_periods_per_resource[resource.id] = Intervals([])
            for slot in slots:
                rented_quantities[slot.start_datetime] += 1
                rented_quantities[slot.end_datetime] -= 1
                slot_periods_per_resource[resource.id] |= Intervals(
                    [
                        (
                            slot.start_datetime.replace(tzinfo=UTC),
                            slot.end_datetime.replace(tzinfo=UTC),
                            slot,
                        )
                    ]
                )
        _debug.pipeline(
            "booked_periods",
            slots=slots_sudo,
            resources_booked=len(slot_periods_per_resource),
            transitions=len(rented_quantities),
        )
        return rented_quantities, slot_periods_per_resource

    @staticmethod
    def _availability_windows(
        key_dates, rented_quantities, capacity, min_date, max_date
    ):
        availabilities = []
        current_qty_available = capacity
        for i in range(1, len(key_dates)):
            start_dt = key_dates[i - 1]
            if start_dt > max_date:
                break
            current_qty_available -= rented_quantities[start_dt]
            if start_dt >= min_date:
                availabilities.append(
                    {
                        "start": start_dt,
                        "end": key_dates[i],
                        "quantity_available": current_qty_available,
                    }
                )
        return availabilities
