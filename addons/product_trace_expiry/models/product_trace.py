import datetime

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTrace(models.Model):
    _inherit = "product.trace"

    use_expiration_date = fields.Boolean(
        related="product_id.use_expiration_date",
        string="Use Expiration Date",
    )
    expiration_date = fields.Datetime(
        compute="_compute_expiration_date",
        store=True,
        readonly=False,
        help="This is the date on which the goods with this Serial Number may become dangerous and must not be consumed.",
    )
    use_date = fields.Datetime(
        string="Best before Date",
        compute="_compute_use_date",
        store=True,
        readonly=False,
        help="This is the date on which the goods with this Serial Number start deteriorating, without being dangerous yet.",
    )
    removal_date = fields.Datetime(
        compute="_compute_removal_date",
        store=True,
        readonly=False,
        help="This is the date on which the goods with this Serial Number should be removed from the stock and not be counted in the Fresh On Hand Stock anymore. This date will be used in FEFO removal strategy.",
    )
    alert_date = fields.Datetime(
        compute="_compute_alert_date",
        store=True,
        index="btree_not_null",
        readonly=False,
        help='Date to determine the expired lots and serial numbers using the filter "Expiration Alerts".',
    )
    product_expiry_alert = fields.Boolean(
        compute="_compute_product_expiry_alert",
        help="The Expiration Date has been reached.",
    )
    product_expiry_reminded = fields.Boolean(string="Expiry has been reminded")

    @api.depends("use_expiration_date", "expiration_date", "alert_date")
    @api.depends_context("formatted_display_name")
    def _compute_display_name(self):
        lots_to_process_ids = []
        for lot in self:
            if (
                lot.env.context.get("formatted_display_name")
                and lot.use_expiration_date
                and lot.expiration_date
            ):
                name = f"{lot.name}"
                if fields.Datetime.now() >= lot.expiration_date:
                    name += self.env._("\t--Expired--")
                elif lot.alert_date and fields.Datetime.now() >= lot.alert_date:
                    name += self.env._(
                        "\t--Expire on %(date)s--",
                        date=fields.Datetime.to_string(lot.expiration_date),
                    )
                lot.display_name = name
            else:
                lots_to_process_ids.append(lot.id)
        if lots_to_process_ids:
            super(
                ProductTrace, self.env["product.trace"].browse(lots_to_process_ids)
            )._compute_display_name()

    @api.depends("expiration_date")
    def _compute_product_expiry_alert(self) -> None:
        _debug.perf.count("expiry_alert_compute", lots=self)
        current_date = fields.Datetime.now()
        for lot in self:
            lot.product_expiry_alert = (
                bool(lot.expiration_date) and lot.expiration_date <= current_date
            )

    @api.depends("product_id")
    def _compute_expiration_date(self) -> None:
        for lot in self:
            lot.expiration_date = lot.product_id._get_expiration_date_from(
                fields.Datetime.now()
            )

    @api.depends("product_id", "product_id.use_expiration_date", "expiration_date")
    def _compute_use_date(self) -> None:
        self._update_expiry_date("use_date", "use_time")

    @api.depends("product_id", "product_id.use_expiration_date", "expiration_date")
    def _compute_removal_date(self) -> None:
        self._update_expiry_date("removal_date", "removal_time")

    @api.depends("product_id", "product_id.use_expiration_date", "expiration_date")
    def _compute_alert_date(self) -> None:
        self._update_expiry_date("alert_date", "alert_time")

    def _update_expiry_date(self, date_field, time_field) -> None:
        _debug.lifecycle("lot_expiry_date_update", lots=self, field=date_field)
        for lot in self:
            if not lot.product_id.use_expiration_date or not lot.expiration_date:
                lot[date_field] = False
            else:
                lot[date_field] = lot.expiration_date - datetime.timedelta(
                    days=lot.product_id.product_tmpl_id[time_field]
                )
