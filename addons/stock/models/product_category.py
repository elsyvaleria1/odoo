from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductCategory(models.Model):
    _inherit = "product.category"

    removal_strategy_id = fields.Many2one(
        comodel_name="product.removal",
        string="Force Removal Strategy",
        tracking=True,
        help="Set a specific removal strategy that will be used regardless of the source location for this product category.\n\n"
        "FIFO: products/lots that were stocked first will be moved out first.\n"
        "LIFO: products/lots that were stocked last will be moved out first.\n"
        "Closest location: products/lots closest to the target location will be moved out first.\n"
        "FEFO: products/lots with the closest removal date will be moved out first "
        '(the availability of this method depends on the "Expiration Dates" setting).\n'
        "Least Packages: FIFO but with the least number of packages possible when there are several packages containing the same product.",
    )
    route_ids = fields.Many2many(
        comodel_name="stock.route",
        relation="stock_route_categ",
        column1="categ_id",
        column2="route_id",
        string="Routes",
        domain=[("product_categ_selectable", "=", True)],
    )
    parent_route_ids = fields.Many2many(
        comodel_name="stock.route",
        string="Parent Routes",
        compute="_compute_parent_route_ids",
    )
    total_route_ids = fields.Many2many(
        comodel_name="stock.route",
        string="Total routes",
        compute="_compute_total_route_ids",
        search="_search_total_route_ids",
        readonly=True,
    )
    packaging_reserve_method = fields.Selection(
        selection=[
            ("full", "Reserve Only Full Packagings"),
            ("partial", "Reserve Partial Packagings"),
        ],
        string="Reserve Packagings",
        default="partial",
        help="Reserve Only Full Packagings: will not reserve partial packagings. If customer orders 2 pallets of 1000 units each and you only have 1600 in stock, then only 1000 will be reserved\n"
        "Reserve Partial Packagings: allow reserving partial packagings. If customer orders 2 pallets of 1000 units each and you only have 1600 in stock, then 1600 will be reserved",
    )
    putaway_rule_ids = fields.One2many(
        comodel_name="stock.putaway.rule",
        inverse_name="category_id",
        string="Putaway Rules",
    )
    filter_for_stock_putaway_rule = fields.Boolean(
        string="stock.putaway.rule",
        search="_search_filter_for_stock_putaway_rule",
        store=False,
    )

    @_debug.perf.timed
    @api.depends("parent_id", "parent_id.total_route_ids", "route_ids")
    def _compute_parent_route_ids(self) -> None:
        for category in self:
            ancestor = category
            routes = self.env["stock.route"]
            while ancestor.parent_id:
                ancestor = ancestor.parent_id
                routes |= ancestor.route_ids
            category.parent_route_ids = routes - category.route_ids

    @api.depends("route_ids", "parent_route_ids")
    def _compute_total_route_ids(self) -> None:
        for category in self:
            category.total_route_ids = category.route_ids | category.parent_route_ids

    def _search_total_route_ids(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        wanted = {value} if isinstance(value, int) else set(value or ())
        if not all(isinstance(route_id, int) for route_id in wanted):
            return NotImplemented

        matched = []
        if wanted:
            categories = self.with_context(active_test=False)
            owners = categories.search([("route_ids", "in", list(wanted))])
            if owners:
                candidates = categories.search([("id", "child_of", owners.ids)])
                matched = [
                    category.id
                    for category in candidates
                    if wanted & set(category.total_route_ids.ids)
                ]
                _debug.perf.count(
                    "total_route_search",
                    operator=operator,
                    owners=len(owners),
                    candidates=len(candidates),
                    matched=len(matched),
                )
        return [("id", "in" if operator == "in" else "not in", matched)]

    def _search_filter_for_stock_putaway_rule(self, operator, value):
        if operator != "in":
            return NotImplemented

        domain = Domain.TRUE
        active_model = self.env.context.get("active_model")
        if active_model in (
            "product.template",
            "product.product",
        ) and self.env.context.get("active_id"):
            product = self.env[active_model].browse(self.env.context.get("active_id"))
            product = product.exists()
            if product:
                domain = Domain("id", "=", product.categ_id.id)
        return domain
