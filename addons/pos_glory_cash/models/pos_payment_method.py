from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"
    _CREDENTIAL_FIELDS = {
        "glory_password": "glory_password",
    }

    glory_websocket_address = fields.Char(string="Cash Machine IP")
    glory_username = fields.Char(string="Cash Machine Username")
    glory_password = fields.Char(
        string="Cash Machine Password",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        classification="point_of_sale.terminal_credential",
    )

    def _selection_payment_method_types(self):
        return super()._selection_payment_method_types() + [
            ("glory_cash", "Cash Machine (Glory)")
        ]

    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + [
            "glory_websocket_address",
            "glory_username",
            "glory_password",
        ]

    @api.model
    def _load_pos_data_till_secret_fields(self, config) -> list[str]:
        return [*super()._load_pos_data_till_secret_fields(config), "glory_password"]
