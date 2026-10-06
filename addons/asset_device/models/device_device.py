from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

ASSET_IDENTITY = {
    "imei": "imei",
    "serial_number": "serial",
    "plate": "plate",
}


class DeviceDevice(models.Model):
    _inherit = "device.device"

    own_asset_id = fields.Many2one(
        comodel_name="resource.asset",
        string="Device Asset Record",
        compute="_compute_own_asset_id",
        inverse="_inverse_own_asset_id",
        search="_search_own_asset_id",
        compute_sudo=False,
        copy=False,
        readonly=False,
        value_sql="_own_asset_id_sql",
        help="The asset represented by this endpoint's resource. Several endpoints can represent one physical asset. Distinct from the resource a sensor observes.",
    )

    @api.depends("resource_id", "resource_id.asset_id")
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_own_asset_id(self):
        for device in self:
            device.own_asset_id = device.resource_id.asset_id

    def _search_own_asset_id(self, operator, value):
        return Domain("resource_id.asset_id", operator, value)

    def _own_asset_id_sql(self, field, alias, query=None):
        return self.env["resource.resource"]._asset_projection_sql(
            self._field_to_sql(alias, "resource_id", query)
        )

    def _inverse_own_asset_id(self):
        for device in self:
            asset = device.own_asset_id
            if asset:
                asset.check_access("read")
                device.resource_id = asset.resource_id
            elif device.resource_id.asset_id:
                device.resource_id = False

    def _check_identity_input(self, vals):
        if "own_asset_id" not in vals or not vals.get("resource_id"):
            return
        resource = self.env["resource.resource"].browse(vals["resource_id"])
        resource.check_access("read")
        if resource.asset_id.id != (vals["own_asset_id"] or False):
            raise ValidationError(
                self.env._(
                    "The device asset and represented resource must share one identity."
                )
            )

    def write(self, vals):
        self._check_identity_input(vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_identity_input(vals)
            asset_id = vals.pop(
                "own_asset_id", self.env.context.get("default_own_asset_id")
            )
            if asset_id:
                asset = self.env["resource.asset"].browse(asset_id)
                asset.check_access("read")
                resource_id = asset.resource_id.id
                given_resource = vals.get(
                    "resource_id", self.env.context.get("default_resource_id")
                )
                if given_resource and given_resource != resource_id:
                    raise ValidationError(
                        self.env._(
                            "The device asset and represented resource must share one identity."
                        )
                    )
                vals["resource_id"] = resource_id
        context = dict(self.env.context)
        context.pop("default_own_asset_id", None)
        return super(DeviceDevice, self.with_context(context)).create(vals_list)

    own_asset_kind_code = fields.Char(
        related="own_asset_id.kind_code",
        string="Asset Kind",
    )

    imei = fields.Char(
        compute="_compute_imei",
        store=True,
        readonly=False,
    )
    serial_number = fields.Char(
        compute="_compute_serial_number",
        store=True,
        readonly=False,
    )
    plate = fields.Char(
        compute="_compute_plate",
        store=True,
        readonly=False,
    )

    def _asset_identity(self, code):
        self.check_singleton()
        return (
            self.own_asset_id.resource_id._get_identifier(code)
            if self.own_asset_id
            else False
        )

    @api.depends("own_asset_id", "own_asset_id.identifier_ids.value")
    def _compute_imei(self) -> None:
        for device in self:
            device.imei = device._asset_identity("imei") or device.imei

    @api.depends("own_asset_id", "own_asset_id.identifier_ids.value")
    def _compute_serial_number(self) -> None:
        for device in self:
            device.serial_number = (
                device._asset_identity("serial") or device.serial_number
            )

    @api.depends("own_asset_id", "own_asset_id.identifier_ids.value")
    def _compute_plate(self) -> None:
        for device in self:
            device.plate = device._asset_identity("plate") or device.plate

    @api.constrains("own_asset_id", *ASSET_IDENTITY)
    def _check_identity_matches_asset(self) -> None:
        for device in self.filtered("own_asset_id"):
            for device_field, code in ASSET_IDENTITY.items():
                asset_value = device._asset_identity(code)
                if asset_value and device[device_field] != asset_value:
                    _debug.logic(
                        "identity.refused",
                        reason="differs_from_asset",
                        device=device,
                        field=device_field,
                    )
                    raise ValidationError(
                        self.env._(
                            "%(device)s says its %(label)s is %(device_value)s but "
                            "asset %(asset)s says %(asset_value)s. One device, one "
                            "identity -- correct it on the asset.",
                            device=device.display_name,
                            label=device._fields[device_field].get_description(
                                self.env
                            )["string"],
                            device_value=device[device_field] or "-",
                            asset=device.own_asset_id.display_name,
                            asset_value=asset_value,
                        )
                    )

    def action_view_own_asset(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "resource_asset.action_resource_asset"
        )
        action["res_id"] = self.own_asset_id.id
        action["view_mode"] = "form"
        action["views"] = [(False, "form")]
        return action
