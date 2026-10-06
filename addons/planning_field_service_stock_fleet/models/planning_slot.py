from datetime import UTC, datetime, time, timedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    picking_ids = fields.One2many(
        comodel_name="stock.picking",
        inverse_name="planning_slot_id",
        string="Deliveries",
    )

    def _with_visit_deliveries_privilege(self, records):
        # a trip may be booked in another of the employee's companies than the visit
        return records.with_privilege(
            "planning_field_service_stock_fleet.privilege_visit_deliveries",
            reason="a visit ties and settles the deliveries its employee carries",
        ).with_context(allowed_company_ids=self.env.user.company_ids.ids)

    def _get_visit_day_bounds(self) -> tuple[datetime, datetime]:
        """The visit's local day, as naive UTC datetimes.

        :rtype: tuple[datetime, datetime]
        """
        self.check_singleton()
        tz = self._get_tzinfo()
        local_day = self.start_datetime.replace(tzinfo=UTC).astimezone(tz).date()
        day_start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(UTC)
        day_start = day_start.replace(tzinfo=None)
        return day_start, day_start + timedelta(days=1)

    def _get_trip_deliveries_domain(self):
        """The customer's deliveries that the visit's employee carries on his
        trips: still to hand over on a trip under way, or handed over from a trip
        on the day of the visit, which may have been declared afterwards."""
        self.check_singleton()
        day_start, day_end = self._get_visit_day_bounds()
        still_carried = Domain(
            [("state", "=", "assigned"), ("batch_id.trip_state", "=", "in_transit")]
        )
        handed_over = Domain(
            [
                ("state", "=", "done"),
                ("batch_id.date_departure", "!=", False),
                ("date_done", ">=", day_start),
                ("date_done", "<", day_end),
            ]
        )
        # Matched by user, not by employee: a salesperson has one employee per
        # company, and his trip may be booked in another one than the visit.
        return Domain(
            [
                ("planning_slot_id", "=", False),
                ("picking_type_code", "=", "outgoing"),
                ("batch_id.operator_id.user_id", "=", self.user_id.id),
                ("partner_id", "child_of", self.partner_id.commercial_partner_id.id),
                ("company_id", "in", self.user_id.company_ids.ids),
            ]
        ) & (still_carried | handed_over)

    def action_link_trip_deliveries(self) -> None:
        """Tie to each visit the deliveries its employee carries for its customer."""
        # Only who may edit the visit ties deliveries to it; the domain is the
        # visit's own reach (its employee's trips, its customer), which the
        # employee may not be able to read trip by trip.
        self.check_access("write")
        Picking = self._with_visit_deliveries_privilege(self.env["stock.picking"])
        for slot in self:
            if not (slot.partner_id and slot.user_id):
                continue
            pickings = Picking.browse(
                Picking._search(slot._get_trip_deliveries_domain(), bypass_access=True)
            )
            if pickings:
                _debug.lifecycle(
                    "visit_deliveries_linked", slot=slot, pickings=pickings
                )
                pickings.planning_slot_id = slot

    def action_sign_in(self):
        res = super().action_sign_in()
        self.action_link_trip_deliveries()
        return res

    def _action_complete(self):
        self.action_link_trip_deliveries()
        # the lock holds for a visitor without inventory rights
        Picking = self._with_visit_deliveries_privilege(self.env["stock.picking"])
        pending = Picking.browse(
            Picking._search(
                [
                    ("planning_slot_id", "in", self.ids),
                    ("state", "not in", ("done", "cancel")),
                    ("batch_id.date_departure", "!=", False),
                ],
                bypass_access=True,
            )
        )
        if pending:
            raise UserError(
                self.env._(
                    "Mark %(pickings)s as delivered or not delivered before completing the visit.",
                    pickings=", ".join(pending.mapped("name")),
                )
            )
        return super()._action_complete()
