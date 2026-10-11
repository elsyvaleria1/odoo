from odoo import api, fields, models
from odoo.db.schema import column_exists, create_column


class AccountMove(models.Model):
    _inherit = "account.move"

    intrastat_transport_mode_id = fields.Many2one(
        comodel_name="account.intrastat.code",
        domain="[('type', '=', 'transport')]",
    )

    intrastat_country_id = fields.Many2one(
        comodel_name="res.country",
        compute="_compute_intrastat_country_id",
        store=True,
        readonly=False,
        domain=[("country_group_ids.code", "=", "INTRASTAT")],
        help="Intrastat country, arrival for sales, dispatch for purchases",
    )

    def _get_invoice_intrastat_country_id(self):
        self.check_singleton()
        if self.is_sale_document():
            if (
                self.partner_shipping_id.country_id
                and "INTRASTAT"
                in self.partner_shipping_id.country_id.country_group_codes
            ):
                return self.partner_shipping_id.country_id.id
            else:
                return False
        return self.partner_id.country_id.id

    @api.depends("partner_id", "partner_shipping_id")
    def _compute_intrastat_country_id(self) -> None:
        for move in self:
            if (
                move.partner_id.country_id
                and "INTRASTAT" in move.partner_id.country_id.country_group_codes
            ) or move.is_sale_document():
                move.intrastat_country_id = move._get_invoice_intrastat_country_id()
            else:
                move.intrastat_country_id = False


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _auto_init(self):
        if not column_exists(
            self.env.cr, "account_move_line", "intrastat_product_origin_country_id"
        ):
            create_column(
                self.env.cr,
                "account_move_line",
                "intrastat_product_origin_country_id",
                "int4",
            )
        return super()._auto_init()

    intrastat_transaction_id = fields.Many2one(
        comodel_name="account.intrastat.code",
        string="Intrastat",
        compute="_compute_intrastat_transaction_id",
        store=True,
        readonly=False,
        domain="[('type', '=', 'transaction')]",
    )
    intrastat_product_origin_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Product Country",
        compute="_compute_origin_country",
        store=True,
        readonly=False,
    )

    @api.depends("product_id", "move_id.intrastat_country_id")
    def _compute_origin_country(self) -> None:
        for line in self:
            line.intrastat_product_origin_country_id = (
                line.move_id.intrastat_country_id
                and line.product_id.product_tmpl_id.intrastat_origin_country_id
            ) or False

    @api.depends("move_id.move_type", "move_id.journal_id")
    def _compute_intrastat_transaction_id(self) -> None:
        for line in self:
            if line.move_id.intrastat_country_id:
                if line.move_id.move_type in ("in_invoice", "out_invoice"):
                    line.intrastat_transaction_id = line.move_id.company_id.intrastat_default_invoice_transaction_code_id
                    continue
                if line.move_id.move_type in ("in_refund", "out_refund"):
                    line.intrastat_transaction_id = line.move_id.company_id.intrastat_default_refund_transaction_code_id
                    continue
            line.intrastat_transaction_id = None

    def _get_fields_lock_date_protected(self):
        protected_fields = super()._get_fields_lock_date_protected()
        protected_fields["fiscal"] += [
            "intrastat_product_origin_country_id",
            "intrastat_transaction_id",
        ]
        return protected_fields

    def copy_data(self, default=None):
        data_list = super().copy_data(default=default)
        for line, values in zip(self, data_list, strict=True):
            if line.move_id.intrastat_country_id:
                values.pop("intrastat_transaction_id", None)
        return data_list
