import logging

from odoo import api, fields, models

from odoo.addons.base.fields import ResourceIdentifier
from odoo.addons.base.models.resource_utils import SKIP_IDENTITY_CHECK

_logger = logging.getLogger(__name__)

ASSET_ATTRIBUTE_FIELDS = frozenset(
    {
        "name",
        "product_id",
        "company_id",
        "date_acquisition",
        "date_write_off",
        "model_year",
        "brand_new",
    }
)
LOG_CATEGORY_SEEDS = {
    "fuel": "asset_ledger.product_category_fuel",
    "highway": "asset_ledger.product_category_highway_toll",
    "service": "asset_ledger.product_category_maintenance_and_repairs",
    "operator": "asset_ledger.product_category_operator_assignment",
}


def _bool_search_inclusion_operator(operator, value) -> str:
    if operator == "in":
        return "in" if (True in value or 1 in value) else "not in"
    if operator == "not in":
        return "not in" if (True in value or 1 in value) else "in"
    truthy = bool(value)
    if (operator == "=" and truthy) or (operator in ("<>", "!=") and not truthy):
        return "in"
    return "not in"


class ProductTrace(models.Model):
    _inherit = "product.trace"

    kind_code = fields.Char(related="asset_id.kind_code")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
    )
    location = fields.Char(
        related="asset_id.location",
        readonly=False,
    )
    model_year = fields.Integer(help="The commercial model year.")
    brand_new = fields.Boolean(
        default=True,
        help="Mark as True if this asset was acquired as brand new.",
    )

    license_plate = ResourceIdentifier(identifier_code="plate", through="asset_id")
    vin_sn = ResourceIdentifier(
        identifier_code="vin",
        through="asset_id",
        string="Serial Number / VIN",
    )
    cadastral_id = ResourceIdentifier(
        identifier_code="cadastral",
        through="asset_id",
        string="Cadastral ID",
    )
    engine_sn = ResourceIdentifier(
        identifier_code="engine",
        through="asset_id",
        string="Engine Serial Number",
    )
    imei = ResourceIdentifier(identifier_code="imei", through="asset_id", string="IMEI")

    date_acquisition = fields.Date(
        copy=False,
        tracking=True,
        help="Date of asset's registration",
    )
    date_write_off = fields.Date(
        copy=False,
        tracking=True,
        help="Date when the asset's license plate has been cancelled/removed.",
    )
    value_original = fields.Monetary(
        related="asset_id.value_original",
        readonly=False,
    )
    value_residual = fields.Monetary(
        related="asset_id.value_residual",
        readonly=False,
    )
    account_prefix = fields.Char(
        related="asset_id.account_prefix",
        readonly=False,
    )

    area = fields.Integer(
        related="asset_id.area",
        readonly=False,
    )

    log_ids = fields.One2many(
        comodel_name="resource.log",
        inverse_name="trace_id",
    )
    odometer_uom_id = fields.Many2one(
        related="asset_id.odometer_uom_id",
        readonly=False,
    )
    odometer_uom_name = fields.Char(
        related="odometer_uom_id.display_name",
        string="Odometer Unit",
    )

    @api.model_create_multi
    def create(self, vals_list):
        skip = self.env.context.get(SKIP_IDENTITY_CHECK)
        lots = super(
            ProductTrace, self.with_context(**{SKIP_IDENTITY_CHECK: True})
        ).create(vals_list)
        lots = lots.with_env(self.env)
        lots.filtered("asset_id")._sync_resource_asset()
        ledger_map = self._asset_ledger_field_map()
        by_given = {}
        for lot, vals in zip(lots, vals_list, strict=True):
            given = {ledger_map[k]: vals[k] for k in ledger_map if k in vals}
            asset = lot.asset_id.sudo()
            if not asset:
                continue
            if given:
                key = tuple(sorted(given.items(), key=lambda item: item[0]))
                by_given.setdefault(key, asset.browse())
                by_given[key] |= asset
            elif not skip:
                asset._check_required_identifiers()
        for key, assets in by_given.items():
            assets.write(dict(key))
        identity = self._get_identifier_field_names()
        for lot, vals in zip(lots, vals_list, strict=True):
            given = {name: vals[name] for name in identity if vals.get(name)}
            if given and lot.asset_id:
                lot.write(given)
        return lots

    @api.model
    def _get_identifier_field_names(self):
        return tuple(
            name
            for name, field in self._fields.items()
            if isinstance(field, ResourceIdentifier)
        )

    def write(self, vals):
        ledger_map = self._asset_ledger_field_map()
        ledger = {ledger_map[k]: vals[k] for k in ledger_map if k in vals}
        if ledger:
            vals = {k: v for k, v in vals.items() if k not in ledger_map}
            self.asset_id.sudo().write(ledger)
        res = super().write(vals) if vals else True
        touched = vals.keys()
        if "asset_id" in touched:
            self.filtered("asset_id")._sync_resource_asset()
        if touched & ASSET_ATTRIBUTE_FIELDS:
            self.filtered("asset_id")._sync_resource_asset_attributes()
        return res

    def _prepare_asset_vals(self):
        vals = super()._prepare_asset_vals()
        vals.update(
            {
                "date_acquisition": self.date_acquisition,
                "date_disposal": self.date_write_off,
                "model_year": self.model_year,
                "brand_new": self.brand_new,
            }
        )
        return vals

    def _sync_resource_asset_attributes(self) -> None:
        for lot in self.filtered("asset_id"):
            vals = lot._prepare_asset_vals()
            vals.pop("trace_id", None)
            if not vals.get("kind_id"):
                vals.pop("kind_id", None)
            asset = lot.asset_id.sudo()
            changed = {
                name: value
                for name, value in vals.items()
                if asset._fields[name].convert_to_write(asset[name], asset) != value
            }
            if "kind_id" in changed:
                asset = asset._retype(
                    self.env["resource.kind"].browse(changed.pop("kind_id"))
                )
            if changed:
                asset.write(changed)

    def _sync_resource_asset(self) -> None:
        for lot in self.filtered("asset_id"):
            lot._sync_resource_asset_meter(None)

    def _sync_resource_asset_meter(self, meter_model) -> None:
        self.check_singleton()
        self.asset_id.sudo()._sync_odometer_meter()

    @api.depends("asset_id.display_name", "kind_code")
    def _compute_display_name(self) -> None:
        vehicles = self.filtered(
            lambda lot: lot.kind_code == "vehicle" and lot.asset_id
        )
        for lot in vehicles:
            lot.display_name = lot.asset_id.display_name
        super(ProductTrace, self - vehicles)._compute_display_name()

    @api.depends("company_id")
    def _compute_currency_id(self) -> None:
        fallback = self.env.company.currency_id
        for lot in self:
            lot.currency_id = lot.company_id.currency_id or fallback

    def _get_log_model(self):
        return self.env["resource.log"].with_context(active_test=True)

    _bool_search_inclusion_operator = staticmethod(_bool_search_inclusion_operator)

    ASSET_LEDGER_FIELDS = (
        "account_prefix",
        "area",
        "value_original",
        "value_residual",
        "odometer_uom_id",
        "location",
    )

    @api.model
    def _asset_ledger_field_names(self):
        return tuple(self._asset_ledger_field_map())

    @api.model
    def _asset_ledger_field_map(self):
        return {name: name for name in self.ASSET_LEDGER_FIELDS}

    @api.model
    def _cron_refresh_service_activity(self):
        return self.env["resource.resource"]._cron_refresh_service_activity()

    def _action_view_logs(self, domain, default_log_type=None):
        self.check_singleton()
        return self.asset_id._action_view_logs(domain, default_log_type)

    def action_view_logs_service(self):
        self.check_singleton()
        return self.asset_id.action_view_logs_service()

    def action_view_logs_all(self):
        self.check_singleton()
        return self.asset_id.action_view_logs_all()

    def action_view_logs_fuel(self):
        self.check_singleton()
        return self.asset_id.action_view_logs_fuel()

    def action_register_fuel(self):
        self.check_singleton()
        return self.asset_id.action_register_fuel()
