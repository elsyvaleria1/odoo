import io
from unittest.mock import patch

from PIL import Image

from odoo import Command
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.telegram.tests.common import TelegramBotTestCase

OFFICE_CHAT = "598001"
SHEET = {
    "tracking_ref": "TOL01584640",
    "destination": "TAPACHULA, CHIS.",
    "service": "ocurre",
    "total": 4731.25,
    "subtotal": 4078.66,
    "tax_amount": 652.59,
}


def _png(seed) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1 + seed % 50, 1 + seed // 50)).save(buffer, format="PNG")
    return buffer.getvalue()


@tagged("post_install", "-at_install")
class TestShipmentFlow(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public = cls.env.ref("base.public_user")
        cls.office_user = cls.env["res.users"].create(
            {
                "name": "Office",
                "login": "tg_ship_office",
                "group_ids": [Command.set([cls.env.ref("stock.group_stock_user").id])],
            }
        )
        cls._bound_account(
            OFFICE_CHAT, cls.office_user.partner_id, user=cls.office_user
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tres Guerras",
                "product_id": cls.env["product.product"]
                .create({"name": "Freight", "type": "service"})
                .id,
                "tracking_ref_pattern": "[A-Z]{3}[0-9]{8}",
                "tracking_ref_example": "TOL01584640",
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "Agro Customer"})
        cls.supplier = cls.env["res.partner"].create({"name": "Agro Supplier"})
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.out = cls._picking(warehouse.out_type_id, cls.customer)
        cls.other_out = cls._picking(warehouse.out_type_id, cls.customer)
        cls.receipt = cls._picking(warehouse.in_type_id, cls.supplier)
        cls.test_bot.command_ids = cls.env.ref(
            "stock_shipment_telegram.command_embarque"
        )
        cls.update_id = 7700
        cls.Sheet = cls.env["telegram.shipment.sheet"]

    @classmethod
    def _picking(cls, picking_type, partner, **values):
        return cls.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id,
                "carrier_id": cls.carrier.id
                if picking_type.code == "outgoing"
                else False,
                **values,
            }
        )

    def _update(self, payload, read=None):
        type(self).update_id += 1
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        values = SHEET if read is None else read
        with (
            patch.object(
                type(self.test_bot),
                "get_file",
                lambda bot, file_id: {
                    "content": _png(int(file_id.rpartition("-")[2] or 0)),
                    "file_path": f"photos/{file_id}.png",
                },
            ),
            patch.object(
                type(self.Sheet), "_read_sheet", lambda sheet, content: values
            ),
            self.mock_api_gateway_post() as post,
            self.mock_rate_limiter(),
        ):
            self.env["telegram.router"]._handle_update(
                self.test_bot.with_user(self.public).sudo(),
                {"update_id": self.update_id, **payload},
            )
        self.posted = [call.kwargs.get("json") or {} for call in post.call_args_list]
        return "\n".join(
            call.kwargs["json"].get("text", "")
            for call in post.call_args_list
            if call.kwargs.get("json")
        )

    def _say(self, text):
        return self._update(
            {
                "message": self.mock_telegram_message(
                    chat_id=OFFICE_CHAT, text=text, message_id=self.update_id
                )
            }
        )

    def _sheet_photo(self, read=None):
        message = self.mock_telegram_message(
            chat_id=OFFICE_CHAT, text="", message_id=self.update_id
        )
        message.pop("text")
        seed = self.update_id
        message["photo"] = [{"file_id": f"sheet-{seed}", "file_unique_id": f"s-{seed}"}]
        return self._update({"message": message}, read=read)

    def _press(self, data):
        return self._update(
            {
                "callback_query": self.mock_telegram_callback_query(
                    callback_data=data, chat_id=OFFICE_CHAT
                )
            }
        )

    def _last_sheet(self):
        return self.Sheet.search([], limit=1)

    def _offered(self):
        for message in reversed(self.posted):
            markup = message.get("reply_markup") or {}
            if isinstance(markup, str):
                markup = json_loads(markup)
            if markup.get("inline_keyboard"):
                return [
                    button["callback_data"]
                    for row in markup["inline_keyboard"]
                    for button in row
                ]
        return []

    def test_the_tracking_number_goes_on_the_chosen_delivery(self):
        self._say("/embarque")
        reply = self._sheet_photo()
        sheet = self._last_sheet()
        self.assertIn("TOL01584640", reply)
        self.assertIn(self.out, sheet.candidate_ids)
        self.assertEqual(sheet.carrier_id, self.carrier)

        reply = self._press(f"emb:p:{sheet.id}:{self.out.id}")

        self.assertEqual(self.out.carrier_tracking_ref, "TOL01584640")
        self.assertEqual(self.out.carrier_id, self.carrier)
        self.assertEqual((sheet.state, sheet.picking_id), ("done", self.out))
        self.assertTrue(
            self.out.message_ids.attachment_ids, "the sheet is kept as sent"
        )
        self.assertEqual(sheet.extracted["total"], 4731.25)
        self.assertIn(self.out.name, reply)
        self.assertIn("4,731.25", reply)

    def test_an_unreadable_tracking_number_is_refused(self):
        self._say("/embarque")
        reply = self._sheet_photo(read={"total": 100.0})
        self.assertIn("could not read the tracking number", reply)
        self.assertEqual(self._last_sheet().state, "error")

    def test_a_number_no_carrier_uses_is_refused(self):
        self._say("/embarque")
        reply = self._sheet_photo(read={"tracking_ref": "123"})
        self.assertIn("No carrier uses tracking numbers like 123", reply)

    def test_another_tracking_number_is_never_overwritten(self):
        self.out.carrier_tracking_ref = "TOL00000001"
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self.assertNotIn(
            self.out, sheet.candidate_ids, "only free or matching transfers"
        )
        sheet.candidate_ids = self.out
        reply = self._press(f"emb:p:{sheet.id}:{self.out.id}")
        self.assertIn("already carries tracking number TOL00000001", reply)
        self.assertEqual(self.out.carrier_tracking_ref, "TOL00000001")

    def test_the_transfer_already_carrying_the_number_comes_first(self):
        self.other_out.carrier_tracking_ref = "TOL01584640"
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self.assertEqual(self._offered()[0], f"emb:p:{sheet.id}:{self.other_out.id}")

    def test_a_purchase_the_carrier_brings_goes_on_the_receipt(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        reply = self._press(f"emb:in:{sheet.id}")
        self.assertIn(self.receipt, sheet.candidate_ids)
        self.assertIn("receipt", reply)
        self._press(f"emb:p:{sheet.id}:{self.receipt.id}")
        self.assertEqual(self.receipt.carrier_tracking_ref, "TOL01584640")

    def test_none_of_these_records_nothing(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self._press(f"emb:x:{sheet.id}")
        self.assertEqual(sheet.state, "error")
        self.assertFalse(self.out.carrier_tracking_ref)

    def _transfer_buttons(self):
        return [
            data for data in self._offered() if data.startswith(("emb:p:", "emb:m:"))
        ]

    @staticmethod
    def _tail(picking):
        return picking.name.rpartition("/")[2]

    def test_typed_digits_offer_the_delivery_ending_in_them(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()

        reply = self._say(self._tail(self.other_out))

        self.assertIn("ending in", reply)
        self.assertIn(f"emb:p:{sheet.id}:{self.other_out.id}", self._transfer_buttons())
        self.assertNotIn(f"emb:p:{sheet.id}:{self.out.id}", self._transfer_buttons())
        self._press(f"emb:p:{sheet.id}:{self.other_out.id}")
        self.assertEqual(self.other_out.carrier_tracking_ref, "TOL01584640")
        self.assertFalse(self.out.carrier_tracking_ref)

    def test_a_button_offered_before_the_digits_still_assigns(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self._say(self._tail(self.other_out))

        self._press(f"emb:p:{sheet.id}:{self.out.id}")

        self.assertEqual(self.out.carrier_tracking_ref, "TOL01584640")

    def test_digits_no_open_delivery_ends_in_offer_none(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()

        reply = self._say("999999")

        self.assertIn("ends in", reply)
        self.assertFalse(self._transfer_buttons())
        self.assertEqual(sheet.state, "pending", "the sheet still waits")

    def test_digits_before_any_sheet_ask_for_the_sheet(self):
        self._say("/embarque")
        reply = self._say(self._tail(self.out))
        self.assertIn("Send the shipping order first", reply)
        self.assertFalse(self.Sheet.search([]))

    def test_one_tracking_number_goes_on_several_deliveries(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()

        reply = self._press(f"emb:p:{sheet.id}:{self.out.id}")
        self.assertIn("also cover another", reply)
        self._press(f"emb:m:{sheet.id}:{self.other_out.id}")

        sheets = self.Sheet.search([("tracking_ref", "=", "TOL01584640")])
        self.assertEqual(sheets.picking_id, self.out | self.other_out)
        self.assertEqual(set(sheets.mapped("state")), {"done"})
        self.assertEqual(self.other_out.carrier_tracking_ref, "TOL01584640")
        self.assertEqual(self.other_out.carrier_id, self.carrier)
        self.assertTrue(
            self.other_out.message_ids.attachment_ids, "each transfer keeps the sheet"
        )

    def test_typed_digits_add_one_more_delivery(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self._press(f"emb:p:{sheet.id}:{self.out.id}")

        reply = self._say(self._tail(self.other_out))
        self.assertIn("ending in", reply)
        self._press(f"emb:m:{sheet.id}:{self.other_out.id}")

        self.assertEqual(self.other_out.carrier_tracking_ref, "TOL01584640")

    def test_a_delivery_already_carrying_the_number_is_not_added_twice(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self._press(f"emb:p:{sheet.id}:{self.out.id}")

        reply = self._press(f"emb:m:{sheet.id}:{self.out.id}")

        self.assertIn("no longer valid", reply)
        self.assertEqual(
            self.Sheet.search_count([("tracking_ref", "=", "TOL01584640")]), 1
        )

    def test_a_button_pressed_after_finishing_still_assigns(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self._press("emb:fin")

        self._press(f"emb:p:{sheet.id}:{self.out.id}")

        self.assertEqual(self.out.carrier_tracking_ref, "TOL01584640")

    def _second_sheet(self):
        self._sheet_photo(read={**SHEET, "tracking_ref": "TOL01584641"})
        return self._last_sheet()

    def test_a_button_of_an_older_sheet_leaves_the_digits_on_the_newest(self):
        self._say("/embarque")
        self._sheet_photo()
        older = self._last_sheet()
        newest = self._second_sheet()

        reply = self._press(f"emb:p:{older.id}:{self.out.id}")
        self.assertNotIn("also cover another", reply, "no offer for the older sheet")
        self._say(self._tail(self.other_out))

        self.assertIn(
            f"emb:p:{newest.id}:{self.other_out.id}", self._transfer_buttons()
        )
        self.assertFalse(
            [data for data in self._transfer_buttons() if data.startswith("emb:m:")]
        )

    def test_receipt_of_an_older_sheet_leaves_the_newest_on_deliveries(self):
        self._say("/embarque")
        self._sheet_photo()
        older = self._last_sheet()
        newest = self._second_sheet()

        self._press(f"emb:in:{older.id}")
        self._say(self._tail(self.other_out))

        self.assertIn(
            f"emb:p:{newest.id}:{self.other_out.id}", self._transfer_buttons()
        )

    def test_one_more_after_finishing_is_refused(self):
        self._say("/embarque")
        self._sheet_photo()
        sheet = self._last_sheet()
        self._press(f"emb:p:{sheet.id}:{self.out.id}")
        self._press("emb:fin")

        reply = self._press(f"emb:m:{sheet.id}:{self.other_out.id}")

        self.assertIn("no longer valid", reply)
        self.assertFalse(self.other_out.carrier_tracking_ref)
