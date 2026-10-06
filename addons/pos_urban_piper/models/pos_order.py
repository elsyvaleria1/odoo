from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads


class PosOrder(models.Model):
    _inherit = "pos.order"

    delivery_status = fields.Selection(
        selection=[
            ("placed", "Placed"),
            ("acknowledged", "Acknowledged"),
            ("food_ready", "Food Ready"),
            ("dispatched", "Dispatched"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        help="Status of the order as provided by UrbanPiper.",
    )
    delivery_provider_id = fields.Many2one(
        comodel_name="pos.delivery.provider",
        help="Responsible delivery provider for online order, e.g., UberEats, Zomato.",
    )
    delivery_identifier = fields.Char(
        string="Delivery ID",
        help="Unique delivery ID provided by UrbanPiper.",
    )
    delivery_json = fields.Json(
        string="Delivery JSON",
        store=True,
        help="JSON data of the order.",
    )
    delivery_rider_json = fields.Json(
        string="Delivery Rider JSON",
        store=True,
        help="JSON data of the delivery rider.",
    )
    prep_time = fields.Integer(
        string="Food Preparation Time",
        help="Preparation time for the food as provided by UrbanPiper.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "delivery_status",
            "delivery_provider_id",
            "delivery_identifier",
            "delivery_json",
            "delivery_rider_json",
            "prep_time",
        ]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_online_order(self) -> None:
        if self.filtered(lambda o: o.delivery_identifier):
            raise UserError(
                self.env._(
                    "Online orders cannot be deleted. If needed, reject the order instead or contact the food delivery provider."
                )
            )

    @api.model
    def _load_pos_preparation_data_fields(self):
        res = super()._load_pos_preparation_data_fields()
        return res + [
            "delivery_status",
            "delivery_provider_id",
            "delivery_identifier",
            "prep_time",
            "config_id",
        ]

    def mark_urbanpiper_prep_order_as_printed(self) -> bool:
        self.check_singleton()
        self.lock_for_update()

        lopc = (
            json_loads(self.last_order_preparation_change)
            if self.last_order_preparation_change
            else {
                "lines": {},
                "metadata": {},
            }
        )
        if lopc.get("urbanpiper_printed", False):
            raise ValueError(
                "This delivery order has already been printed automatically."
            )

        lopc["urbanpiper_printed"] = True
        self.last_order_preparation_change = json_dumps(lopc)
        return True
