import logging

from odoo import api, fields, models

from .product_trace import LOG_CATEGORY_SEEDS, _bool_search_inclusion_operator

_logger = logging.getLogger(__name__)


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    location = fields.Char(
        string="Asset Location",
        help="Where the thing is kept (garage, ...)",
    )
    asset_tag_ids = fields.Many2many(
        comodel_name="resource.tag",
        relation="resource_asset_tag_rel",
        column1="asset_id",
        column2="tag_id",
        string="Asset Tags",
    )
    value_residual = fields.Monetary(copy=False)
    account_prefix = fields.Char(
        tracking=True,
        help="This fields is required by Accounting to group according to its needs.",
    )
    area = fields.Integer(
        help="Surface area of the asset. The unit follows the system setting, so "
        "read area_uom_name rather than assuming square metres."
    )
    area_uom_name = fields.Char(
        string="Area Unit",
        compute="_compute_area_uom_name",
    )

    service_activity = fields.Selection(
        selection=[
            ("none", "None"),
            ("overdue", "Overdue"),
            ("today", "Today"),
        ],
        compute="_compute_service_activity",
        store=True,
    )
    count_logs_assignment = fields.Integer(
        compute="_compute_count_logs_all",
        compute_sudo=True,
        help="Operator assignment logs on this asset, counted in every state.",
    )
    count_logs_service = fields.Integer(
        compute="_compute_count_logs_all",
        compute_sudo=True,
        help="Service logs on this asset, counted in every state.",
    )
    count_logs_fuel = fields.Integer(
        compute="_compute_count_logs_all",
        compute_sudo=True,
        help="Fuel consumption logs on this asset (by category), counted in every state.",
    )
    count_logs_all = fields.Integer(
        compute="_compute_count_logs_all",
        compute_sudo=True,
        help="Every log on this asset, counted in every state.",
    )

    _bool_search_inclusion_operator = staticmethod(_bool_search_inclusion_operator)

    def _compute_area_uom_name(self) -> None:
        self.area_uom_name = (
            self.env["product.template"]._get_uom_from_setting("area").display_name
        )

    @api.model
    def _get_seed_log_category(self, log_type):
        return self.env.ref(LOG_CATEGORY_SEEDS[log_type], raise_if_not_found=False)

    @api.depends("log_ids", "log_ids.log_type", "log_ids.state", "log_ids.active")
    def _compute_count_logs_all(self) -> None:
        by_type = self._get_log_counts_by_type()
        for asset in self:
            counts = by_type[asset.id]
            asset.count_logs_all = sum(counts.values())
            asset.count_logs_fuel = counts["fuel"]
            asset.count_logs_assignment = counts["operator"]
            asset.count_logs_service = counts["service"]

    @api.depends("log_ids", "log_ids.active", "log_ids.activity_state")
    def _compute_service_activity(self) -> None:
        for asset in self:
            asset.service_activity = self._most_urgent_activity_state(
                asset.log_ids.mapped("activity_state"),
                among=("overdue", "today"),
                fallback="none",
            )

    @api.model
    def _cron_refresh_service_activity(self):
        assets = self.search(
            [
                "|",
                ("log_ids.activity_ids", "!=", False),
                ("service_activity", "in", ("overdue", "today")),
            ]
        )
        if not assets:
            return
        self.env.add_to_compute(assets._fields["service_activity"], assets)
        assets.flush_recordset(["service_activity"])
        _logger.info(
            "Refreshed service_activity on %d asset(s) against today.",
            len(assets),
        )

    def _get_log_action_xml_id(self) -> str:
        return "asset_ledger.action_product_asset_log"

    def _get_log_type_context(self, log_type):
        seed = self._get_seed_log_category(log_type)
        return {"default_product_category_id": seed.id} if seed else {}

    def action_view_logs_service(self):
        return self._action_view_logs(
            [("log_type", "=", "service")],
            self._get_log_type_context("service"),
        )

    def action_view_logs_all(self):
        return self._action_view_logs()

    def action_view_logs_fuel(self):
        return self._action_view_logs(
            [("log_type", "=", "fuel")],
            self._get_log_type_context("fuel"),
        )

    def action_register_fuel(self):
        self.check_singleton()
        fuel_product = self.env.ref(
            "asset_ledger.product_product_fuel_debit",
            raise_if_not_found=False,
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Register Fuel"),
            "res_model": "resource.log",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_asset_id": self.id,
                "default_product_id": fuel_product.id if fuel_product else False,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        things = [
            vals
            for vals in vals_list
            if (vals.get("kind_id") or vals.get("product_id"))
            and "odometer_uom_id" not in vals
        ]
        if things:
            uom = self.env["product.template"]._get_uom_from_setting("odometer")
            for vals in things:
                vals["odometer_uom_id"] = uom.id
        return super().create(vals_list)
