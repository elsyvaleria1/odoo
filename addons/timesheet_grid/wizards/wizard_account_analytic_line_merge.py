from odoo import api, fields, models
from odoo.exceptions import ValidationError


class WizardAccountAnalyticLineMerge(models.TransientModel):
    _name = "wizard.account.analytic.line.merge"
    _description = "Merge Timesheets"

    name = fields.Char(
        string="Description",
        compute="_compute_name",
        store=True,
        readonly=False,
    )
    timesheet_ids = fields.Many2many(
        comodel_name="account.analytic.line",
        string="Timesheets",
        export_string_translation=False,
        domain="[('project_id', '!=', False), ('validated', '=', False)]",
    )

    date = fields.Date()
    unit_amount = fields.Float(
        string="Quantity",
        compute="_compute_unit_amount",
        store=True,
        readonly=False,
    )
    encoding_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        export_string_translation=False,
        readonly=True,
    )

    project_id = fields.Many2one(
        comodel_name="project.project",
        domain=[("is_template", "=", False)],
    )
    task_id = fields.Many2one(
        comodel_name="project.task",
        compute="_compute_task_id",
        store=True,
        readonly=False,
        domain="[('project_id.allow_timesheets', '=', True), ('project_id', '=?', project_id)]",
    )
    employee_id = fields.Many2one(comodel_name="hr.employee")

    @api.constrains("timesheet_ids")
    def _check_timesheet_ids(self) -> None:
        for wizard in self:
            if len(set(wizard.timesheet_ids.mapped("encoding_uom_id"))) > 1:
                raise ValidationError(
                    self.env._("The timesheets must have the same encoding unit")
                )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_ids = self.env.context.get("active_ids")

        if "timesheet_ids" in fields and active_ids:
            timesheets = self.env["account.analytic.line"].browse(active_ids)
            timesheets = timesheets.filtered(
                lambda l: l.project_id and not l.validated and not l.is_timer_running
            )
            if timesheets:
                res["timesheet_ids"] = timesheets.ids

                if "date" in fields:
                    res["date"] = timesheets[0].date

                for f in ["encoding_uom_id", "project_id", "task_id", "employee_id"]:
                    if f in fields:
                        res[f] = timesheets[0][f].id

        return res

    @api.depends("project_id")
    def _compute_task_id(self) -> None:
        for entry in self:
            if entry.project_id != entry.task_id.project_id:
                entry.task_id = False

    @api.depends("timesheet_ids")
    def _compute_name(self):
        for entry in self:
            all_names = set(entry.timesheet_ids.mapped("name"))
            entry.name = " / ".join(
                [name for name in sorted(all_names) if name and name != "/"]
            )

    @api.depends("timesheet_ids")
    def _compute_unit_amount(self) -> None:
        for entry in self:
            entry.unit_amount = sum(entry.timesheet_ids.mapped("unit_amount"))

    def action_merge(self):
        self.check_singleton()

        self.env["account.analytic.line"].create(
            self._prepare_merged_timesheet_values()
        )
        self.timesheet_ids.unlink()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": self.env._("The timesheets have successfully been merged."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _prepare_merged_timesheet_values(self):
        return {
            "name": self.name,
            "date": self.date,
            "unit_amount": self.unit_amount,
            "encoding_uom_id": self.encoding_uom_id.id,
            "project_id": self.project_id.id,
            "task_id": self.task_id.id,
            "employee_id": self.employee_id.id,
        }
