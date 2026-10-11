from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Machine",
        compute="_compute_asset_id",
        inverse="_inverse_asset_id",
        search="_search_asset_id",
        compute_sudo=False,
        copy=False,
        readonly=False,
        value_sql="_asset_id_sql",
        help="The machine this work center's resource is. Its downtime, custody and bookings are the work center's.",
    )

    @api.depends("resource_id", "resource_id.kind_id")
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_asset_id(self):
        for workcenter in self:
            resource = workcenter.resource_id
            workcenter.asset_id = resource if resource.kind_id else False

    def _search_asset_id(self, operator, value):
        if operator not in ("in", "not in", "any", "not any"):
            return NotImplemented
        positive = "in" if operator in ("in", "not in") else "any"
        if positive == "in":
            ids = [v for v in value if v]
            domain = Domain("resource_id", "in", ids) & Domain(
                "resource_id.kind_id", "!=", False
            )
            if len(ids) < len(value):
                domain |= Domain("resource_id.kind_id", "=", False)
        else:
            domain = Domain("resource_id", "any", value) & Domain(
                "resource_id.kind_id", "!=", False
            )
        return ~domain if operator.startswith("not") else domain

    def _asset_id_sql(self, field, alias, query=None):
        return self.env["resource.resource"]._asset_projection_sql(
            self._field_to_sql(alias, "resource_id", query)
        )

    def _check_identity_input(self, vals):
        if not vals.get("asset_id") or not vals.get("resource_id"):
            return
        asset = self.env["resource.resource"].browse(vals["asset_id"])
        asset.check_access("read")
        if asset.id != vals["resource_id"]:
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
                asset = self.env["resource.resource"].browse(asset_id)
                asset.check_access("read")
                given_resource = vals.get(
                    "resource_id", self.env.context.get("default_resource_id")
                )
                if given_resource and given_resource != asset.id:
                    raise ValidationError(
                        self.env._(
                            "The work center machine and resource must share one identity."
                        )
                    )
                vals["resource_id"] = asset.id
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
            (left - self.resource_id).filtered(
                lambda resource: not resource.kind_id
            )._archive_if_unused()
        return result

    def _inverse_asset_id(self):
        for workcenter in self:
            asset = workcenter.asset_id
            if asset:
                asset.check_access("read")
                target = asset
            elif workcenter.resource_id.kind_id:
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
