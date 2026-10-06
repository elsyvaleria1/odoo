from odoo import api, fields, models
from odoo.tools import SQL


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    asset_id = fields.One2one(
        comodel_name="resource.asset",
        inverse_name="resource_id",
        context={"active_test": False},
    )

    def _check_transition(self, state):
        super()._check_transition(state)
        self.asset_id._check_transition(state)

    def _check_reactivation(self):
        super()._check_reactivation()
        self.asset_id._check_reactivation()

    def _on_custody_changed(self, role, changes, planned=False):
        super()._on_custody_changed(role, changes, planned=planned)
        self.asset_id._on_custody_changed(role, changes, planned=planned)

    @api.model
    def _asset_projection_sql(self, resource_id):
        assets = self.env["resource.asset"].with_context(active_test=False)._search([])
        return SQL(
            "(SELECT asset.id FROM resource_asset asset WHERE asset.resource_id = %s AND asset.id IN %s)",
            resource_id,
            assets.subselect(),
        )
