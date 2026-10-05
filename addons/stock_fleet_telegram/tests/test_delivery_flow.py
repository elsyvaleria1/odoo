import base64
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.telegram.tests.common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestDeliveryFlow(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = warehouse.out_type_id
        cls.out_type.write(
            {
                "dispatch_management": True,
                "dispatch_batch_required": True,
                "delivery_proof_required": True,
            }
        )
        cls.seller_user = cls.env["res.users"].create(
            {
                "name": "Seller",
                "login": "tg_trip_seller",
                "group_ids": [
                    Command.set([cls.env.ref("stock_fleet.group_trip_driver").id])
                ],
            }
        )
        cls._bound_account("599001", cls.seller_user.partner_id, user=cls.seller_user)
        supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "tg_trip_supervisor",
                "group_ids": [Command.set([cls.env.ref("stock.group_stock_user").id])],
            }
        )
        seller = cls.env["hr.employee"].create(
            {"name": "Seller", "user_id": cls.seller_user.id}
        )
        kind = cls.env.ref("resource_asset.kind_vehicle")
        car = cls.env["resource.resource"].create(
            {
                "name": "Pickup",
                "kind_id": kind.id,
                "product_id": cls.env["product.product"]
                .create({"name": "Pickup", "type": "consu", "asset_kind_id": kind.id})
                .id,
                "operator_id": seller.resource_id.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertilizer", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 100
        )
        cls.pickings = cls.env["stock.picking"]
        for name in ("Rancho Uno", "Rancho Dos"):
            picking = cls.env["stock.picking"].create(
                {
                    "picking_type_id": cls.out_type.id,
                    "partner_id": cls.env["res.partner"].create({"name": name}).id,
                    "location_id": cls.stock_location.id,
                    "location_dest_id": cls.customer_location.id,
                    "move_ids": [
                        Command.create(
                            {
                                "product_id": cls.product.id,
                                "product_uom_qty": 1,
                                "location_id": cls.stock_location.id,
                                "location_dest_id": cls.customer_location.id,
                            }
                        )
                    ],
                }
            )
            picking.action_confirm()
            picking.action_assign()
            cls.pickings |= picking
        cls.trip = cls.env["stock.picking.batch"].create(
            {
                "picking_type_id": cls.out_type.id,
                "picking_ids": [Command.set(cls.pickings.ids)],
                "vehicle_id": car.id,
                "operator_id": seller.id,
                "supervisor_id": supervisor.id,
                "odometer_departure": 1000.0,
            }
        )
        cls.trip.action_depart()
        cls.test_bot.command_ids = cls.env.ref("stock_fleet_telegram.command_entrega")
        cls.update_id = 9900

    def _update(self, payload, codes=()):
        type(self).update_id += 1
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        handler = type(self.env["telegram.handler.stock_fleet"])
        with (
            patch.object(
                type(self.test_bot),
                "get_file_content",
                lambda bot, file_id: base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                ),
            ),
            patch.object(
                handler, "_read_slip_codes", lambda self, content: list(codes)
            ),
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(),
                {"update_id": self.update_id, **payload},
            )
        return "\n".join(
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        )

    def _say(self, text):
        return self._update(
            {
                "message": self.mock_telegram_message(
                    chat_id="599001", text=text, message_id=self.update_id
                )
            }
        )

    def _photo(self, codes=()):
        message = self.mock_telegram_message(
            chat_id="599001", text="", message_id=self.update_id
        )
        message.pop("text")
        message["photo"] = [{"file_id": "slip", "file_unique_id": "slip"}]
        return self._update({"message": message}, codes=codes)

    def _press(self, data):
        return self._update(
            {
                "callback_query": self.mock_telegram_callback_query(
                    callback_data=data, chat_id="599001"
                )
            }
        )

    def test_the_qr_code_names_the_delivery_and_it_is_delivered(self):
        first = self.pickings[0]
        self._say("/entrega")
        reply = self._photo(codes=[first.name])
        self.assertIn(first.name, reply)

        reply = self._press("ent:ok")

        self.assertEqual(first.state, "done")
        self.assertTrue(first.delivery_proof)
        self.assertEqual(first.delivery_proof_uid, self.seller_user)
        self.assertIn("Hand the paper in by", reply)

    def test_an_unreadable_slip_is_chosen_from_the_pending_deliveries(self):
        second = self.pickings[1]
        self._say("/entrega")
        reply = self._photo()
        self.assertIn("Which one", reply)

        self._press(f"ent:p:{second.id}")
        self._press("ent:ok")

        self.assertEqual(second.state, "done")
        self.assertTrue(second.delivery_proof)

    def test_the_last_delivery_closes_the_salespersons_trip_only_with_its_mode(self):
        for picking in self.pickings:
            self._say("/entrega")
            self._photo(codes=[picking.name])
            self._press("ent:ok")
        self.assertEqual(set(self.pickings.mapped("state")), {"done"})
        self.assertFalse(self.trip.date_return)
