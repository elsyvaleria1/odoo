from odoo import fields, models

from odoo.addons.trade.tools import SALE


class TestTradeOrder(models.Model):
    _name = "test_trade.order"
    _inherit = [
        "mixin.order",
        "mixin.order.amount",
        "mixin.order.merge",
    ]
    _description = "Base Order Test"

    line_ids = fields.One2many(comodel_name="test_trade.order.line")
    duplicated_order_ids = fields.Many2many(comodel_name="test_trade.order")
    partner_ref = fields.Char(copy=False)

    _direction = SALE
    _lock_setting_field = "test_trade_order_lock"

    _sequence_code = "test_trade.order"
    _mark_sent_context_key = "mark_test_trade_order_as_sent"
    _display_name_context_key = "test_trade_order_show_partner_name"
    _portal_url_prefix = "base-order-test"
    _auto_lock_group = ""

    def _get_duplicate_ref_field(self):
        return "partner_ref"

    def _get_display_name_suffix(self):
        if not self.env.context.get(self._get_display_name_context_key()):
            return ""
        return f" - {self.partner_id.name}" if self.partner_id.name else ""

    def _get_import_template_label(self):
        return "Import Template for Base Order Test"

    def _get_import_template_path(self):
        return "/test_trade_order/static/xls/test_trade_order.xls"

    def _get_catalog_removed_line_price(self, product, **kwargs):
        return product.list_price

    def _get_catalog_line_price(self, line):
        return line.price_unit

    def _get_mail_subtitles(self, render_context):
        return [self.name]

    def _get_state_track_subtype_xmlid(self, init_values):
        if "state" in init_values and self.state == "done":
            return "mail.mt_note"
        return None
