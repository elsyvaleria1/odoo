from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        string="Machine",
        compute="_compute_asset_id",
        inverse="_inverse_asset_id",
        search="_search_asset_id",
        compute_sudo=False,
        copy=False,
        readonly=False,
        value_sql="_asset_id_sql",
        help="The asset represented by this work center's resource. The machine's downtime, custody and bookings are shared with the work center.",
    )

    @api.depends("resource_id", "resource_id.asset_id")
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_asset_id(self):
        for workcenter in self:
            workcenter.asset_id = workcenter.resource_id.asset_id

    def _search_asset_id(self, operator, value):
        return Domain("resource_id.asset_id", operator, value)

    def _asset_id_sql(self, field, alias, query=None):
        return self.env["resource.resource"]._asset_projection_sql(
            self._field_to_sql(alias, "resource_id", query)
        )

    def _check_identity_input(self, vals):
        if not vals.get("asset_id") or not vals.get("resource_id"):
            return
        asset = self.env["resource.asset"].browse(vals["asset_id"])
        asset.check_access("read")
        if asset.resource_id.id != vals["resource_id"]:
            raise ValidationError(
                self.env._(
                    "The work center machine and resource must share one identity."
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_identity_input(vals)
            asset_id = vals.pop("asset_id", self.env.context.get("default_asset_id"))
            if asset_id:
                asset = self.env["resource.asset"].browse(asset_id)
                asset.check_access("read")
                given_resource = vals.get(
                    "resource_id", self.env.context.get("default_resource_id")
                )
                if given_resource and given_resource != asset.resource_id.id:
                    raise ValidationError(
                        self.env._(
                            "The work center machine and resource must share one identity."
                        )
                    )
                vals["resource_id"] = asset.resource_id.id
                vals.pop("resource_calendar_id", None)
        context = dict(self.env.context)
        context.pop("default_asset_id", None)
        return super(MrpWorkcenter, self.with_context(context)).create(vals_list)

    def write(self, vals):
        self._check_identity_input(vals)
        left = (
            self.resource_id
            if vals.get("resource_id")
            else self.env["resource.resource"]
        )
        result = super().write(vals)
        if left:
            (left - self.resource_id)._archive_if_unused()
        return result

    def _inverse_asset_id(self):
        for workcenter in self:
            asset = workcenter.asset_id
            if asset:
                asset.check_access("read")
                target = asset.resource_id
            elif workcenter.resource_id.asset_id:
                target = workcenter._provision_resource()
            else:
                continue
            if workcenter.resource_id != target:
                workcenter.write({"resource_id": target.id})

    def _provision_resource(self):
        self.check_singleton()
        return self.env["resource.resource"].create(
            self._prepare_resource_values(
                {"name": self.name, "company_id": self.company_id.id}, self.tz
            )
        )
