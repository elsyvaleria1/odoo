from datetime import timedelta

from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    delivery_datetime = fields.Datetime(
        help="Scheduled delivery datetime for the delivery order."
    )
    is_notified = fields.Boolean(
        help="Flag indicating if the delivery notification has been sent."
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "delivery_datetime",
        ]

    @api.model
    def notify_future_deliveries(self) -> None:
        future_orders = self.search(
            [
                ("delivery_datetime", ">", fields.Datetime.now()),
                ("is_notified", "=", False),
            ]
        )
        orders_to_notify = self.env["pos.order"]
        for order in future_orders:
            delivery_datetime = order.delivery_datetime
            notify_time = delivery_datetime - timedelta(minutes=order.prep_time)
            if fields.Datetime.now() >= notify_time:
                orders_to_notify |= order
        if orders_to_notify:
            for order in orders_to_notify:
                if not order.session_id.config_id.current_session_id:
                    order.session_id.config_id.order_status_update(
                        order.id, "Cancelled", "store_closed"
                    )
                    order.state = "cancel"
                    continue
                if order.session_id != order.session_id.config_id.current_session_id:
                    order.session_id = order.session_id.config_id.current_session_id
            orders_by_config = orders_to_notify.grouped(
                lambda o: o.session_id.config_id
            )
            for config in orders_to_notify.session_id.config_id:
                config[0]._notify(
                    "FUTURE_ORDER_NOTIFICATION", orders_by_config[config].ids
                )
            orders_to_notify.is_notified = True
