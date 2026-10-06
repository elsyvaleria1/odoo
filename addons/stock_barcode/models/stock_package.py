from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPackage(models.Model):
    _inherit = "stock.package"
    _search_visibility_fields = ()
    _barcode_field = "name"

    @api.model
    def _search(self, domain, *args, **kwargs):
        domain = self.env.company.sudo().barcodes_config_id.nomenclature_id._preprocess_gs1_search_args(
            domain, ["package"], "name"
        )
        return super()._search(domain, *args, **kwargs)

    @api.model
    def action_create_from_barcode(self, vals) -> dict:
        """Creates a new package then returns its data to be added in the client side cache."""
        _debug.lifecycle("barcode_package_create", packages=self)
        res = self.create(vals)
        return {"stock.package": res.read(self._get_fields_stock_barcode(), load=False)}

    @api.model
    def _get_fields_stock_barcode(self):
        return [
            "name",
            "complete_name",
            "dest_complete_name",
            "location_id",
            "location_dest_id",
            "package_dest_id",
            "parent_package_id",
            "outermost_package_id",
            "package_type_id",
            "contained_quant_ids",
        ]

    # How many reusable/unlocated packages a barcode payload may carry. They are prefetched so
    # that scanning one resolves without a round trip, but they are unrelated to the operation
    # being opened, so an unbounded set is pure payload: a 5-line picking was shipping every
    # package in the database. Overridable with the `stock_barcode.usable_packages_limit`
    # config parameter.
    USABLE_PACKAGES_LIMIT = 200

    @api.model
    def _get_usable_packages(self):
        _debug.logic("barcode_usable_packages", packages=self)
        usable_packages_domain = [
            "|",
            ("package_type_id.package_use", "=", "reusable"),
            ("location_id", "=", False),
        ]
        records_limit = self.env.registry.settings.get_int(
            self.env, "stock_barcode.usable_packages_limit", self.USABLE_PACKAGES_LIMIT
        )
        packages = self.env["stock.package"].search(
            usable_packages_domain, limit=records_limit, order="create_date desc"
        )
        loc_ids = self.env.context.get("pack_locs")
        if loc_ids:
            # Bounded like the reusable ones: an unbounded set shipped every package stored
            # under the destination. A package left out is fetched by barcode when scanned.
            packages |= self.env["stock.package"].search(
                [("location_id", "in", loc_ids)],
                limit=records_limit,
                order="create_date desc",
            )
        return packages
