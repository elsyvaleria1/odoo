import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Datetime
from odoo.tools.date_utils import get_timedelta

_logger = logging.getLogger(__name__)


class MaintenancePlan(models.Model):
    _inherit = "maintenance.plan"
    _order = "date_next_scheduled, id"

    name = fields.Char(
        compute="_compute_name",
        precompute=True,
        store=True,
        readonly=False,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        compute="_compute_product_id",
        store=True,
        readonly=False,
        tracking=True,
    )
    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        compute="_compute_asset_id",
        inverse="_inverse_asset_id",
        precompute=True,
        store=True,
        index="btree_not_null",
        domain="[('product_id.maintenance_ok', '=', True), ('product_id', '=', product_id)]",
        help="The one asset this plan maintains, which its odometer trigger and its template read.",
    )
    trace_id = fields.Many2one(
        related="asset_id.trace_id",
    )
    kind_id = fields.Many2one(
        related="asset_id.kind_id",
    )
    kind_code = fields.Char(related="asset_id.kind_code")
    template_id = fields.Many2one(
        comodel_name="maintenance.plan.template",
        index="btree_not_null",
        tracking=True,
    )
    distance_interval = fields.Float(
        help="Distance between preventive services, in the asset's own odometer "
        "unit -- read odometer_uom_name rather than assuming kilometres. "
        "0 disables the distance trigger (the plan runs on time only)."
    )
    last_maintenance_odometer = fields.Float(
        tracking=True,
        help="Odometer reading recorded at the last completed maintenance.",
    )
    next_maintenance_odometer = fields.Float(
        compute="_compute_next_maintenance_odometer",
        store=True,
        readonly=False,
        tracking=True,
        help="Odometer at which the next service is due. Auto-calculated as "
        "last maintenance odometer + distance interval, but can be manually "
        "adjusted.",
    )
    odometer_meter_id = fields.Many2one(
        comodel_name="resource.meter",
        compute="_compute_odometer_meter_id",
        store=True,
        index="btree_not_null",
    )
    current_odometer = fields.Float(
        compute="_compute_current_odometer",
        help="Odometer the asset has reached: its odometer meter, fed by the "
        "ledger and by telemetry.",
    )
    distance_remaining = fields.Float(
        compute="_compute_distance_remaining",
        help="Distance left before the next service is due.",
    )
    odometer_uom_name = fields.Char(
        related="asset_id.odometer_uom_name",
        string="Distance Unit",
    )
    maintenance_completed_count = fields.Integer(compute="_compute_maintenance_metrics")
    maintenance_cancelled_count = fields.Integer(compute="_compute_maintenance_metrics")
    maintenance_compliance_rate = fields.Float(
        compute="_compute_maintenance_metrics",
        help="Percentage of completed vs total scheduled maintenances",
    )
    conflicting_plan_ids = fields.Many2many(
        comodel_name="maintenance.plan",
        compute="_compute_conflicting_plans",
        help="Other maintenance plans scheduled for the same day that may cause resource bottlenecks",
    )
    has_date_conflict = fields.Boolean(compute="_compute_conflicting_plans")
    state = fields.Selection(
        selection=[
            ("upcoming", "Upcoming"),
            ("planned", "Planned"),
            ("today", "Today"),
            ("overdue", "Overdue"),
        ],
        compute="_compute_state",
        store=True,
    )

    _unique_active_plan = models.UniqueIndex(
        "(asset_id, repeat_interval, repeat_unit) WHERE active = TRUE",
        "Only one active plan per equipment with the same interval is allowed.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        defaults = self.default_get(["repeat_interval", "repeat_unit"])
        for vals in vals_list:
            if not vals.get("asset_id", self.env.context.get("default_asset_id")):
                continue
            for name, value in self._get_asset_plan_defaults().items():
                if name not in vals and f"default_{name}" not in self.env.context:
                    vals[name] = value
            if not vals.get("date_first_occurrence") and not self.env.context.get(
                "default_date_first_occurrence"
            ):
                vals["date_first_occurrence"] = now + get_timedelta(
                    vals.get("repeat_interval") or defaults.get("repeat_interval") or 1,
                    vals.get("repeat_unit") or defaults.get("repeat_unit") or "month",
                )
        return super().create(vals_list)

    @api.model
    def _get_asset_plan_defaults(self):
        return {
            "repeat_anchor": "completion",
            "block_resource": False,
            "duration": float(
                self.env.registry.settings.get(
                    self.env, "asset_ledger_maintenance.default_duration", "1.0"
                )
            ),
        }

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if self.env.context.get("default_asset_id"):
            for name, value in self._get_asset_plan_defaults().items():
                if name in fields and f"default_{name}" not in self.env.context:
                    defaults[name] = value
            if (
                "date_first_occurrence" in fields
                and "default_date_first_occurrence" not in self.env.context
            ):
                cadence = super().default_get(["repeat_interval", "repeat_unit"])
                defaults["date_first_occurrence"] = Datetime.now() + get_timedelta(
                    cadence.get("repeat_interval") or 1,
                    cadence.get("repeat_unit") or "month",
                )
        return defaults

    @api.depends("resource_ids")
    def _compute_asset_id(self) -> None:
        assets = self.env["resource.asset"].search(
            [("resource_id", "in", self.resource_ids._origin.ids)]
        )
        for plan in self:
            mine = assets.filtered(
                lambda asset, resources=plan.resource_ids._origin: (
                    asset.resource_id in resources
                )
            )
            plan.asset_id = mine if len(mine) == 1 else False

    def _inverse_asset_id(self) -> None:
        for plan in self:
            kept = plan.resource_ids.filtered(lambda resource: not resource.asset_id)
            plan.resource_ids = kept | plan.asset_id.resource_id

    @api.depends("asset_id", "repeat_interval", "repeat_unit")
    def _compute_name(self):
        units = dict(self._fields["repeat_unit"]._description_selection(self.env))
        for plan in self:
            if plan.asset_id and plan.repeat_interval and plan.repeat_unit:
                plan.name = self.env._(
                    "Maintenance Plan - %(asset)s - Every %(interval)s %(unit)s",
                    asset=plan.asset_id.name,
                    interval=plan.repeat_interval,
                    unit=units.get(plan.repeat_unit, ""),
                )
            elif plan.asset_id:
                plan.name = self.env._(
                    "Maintenance Plan - %(asset)s", asset=plan.asset_id.name
                )
            elif not plan.name:
                plan.name = self.env._("Maintenance Plan")

    @api.depends("asset_id")
    def _compute_product_id(self) -> None:
        for plan in self:
            if plan.asset_id:
                plan.product_id = plan.asset_id.product_id

    @api.onchange("template_id")
    def _onchange_template_id(self) -> None:
        if self.template_id and self.template_id.product_id:
            self.product_id = self.template_id.product_id

    @api.constrains("resource_ids", "distance_interval")
    def _check_distance_plan_has_one_asset(self) -> None:
        for plan in self:
            if plan.distance_interval > 0 and not plan.asset_id:
                raise ValidationError(
                    self.env._(
                        "Plan '%(plan)s' is triggered by distance, so it maintains exactly one asset, whose odometer it reads.",
                        plan=plan.name,
                    )
                )

    @api.constrains("asset_id")
    def _check_maintenance_ok(self) -> None:
        for plan in self:
            product = plan.asset_id.product_id
            if product and not product.maintenance_ok:
                raise ValidationError(
                    self.env._(
                        "Equipment '%(equipment)s' must have recurring maintenance enabled.",
                        equipment=plan.asset_id.name,
                    )
                )

    @api.depends("date_next_scheduled", "active")
    def _compute_conflicting_plans(self) -> None:
        dated = self.filtered(lambda plan: plan.date_next_scheduled and plan.active)
        (self - dated).update(
            {"conflicting_plan_ids": False, "has_date_conflict": False}
        )
        if not dated:
            return
        moments = dated.mapped("date_next_scheduled")
        candidates = self.search(
            [
                ("date_next_scheduled", ">=", min(moments) - timedelta(days=1)),
                ("date_next_scheduled", "<=", max(moments) + timedelta(days=1)),
            ]
        )
        by_day = {}
        for plan in candidates:
            day = plan._get_local_date(plan.date_next_scheduled)
            by_day[day] = by_day.get(day, self.browse()) | plan
        for plan in dated:
            day = plan._get_local_date(plan.date_next_scheduled)
            siblings = by_day.get(day, self.browse()) - plan
            plan.conflicting_plan_ids = siblings
            plan.has_date_conflict = bool(siblings)

    @api.depends(
        "date_next_scheduled",
        "order_ids.state",
        "order_ids.picking_ids.state",
        "distance_interval",
        "next_maintenance_odometer",
        "asset_id.odometer",
    )
    def _compute_state(self):
        now = fields.Datetime.now()
        for plan in self:
            order = plan._get_open_order() if plan.id else plan.order_ids.browse()
            if order and (order.state == "in_progress" or order.picking_ids):
                plan.state = "planned"
            elif plan.id and plan._is_odometer_due():
                plan.state = "overdue"
            elif not plan.date_next_scheduled:
                plan.state = "upcoming"
            else:
                day = plan._get_local_date(plan.date_next_scheduled)
                today = plan._get_local_date(now)
                plan.state = (
                    "overdue"
                    if day < today
                    else "today"
                    if day == today
                    else "upcoming"
                )

    @api.depends("order_ids.state")
    def _compute_maintenance_metrics(self) -> None:
        for plan in self:
            orders = plan.with_context(active_test=False).order_ids
            completed = len(orders.filtered(lambda order: order.state == "done"))
            cancelled = len(orders.filtered(lambda order: order.state == "cancel"))
            plan.maintenance_completed_count = completed
            plan.maintenance_cancelled_count = cancelled
            total = completed + cancelled
            plan.maintenance_compliance_rate = completed / total * 100 if total else 0.0

    @api.depends("asset_id.odometer_meter_id")
    def _compute_odometer_meter_id(self) -> None:
        for plan in self:
            plan.odometer_meter_id = plan.asset_id.odometer_meter_id

    @api.depends(
        "asset_id", "asset_id.odometer", "odometer_meter_id", "odometer_meter_id.value"
    )
    def _compute_current_odometer(self) -> None:
        for plan in self:
            meter = plan.odometer_meter_id
            plan.current_odometer = (
                meter.value if meter else plan.asset_id.odometer
            ) or 0.0

    @api.depends("next_maintenance_odometer", "current_odometer", "distance_interval")
    def _compute_distance_remaining(self) -> None:
        for plan in self:
            if plan.distance_interval > 0 and plan.current_odometer > 0:
                plan.distance_remaining = (
                    plan.next_maintenance_odometer - plan.current_odometer
                )
            else:
                plan.distance_remaining = 0

    @api.depends("last_maintenance_odometer", "distance_interval")
    def _compute_next_maintenance_odometer(self) -> None:
        for plan in self:
            if plan.distance_interval > 0:
                plan.next_maintenance_odometer = (
                    plan.last_maintenance_odometer + plan.distance_interval
                )
            else:
                plan.next_maintenance_odometer = 0

    def _is_odometer_due(self) -> bool:
        self.check_singleton()
        return (
            self.distance_interval > 0
            and self.current_odometer > 0
            and self.current_odometer >= self.next_maintenance_odometer
        )

    @api.model
    def _get_due_plans(self, moment):
        by_date = self.search([("date_next_scheduled", "<=", moment)])
        # A distance threshold cannot be expressed as a domain -- it compares
        # two fields on different models -- so those plans are filtered here.
        by_odometer = self.search([("distance_interval", ">", 0)]).filtered(
            lambda plan: plan._is_odometer_due()
        )
        return by_date | by_odometer

    def _prepare_order_vals(self, occurrence, previous=None):
        vals = super()._prepare_order_vals(occurrence, previous)
        if self.asset_id:
            vals["name"] = self.env._("Scheduled: %(plan)s", plan=self.name)
        return vals

    def _schedule_after(self, order):
        self.check_singleton()
        if (
            order.state == "done"
            and self.distance_interval > 0
            and self.current_odometer > 0
        ):
            self.last_maintenance_odometer = self.current_odometer
        return super()._schedule_after(order)

    @api.model
    def _cron_start_due_orders(self) -> None:
        now = fields.Datetime.now()
        started = failed = 0
        for plan in self._get_due_plans(now):
            order = plan._get_open_order()
            # An order already under way, or whose transfer a user cancelled, is
            # left to its users: the cron only sends out what nobody has touched.
            if not order or order.picking_ids or order.state != "confirmed":
                continue
            if order.date_scheduled_start and order.date_scheduled_start > now:
                order.date_scheduled_start = now
            route = order._resolve_warehouse_route()
            if not route:
                _logger.warning(
                    "Cron: plan %s is due but its asset sits in no warehouse set up for maintenance",
                    plan.id,
                )
                failed += 1
                continue
            try:
                with self.env.cr.savepoint():
                    order._create_transfer(*route)
                started += 1
            except Exception:
                _logger.exception("Cron: could not send plan %s's order out", plan.id)
                failed += 1
        _logger.info(
            "Cron: %d due maintenance orders sent out, %d could not be",
            started,
            failed,
        )

    @api.model
    def _cron_recompute_state(self) -> None:
        plans = self.search([])
        self.env.add_to_compute(self._fields["state"], plans)
        lots = (
            plans.trace_id
            | self.env["maintenance.order"]
            .search(
                [
                    *self.env["maintenance.order"]._get_domain_open(),
                    ("maintenance_type", "=", "preventive"),
                    ("asset_ids.trace_id", "!=", False),
                ]
            )
            .trace_ids
        )
        self.env.add_to_compute(lots._fields["maintenance_state"], lots)
        plans.flush_recordset(["state"])
        lots.flush_recordset(["maintenance_state"])
        lots.asset_id.invalidate_recordset(["maintenance_state"])

    def action_view_open_order(self) -> dict:
        self.check_singleton()
        order = self._get_open_order()
        if not order:
            raise UserError(
                self.env._(
                    "Plan '%(plan)s' has no open maintenance order.", plan=self.name
                )
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "maintenance.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }
