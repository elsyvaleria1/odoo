from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.base.models.resource_utils import CUSTODY_SILENT

AUTHORISE_TYPE = "stock_fleet_exit.activity_type_exit_authorise"


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    is_fleet_exit = fields.Boolean(
        related="picking_type_id.fleet_exit",
        string="Is a Route",
    )
    passenger_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="stock_picking_batch_passenger_rel",
        column1="batch_id",
        column2="employee_id",
        string="Passengers",
        check_company=True,
        help="Who rides along besides the driver, picked up when they joined.",
    )
    exit_holder_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Usual Operator",
        copy=False,
        readonly=True,
        help="Who held the vehicle when the route departed; it goes back to them "
        "when the route closes.",
    )
    exit_requested_uid = fields.Many2one(
        comodel_name="res.users",
        string="Requested By",
        copy=False,
        readonly=True,
    )
    exit_authorised_uid = fields.Many2one(
        comodel_name="res.users",
        string="Authorised By",
        copy=False,
        readonly=True,
    )
    exit_stay_location = fields.Char(
        string="Stays At",
        copy=False,
        help="Where the vehicle stayed when the route closed away from the "
        "warehouse: the workshop, the dealership. It is the vehicle's location "
        "until a later route brings it back.",
    )
    exit_kept_location = fields.Char(
        copy=False,
        readonly=True,
        help="The vehicle's location before it stayed away, given back when a "
        "later route brings it back to the warehouse.",
    )
    exit_activity_summary = fields.Char(
        string="Route Activities",
        compute="_compute_exit_activity_summary",
    )
    exit_can_decide = fields.Boolean(compute="_compute_exit_can_decide")
    trip_distance = fields.Float(
        string="Distance",
        compute="_compute_trip_distance",
        store=True,
        help="Odometer at return less odometer at departure.",
    )
    trip_hours = fields.Float(
        string="Hours Out",
        compute="_compute_trip_hours",
        store=True,
        aggregator="avg",
    )

    @api.depends("odometer_departure", "odometer_return")
    def _compute_trip_distance(self) -> None:
        for batch in self:
            batch.trip_distance = (
                batch.odometer_return - batch.odometer_departure
                if batch.odometer_return and batch.odometer_departure
                else 0.0
            )

    @api.depends("date_departure", "date_return")
    def _compute_trip_hours(self) -> None:
        for batch in self:
            batch.trip_hours = (
                (batch.date_return - batch.date_departure).total_seconds() / 3600
                if batch.date_departure and batch.date_return
                else 0.0
            )

    @api.depends("activity_ids")
    @api.depends_context("lang")
    def _compute_exit_activity_summary(self) -> None:
        activities = self.filtered("is_fleet_exit")._get_exit_activities()
        for batch in self:
            batch.exit_activity_summary = ", ".join(
                activity.activity_type_id._get_exit_label()
                for activity in activities.sorted("id")
                if activity.res_id == batch.id
            )

    @api.depends("activity_ids")
    @api.depends_context("uid")
    def _compute_exit_can_decide(self) -> None:
        asked = self._get_exit_authorisations().filtered(
            lambda activity: activity.user_id == self.env.user
        )
        for batch in self:
            batch.exit_can_decide = batch.id in asked.mapped("res_id")

    @api.model
    def _prepare_name(self, picking_type, sequence_code, company_id) -> str:
        if picking_type.fleet_exit:
            return (
                self.env["ir.sequence"]
                .with_company(company_id)
                .next_by_code("stock.fleet.exit")
                or "/"
            )
        return super()._prepare_name(picking_type, sequence_code, company_id)

    @api.model
    def _get_exit_gps_odometer(self, vehicle) -> float:
        return 0.0

    @api.model
    def _get_exit_gps_place(self, vehicle) -> str | None:
        return None

    def _get_exit_activities(self, done=None):
        domain = [
            ("res_model", "=", self._name),
            ("res_id", "in", self.ids),
            ("activity_type_id.fleet_exit_role", "=", "destination"),
        ]
        if done is not None:
            domain.append(("active", "=", not done))
        return self.env["mail.activity"].with_context(active_test=False).search(domain)

    def _get_exit_authorisations(self):
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "in", self.ids),
                ("activity_type_id.fleet_exit_role", "=", "authorisation"),
            ]
        )

    @api.model
    def _get_exit_authorisers(self, company):
        group = self.env.ref("stock_fleet_exit.group_fleet_exit_authoriser")
        return self.env["res.users"].search(
            [("all_group_ids", "in", group.id), ("company_ids", "in", company.id)]
        )

    def _add_exit_activity(self, activity_type, user=None):
        self.check_singleton()
        if self.state in ("done", "cancel") or self.date_return:
            raise UserError(self.env._("Route %(route)s is closed.", route=self.name))
        return self.env["mail.activity"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id(self._name),
                "res_id": self.id,
                "activity_type_id": activity_type.id,
                "user_id": (user or self.operator_id.user_id or self.env.user).id,
                "summary": activity_type.name,
            }
        )

    def action_confirm(self):
        self.check_singleton()
        if self.is_fleet_exit and not self.picking_ids:
            self.state = "in_progress"
            return None
        return super().action_confirm()

    def _trip_departure_missing(self):
        if not self.is_fleet_exit or self.picking_ids:
            return super()._trip_departure_missing()
        return [
            *self._get_exit_request_missing(),
            *([] if self.supervisor_id else [self.env._("Supervisor")]),
        ]

    def _get_exit_request_missing(self) -> list[str]:
        self.check_singleton()
        missing = []
        if not self.vehicle_id:
            missing.append(self.env._("Vehicle"))
        if not self.operator_id:
            missing.append(self.env._("Driver"))
        if not self.odometer_departure:
            missing.append(self.env._("Odometer at departure"))
        if not self._get_exit_activities():
            missing.append(self.env._("Route activities"))
        return missing

    def _check_exit_vehicle_free(self) -> None:
        self.check_singleton()
        busy = self.search(
            [
                ("vehicle_id", "=", self.vehicle_id.id),
                ("date_return", "=", False),
                ("state", "!=", "cancel"),
                ("id", "!=", self.id),
                "|",
                ("date_departure", "!=", False),
                ("exit_requested_uid", "!=", False),
            ],
            limit=1,
        )
        if busy:
            raise UserError(
                self.env._(
                    "%(vehicle)s is already on %(trip)s: close it before it asks "
                    "to leave again.",
                    vehicle=self.vehicle_id.display_name,
                    trip=busy.name,
                )
            )

    def action_exit_request(self):
        self.check_singleton()
        if not self.is_fleet_exit or self.date_departure or self.state == "cancel":
            raise UserError(
                self.env._("%(trip)s is not a route waiting to leave.", trip=self.name)
            )
        if self._get_exit_authorisations():
            raise UserError(
                self.env._(
                    "%(trip)s is already waiting to be authorised.", trip=self.name
                )
            )
        missing = self._get_exit_request_missing()
        if missing:
            raise UserError(
                self.env._(
                    "Route %(trip)s cannot ask to leave, it is missing: %(fields)s.",
                    trip=self.name,
                    fields=", ".join(missing),
                )
            )
        self._check_exit_vehicle_free()
        authorisers = (
            self._get_exit_authorisers(self.company_id) - self.operator_id.user_id
        )
        if not authorisers:
            raise UserError(
                self.env._(
                    "Nobody can authorise %(trip)s: add the vehicle exit "
                    "authorisers in Settings, Users.",
                    trip=self.name,
                )
            )
        self.exit_requested_uid = self.env.user
        activities = self.env["mail.activity"]
        for user in authorisers:
            activities |= self.activity_schedule(
                AUTHORISE_TYPE,
                user_id=user.id,
                summary=self.env._("Authorise %(trip)s", trip=self.name),
            )
        self._notify_exit_requested(activities)
        return activities

    def _notify_exit_requested(self, activities) -> None:
        pass

    def _notify_exit_decided(self, authorised, others) -> None:
        pass

    def _take_exit_decision(self):
        self.check_singleton()
        asked = self._get_exit_authorisations()
        mine = asked.filtered(lambda activity: activity.user_id == self.env.user)
        if not mine:
            raise UserError(
                self.env._(
                    "%(trip)s is not waiting for your authorisation, or it was "
                    "already decided.",
                    trip=self.name,
                )
            )
        return mine, asked - mine

    def action_exit_authorise(self):
        self.check_singleton()
        mine, others = self._take_exit_decision()
        self.write({"supervisor_id": self.env.uid, "exit_authorised_uid": self.env.uid})
        self.action_depart()
        mine.action_feedback(feedback=self.env._("Authorised"))
        others_users = others.user_id
        others.unlink()
        self._notify_exit_decided(True, others_users)

    def action_exit_refuse(self, reason=None):
        self.check_singleton()
        mine, others = self._take_exit_decision()
        feedback = self.env._("Refused")
        mine.action_feedback(feedback=f"{feedback}: {reason}" if reason else feedback)
        others_users = others.user_id
        others.unlink()
        self._get_exit_activities(done=False).unlink()
        self.action_cancel()
        self._notify_exit_decided(False, others_users)

    def action_cancel(self):
        self.filtered("is_fleet_exit")._get_exit_authorisations().unlink()
        return super().action_cancel()

    def action_depart(self):
        self.check_singleton()
        if not self.is_fleet_exit:
            return super().action_depart()
        if not self.exit_authorised_uid:
            raise UserError(
                self.env._(
                    "Route %(trip)s leaves once a vehicle exit authoriser "
                    "authorises it: ask for the authorisation.",
                    trip=self.name,
                )
            )
        holder = self.vehicle_id.operator_employee_id
        res = super().action_depart()
        self.exit_holder_id = holder
        if holder != self.operator_id:
            self._exit_hand_vehicle(self.operator_id)
        return res

    def action_return(self):
        res = super().action_return()
        if self.is_fleet_exit:
            self._exit_after_close()
        return res

    def action_exit_close_here(self):
        self.check_singleton()
        if not self.exit_stay_location:
            raise UserError(
                self.env._(
                    "Say where %(vehicle)s stays before closing %(trip)s there.",
                    vehicle=self.vehicle_id.display_name,
                    trip=self.name,
                )
            )
        return self.action_return()

    def _exit_after_close(self) -> None:
        self.check_singleton()
        self._get_exit_activities(done=False).action_feedback(
            feedback=self.env._("Closed with the route")
        )
        self._exit_give_vehicle_back()
        if self.exit_stay_location:
            self.exit_kept_location = self.vehicle_id.resource_id.location
            self._exit_write_vehicle({"location": self.exit_stay_location})
            return
        away = self.search(
            [
                ("vehicle_id", "=", self.vehicle_id.id),
                ("exit_stay_location", "!=", False),
                ("id", "!=", self.id),
            ],
            order="date_return desc, id desc",
            limit=1,
        )
        if away and self.vehicle_id.resource_id.location == away.exit_stay_location:
            self._exit_write_vehicle({"location": away.exit_kept_location or False})

    def _exit_give_vehicle_back(self) -> None:
        self.check_singleton()
        if self.exit_holder_id == self.operator_id:
            return
        if self.vehicle_id.operator_employee_id != self.operator_id:
            self.message_post(
                body=self.env._(
                    "%(vehicle)s changed hands while it was out: it stays with "
                    "%(holder)s.",
                    vehicle=self.vehicle_id.display_name,
                    holder=self.vehicle_id.operator_employee_id.name or "—",
                ),
                message_type="notification",
            )
            return
        self._exit_hand_vehicle(self.exit_holder_id)

    def _exit_hand_vehicle(self, employee) -> None:
        self._exit_write_vehicle({"operator_employee_id": employee.id})

    def _exit_write_vehicle(self, vals) -> None:
        self.check_singleton()
        self.vehicle_id.resource_id.with_privilege(
            "stock_fleet_exit.privilege_exit_hand_over",
            reason="a route hands its vehicle over and back",
        ).with_context(**{CUSTODY_SILENT: True}).write(vals)
