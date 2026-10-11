from odoo import fields, models


class MixinMaintenanceTarget(models.AbstractModel):

    _name = "mixin.maintenance.target"
    _description = "Maintained Resource"

    resource_id = fields.Many2one(comodel_name="resource.resource")
    maintenance_profile_id = fields.One2one(
        related="resource_id.maintenance_profile_id"
    )
    maintenance_team_id = fields.Many2one(
        related="resource_id.maintenance_team_id",
        readonly=False,
    )
    technician_user_id = fields.Many2one(
        related="resource_id.technician_user_id",
        readonly=False,
    )
    date_in_service = fields.Date(
        related="resource_id.date_in_service",
        readonly=False,
    )
    expected_mtbf = fields.Integer(
        related="resource_id.expected_mtbf",
        readonly=False,
    )
    mtbf = fields.Integer(related="resource_id.mtbf")
    mttr = fields.Integer(related="resource_id.mttr")
    date_next_failure = fields.Date(related="resource_id.date_next_failure")
    date_last_failure = fields.Date(related="resource_id.date_last_failure")
    maintenance_ids = fields.Many2many(related="resource_id.maintenance_ids")
    maintenance_count = fields.Integer(related="resource_id.maintenance_count")
    maintenance_open_count = fields.Integer(
        related="resource_id.maintenance_open_count"
    )
    maintenance_plan_ids = fields.Many2many(related="resource_id.maintenance_plan_ids")
    maintenance_plan_count = fields.Integer(
        related="resource_id.maintenance_plan_count"
    )

    def action_view_maintenance(self):
        self.check_singleton()
        return self.resource_id.action_view_maintenance()

    def action_view_maintenance_plans(self):
        self.check_singleton()
        return self.resource_id.action_view_maintenance_plans()
