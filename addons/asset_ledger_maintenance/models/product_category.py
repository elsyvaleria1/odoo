from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    maintenance_team_active = fields.Boolean(
        default=True,
        help="If unchecked, the maintenance team will be archived. "
        "This only affects maintenance team visibility, not the product category itself.",
    )
    is_maintenance_team = fields.Boolean(
        default=False,
        help="Enable this category as a maintenance team. "
        "Teams can manage maintenance orders and track performance metrics.",
    )
    maintenance_order_count = fields.Integer(
        string="Maintenance Orders",
        compute="_compute_maintenance_order_count",
        help="Number of maintenance orders assigned to this team",
    )
    maintenance_plan_count = fields.Integer(
        string="Maintenance Plans",
        compute="_compute_maintenance_plan_count",
        help="Number of active maintenance plans managed by this team",
    )
    color = fields.Integer(
        string="Color Index",
        help="Color for kanban card visualization",
    )

    def _compute_maintenance_order_count(self) -> None:
        teams = self.filtered("is_maintenance_team")
        (self - teams).maintenance_order_count = 0
        if not teams:
            return
        Order = self.env["maintenance.order"]
        orders = Order.search(
            [
                ("asset_ids.product_id.categ_id", "in", teams.ids),
                *Order._get_domain_open(),
            ]
        )
        for category in teams:
            category.maintenance_order_count = len(
                orders.filtered(
                    lambda order, category=category: (
                        category in order.asset_ids.product_id.categ_id
                    )
                )
            )

    def _compute_maintenance_plan_count(self) -> None:
        teams = self.filtered("is_maintenance_team")
        (self - teams).maintenance_plan_count = 0
        if not teams:
            return
        counts = dict(
            self.env["maintenance.plan"]._read_group(
                [("asset_id.product_id.categ_id", "in", teams.ids)],
                ["asset_id.product_id.categ_id"],
                ["__count"],
            )
        )
        for category in teams:
            category.maintenance_plan_count = counts.get(category, 0)

    def action_view_maintenance_orders(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "asset_ledger_maintenance.action_maintenance_order"
        )
        action["domain"] = [("asset_ids.product_id.categ_id", "=", self.id)]
        return action

    def action_view_maintenance_plans(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "asset_ledger_maintenance.action_maintenance_plan"
        )
        action["domain"] = [("asset_id.product_id.categ_id", "=", self.id)]
        return action
