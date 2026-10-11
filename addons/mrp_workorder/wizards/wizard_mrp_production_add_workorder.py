from odoo import Command, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMrpProductionAddWorkorder(models.TransientModel):
    _name = "wizard.mrp.production.add.workorder"
    _description = "Additional Workorder"

    production_id = fields.Many2one(
        comodel_name="mrp.production",
        default=lambda self: self.env.context.get("active_id", None),
        required=True,
    )
    name = fields.Char(
        string="Title",
        required=True,
    )
    blocked_by_workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Insert after operation",
        copy=False,
        domain="[('production_id', '=', production_id)]",
    )
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Work Center",
        required=True,
    )
    duration_expected = fields.Float(string="Expected Duration")
    date_start = fields.Datetime()
    company_id = fields.Many2one(related="production_id.company_id")
    employee_assigned_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="mrp_workorder_additional_employee_assigned",
        column1="additional_workorder_id",
        column2="employee_id",
        string="Employee",
    )

    def add_workorder(self) -> None:
        if self.production_id.state in ("done", "cancel"):
            _debug.logic(
                "add_workorder_refused",
                reason="production_closed",
                production=self.production_id.id,
            )
            raise UserError(
                self.env._(
                    "You cannot add a work order to a closed manufacturing order."
                )
            )
        by = "default"
        if self.blocked_by_workorder_id:
            by = "after_selected"
            new_wo_sequence = self.blocked_by_workorder_id.sequence
        elif self.production_id.workorder_ids:
            by = "before_first"
            new_wo_sequence = self.production_id.workorder_ids[0].sequence - 1
        else:
            new_wo_sequence = 100
        _debug.logic(
            "add_workorder_placed",
            production=self.production_id.id,
            by=by,
            sequence=new_wo_sequence,
        )
        wo = self.env["mrp.workorder"].create(
            {
                "production_id": self.production_id.id,
                "name": self.name,
                "sequence": new_wo_sequence,
                "workcenter_id": self.workcenter_id.id,
                "duration_expected": self.duration_expected,
                "date_start": self.date_start or self.blocked_by_workorder_id.date_end,
                "employee_assigned_ids": self.employee_assigned_ids.ids,
                "product_uom_id": self.production_id.product_uom_id.id,
                "blocked_by_workorder_ids": [self.blocked_by_workorder_id.id]
                if self.blocked_by_workorder_id
                else False,
            }
        )
        _debug.lifecycle(
            "workorder_added", workorder=wo.id, production=self.production_id.id
        )
        if wo.date_start:
            wo.date_end = wo._get_date_end()
        if self.blocked_by_workorder_id:
            for next_wo in self.blocked_by_workorder_id.needed_by_workorder_ids:
                if next_wo.id != wo.id:
                    next_wo.blocked_by_workorder_ids = [Command.link(wo.id)]
        elif self.production_id.workorder_ids - wo:
            self.production_id.workorder_ids.sorted()[1].blocked_by_workorder_ids = [
                Command.link(wo.id)
            ]
