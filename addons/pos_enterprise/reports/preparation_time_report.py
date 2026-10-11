from odoo import fields, models
from odoo.tools import SQL, frozendict


class PreparationTimeReport(models.Model):
    _name = "preparation.time.report"
    _auto = False
    _depends = frozendict(
        {
            "pos.order": ["config_id"],
            "pos.order.line": [
                "create_date",
                "order_id",
                "preparation_time",
                "product_id",
                "qty",
            ],
        }
    )
    _description = "POS Preparation Time Report"

    preparation_time = fields.Float()
    avg_preparation_time = fields.Float(string="Average Preparation Time")
    order_hour = fields.Char(string="Hour")
    create_date = fields.Datetime(string="Order Date")
    pos_config_id = fields.Many2one(
        comodel_name="pos.config",
        string="POS Config",
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
    )
    order_id = fields.Many2one(
        comodel_name="pos.order",
        readonly=True,
    )
    qty = fields.Float(string="Quantity")

    def _select(self):
        user_tz = self.env.user.tz or "UTC"
        return SQL(
            """
            CREATE OR REPLACE VIEW %(table_name)s AS
            WITH base AS (
                SELECT
                    line.id,
                    line.preparation_time,
                    line.create_date AS create_date,
                    line.product_id AS product_id,
                    line.order_id AS order_id,
                    line.qty AS qty,
                    TO_CHAR(line.create_date AT TIME ZONE 'UTC' AT TIME ZONE %(user_tz)s, 'HH24:00') AS order_hour,
                    pc.id AS pos_config_id
                FROM pos_order_line line
                JOIN pos_order po ON line.order_id = po.id
                JOIN pos_config pc ON po.config_id = pc.id
                WHERE line.preparation_time >= 0
            )
            SELECT
                id,
                preparation_time,
                AVG(preparation_time) OVER (
                    PARTITION BY order_hour, pos_config_id
                ) /
                COUNT(*) OVER (
                    PARTITION BY order_hour, pos_config_id
                ) AS avg_preparation_time,
                create_date,
                order_hour,
                product_id,
                order_id,
                qty,
                pos_config_id
            FROM base
            """,
            table_name=SQL.identifier(self._table),
            user_tz=user_tz,
        )

    def init(self) -> None:
        self.env.cr.execute(self._select())
