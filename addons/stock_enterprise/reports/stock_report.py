from odoo import api, fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class StockReport(models.Model):
    _name = "stock.report"
    _description = "Stock Report"
    _rec_name = "id"
    _auto = False
    _depends = frozendict(
        {
            "product.product": ["product_tmpl_id"],
            "product.template": ["categ_id", "is_storable"],
            "stock.move": [
                "company_id",
                "picking_id",
                "picking_type_id",
                "product_id",
                "product_qty",
                "reference",
                "state",
            ],
            "stock.picking": [
                "backorder_id",
                "create_date",
                "date_done",
                "date_planned",
                "name",
                "partner_id",
            ],
            "stock.picking.type": ["code"],
        }
    )
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    date_done = fields.Datetime(
        string="Transfer Date",
        readonly=True,
    )
    creation_date = fields.Datetime(readonly=True)
    date_planned = fields.Datetime(
        string="Expected Date",
        readonly=True,
    )
    delay = fields.Float(
        string="Delay (Days)",
        readonly=True,
        aggregator="avg",
    )
    cycle_time = fields.Float(
        string="Cycle Time (Days)",
        readonly=True,
        aggregator="avg",
    )
    picking_type_code = fields.Selection(
        selection=[
            ("incoming", "Vendors"),
            ("outgoing", "Customers"),
            ("internal", "Internal"),
        ],
        string="Type",
        readonly=True,
    )
    operation_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
    )
    picking_name = fields.Char(readonly=True)
    reference = fields.Char(readonly=True)
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Transfer Reference",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "New"),
            ("cancel", "Cancelled"),
            ("waiting", "Waiting Another Move"),
            ("confirmed", "Waiting Availability"),
            ("partially_available", "Partially Available"),
            ("assigned", "Available"),
            ("done", "Done"),
        ],
        string="Status",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
    )
    is_backorder = fields.Boolean(
        string="Is a Backorder",
        readonly=True,
    )
    product_qty = fields.Float(
        string="Product Quantity",
        readonly=True,
    )
    is_late = fields.Boolean(readonly=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    categ_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
        readonly=True,
    )

    @api.depends("reference", "product_id.name")
    def _compute_display_name(self):
        for report in self:
            report.display_name = (
                f"{report.reference} - {report.product_id.display_name}"
            )

    def _select(self):
        return """
            sm.id as id,
            sp.name as picking_name,
            sp.date_done as date_done,
            sp.creation_date as creation_date,
            sp.date_planned as date_planned,
            sp.partner_id as partner_id,
            sp.is_backorder as is_backorder,
            sp.delay as delay,
            sp.delay > 0 as is_late,
            sp.cycle_time as cycle_time,
            spt.code as picking_type_code,
            spt.id as operation_type_id,
            p.id as product_id,
            sm.reference as reference,
            sm.picking_id as picking_id,
            sm.state as state,
            sm.product_qty as product_qty,
            sm.company_id as company_id,
            cat.id as categ_id
        """

    def _from(self):
        return """
            stock_move sm
            LEFT JOIN (
                SELECT
                    id,
                    name,
                    date_done,
                    create_date as creation_date,
                    date_planned,
                    partner_id,
                    backorder_id IS NOT NULL as is_backorder,
                    (extract(epoch from avg(date_done-date_planned))/(24*60*60))::decimal(16,2) as delay,
                    (extract(epoch from avg(date_done-create_date))/(24*60*60))::decimal(16,2) as cycle_time
                FROM
                    stock_picking
                GROUP BY
                    id,
                    name,
                    date_done,
                    create_date,
                    date_planned,
                    partner_id,
                    is_backorder
            ) sp ON sm.picking_id = sp.id
            LEFT JOIN stock_picking_type spt ON sm.picking_type_id = spt.id
            INNER JOIN product_product p ON sm.product_id = p.id
            INNER JOIN product_template t ON p.product_tmpl_id = t.id
            INNER JOIN product_category cat ON t.categ_id = cat.id
            WHERE t.is_storable = true
        """

    def _group_by(self):
        return """
            sm.id,
            sm.reference,
            sm.picking_id,
            sm.state,
            sm.product_qty,
            sm.company_id,
            sp.name,
            sp.date_done,
            sp.creation_date,
            sp.date_planned,
            sp.partner_id,
            sp.is_backorder,
            sp.delay,
            sp.cycle_time,
            spt.code,
            spt.id,
            p.id,
            is_late,
            cat.id
        """

    def init(self) -> None:
        _debug.lifecycle("stock_report_view_init", model="stock.report")
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """CREATE or REPLACE VIEW %s as (
                            SELECT
                                %s
                            FROM
                                %s
                            GROUP BY
                                %s
            )"""
            % (
                self._table,
                self._select(),
                self._from(),
                self._group_by(),
            )
        )
