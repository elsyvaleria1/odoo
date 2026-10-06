from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_is_zero

_debug = DebugLog(__name__)


class MrpWorkcenter(models.Model):
    _name = "mrp.workcenter"
    _inherit = ["mixin.hr", "mrp.workcenter"]

    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="employees with access",
        store=True,
        readonly=False,
        help="if left empty, all employees can log in to the workcenter",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    employee_costs_hour = fields.Monetary(
        string="Employee Hourly Cost",
        currency_field="currency_id",
        default=0.0,
    )

    def action_work_order(self):
        self.check_singleton()
        if self.env.user.has_group(
            "mrp_workorder.group_mrp_wo_shop_floor"
        ) and not self.env.context.get("desktop_list_view", False):
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "mrp_workorder.action_mrp_display"
            )
            action["context"] = self.env["ir.actions.actions"]._eval_action_context(
                action.get("context", "{}")
            )
        else:
            action = super().action_work_order()
        _debug.logic(
            "work_order_action",
            workcenter=self.id,
            by="shop_floor"
            if self.env.user.has_group("mrp_workorder.group_mrp_wo_shop_floor")
            and not self.env.context.get("desktop_list_view", False)
            else "desktop_list",
        )
        action["context"] = dict(
            action["context"],
            workcenter_id=self.id,
            employee_id=self.env["hr.employee"].get_session_owner(),
            shouldHideNewWorkcenterButton=True,
        )
        return action

    @api.model
    def get_employee_barcode(self, barcode):
        domain = [
            ("barcode", "=", barcode),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", self.env.companies.ids),
        ]
        return self.env["hr.employee"].sudo().search(domain, limit=1).id

    def action_enable_routings(self) -> None:
        self.env["res.config.settings"].create([{"group_mrp_routings": True}]).execute()


class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        compute="_compute_employee",
        store=True,
        readonly=False,
        help="employee that record this working time",
    )
    employee_cost = fields.Monetary(
        string="employee_cost",
        compute="_compute_employee_cost",
        default=0,
        store=True,
    )
    total_cost = fields.Float(
        string="Cost",
        compute="_compute_total_cost",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    @api.depends("employee_id.hourly_cost", "workcenter_id.employee_costs_hour")
    def _compute_employee_cost(self) -> None:
        for time in self:
            if time.workorder_id.state == "done" and not float_is_zero(
                time.employee_cost, 2
            ):
                continue

            if time.employee_id and not float_is_zero(time.employee_id.hourly_cost, 2):
                time.employee_cost = time.employee_id.hourly_cost
                by = "employee_hourly_cost"  # debuglog
            else:
                time.employee_cost = time.workcenter_id.employee_costs_hour
                by = "workcenter_rate"  # debuglog
            _debug.logic(
                "employee_cost_resolved",
                productivity=time.id,
                by=by,
                cost=time.employee_cost,
            )

    @api.depends("duration", "employee_cost")
    def _compute_total_cost(self) -> None:
        for time in self:
            time.total_cost = time.employee_cost * time.duration / 60

    @api.depends("user_id")
    def _compute_employee(self) -> None:
        for time in self:
            if time.user_id and time.user_id.employee_id:
                time.employee_id = time.user_id.employee_id

    @api.model
    def _get_open_timer_groupby(self) -> list:
        return ["workorder_id", "employee_id"]
