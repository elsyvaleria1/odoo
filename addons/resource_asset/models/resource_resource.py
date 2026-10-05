from odoo import api, fields, models
from odoo.tools import SQL
from odoo.tools.translate import html_translate


class ResourceResource(models.Model):
    _inherit = "resource.resource"
    # a thing's vendor is one of its company's
    _check_company_auto = True

    asset_id = fields.One2one(
        comodel_name="resource.asset",
        inverse_name="resource_id",
        context={"active_test": False},
    )
    # what a thing is and where it came from, on the resource it is
    description = fields.Html(translate=html_translate)
    model = fields.Char(string="Model Name")
    model_year = fields.Integer(
        help="The commercial model year, which may differ from the year it was built.",
    )
    brand_new = fields.Boolean(default=True)
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        check_company=True,
        tracking=True,
    )
    vendor_ref = fields.Char(string="Vendor Reference")
    warranty_date = fields.Date(string="Warranty Expiration Date")
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Location",
        help="Where the resource normally is, when no inventory location tracks it.",
    )

    def _track_prepare(self, fields_iter):
        # an asset's history is its chatter's; a person's or an intangible's
        # resource keeps none
        return super(ResourceResource, self.filtered("asset_id"))._track_prepare(
            fields_iter
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
