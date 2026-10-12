import ast
import base64
import io
from unittest.mock import patch

from PIL import Image

from odoo import Command
from odoo.exceptions import AccessError, RedirectWarning, UserError
from odoo.libs.documents.document import Document
from odoo.tests import tagged

from odoo.addons.telegram.tests.common import TelegramBotTestCase

DRIVER_CHAT = "599001"
OFFICE_CHAT = "599002"


def _pdf(seed) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40 + seed % 50, 60)).save(buffer, format="PDF")
    return buffer.getvalue()


def _png(seed) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1 + seed % 50, 1 + seed // 50)).save(buffer, format="PNG")
    return buffer.getvalue()


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
        cls._bound_account(
            DRIVER_CHAT, cls.seller_user.partner_id, user=cls.seller_user
        )
        supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "tg_trip_supervisor",
                "group_ids": [Command.set([cls.env.ref("stock.group_stock_user").id])],
            }
        )
        cls.office_user = cls.env["res.users"].create(
            {
                "name": "Office",
                "login": "tg_trip_office",
                "group_ids": [Command.set([cls.env.ref("stock.group_stock_user").id])],
            }
        )
        cls._bound_account(
            OFFICE_CHAT, cls.office_user.partner_id, user=cls.office_user
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "Reviewer",
                "login": "tg_trip_reviewer",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("stock.group_stock_user").id,
                            cls.env.ref("stock_fleet.group_delivery_proof_reviewer").id,
                        ]
                    )
                ],
            }
        )
        seller = cls.env["hr.employee"].create(
            {"name": "Seller", "user_id": cls.seller_user.id}
        )
        kind = cls.env.ref("base.kind_vehicle")
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
        cls.Slip = cls.env["telegram.delivery.slip"]
        cls.Receipt = cls.env["stock.delivery.slip.receipt"]

    def _update(self, payload, codes=(), text="", content=None, reading=None):
        type(self).update_id += 1
        self.patch(self.env.transaction, "default_env", self.env(user=self.public))
        slip_class = type(self.Slip)

        def read(slip, document, representation, empty):
            return list(codes) if representation == "barcodes" else text

        with (
            patch.object(
                type(self.test_bot),
                "get_file",
                lambda bot, file_id: {
                    "content": content or _png(int(file_id.rpartition("-")[2] or 0)),
                    "file_path": f"photos/{file_id}.png",
                },
            ),
            patch.object(slip_class, "_read", read),
            patch.object(
                slip_class, "_read_with_model", lambda slip, content: reading or {}
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

    def _say(self, text, chat=DRIVER_CHAT):
        return self._update(
            {
                "message": self.mock_telegram_message(
                    chat_id=chat, text=text, message_id=self.update_id
                )
            }
        )

    def _photo(
        self, codes=(), text="", chat=DRIVER_CHAT, seed=None, unique=None, reading=None
    ):
        seed = self.update_id if seed is None else seed
        message = self.mock_telegram_message(
            chat_id=chat, text="", message_id=self.update_id
        )
        message.pop("text")
        message["photo"] = [
            {"file_id": f"slip-{seed}", "file_unique_id": unique or f"u-{seed}"}
        ]
        return self._update(
            {"message": message}, codes=codes, text=text, reading=reading
        )

    def _document(self, mimetype, content, codes=(), chat=DRIVER_CHAT):
        message = self.mock_telegram_message(
            chat_id=chat, text="", message_id=self.update_id
        )
        message.pop("text")
        message["document"] = {
            "file_id": f"doc-{self.update_id}",
            "file_unique_id": f"d-{self.update_id}",
            "file_name": "remision.pdf",
            "mime_type": mimetype,
            "file_size": len(content),
        }
        return self._update({"message": message}, codes=codes, content=content)

    def _press(self, data, chat=DRIVER_CHAT):
        return self._update(
            {
                "callback_query": self.mock_telegram_callback_query(
                    callback_data=data, chat_id=chat
                )
            }
        )

    def _chat(self, chat=DRIVER_CHAT):
        return self.env["telegram.chat"].search(
            [("bot_id", "=", self.test_bot.id), ("chat_id", "=", chat)]
        )

    def _last_slip(self, chat=DRIVER_CHAT):
        return self.Slip.search([("chat_id", "=", self._chat(chat).id)], limit=1)

    def test_the_code_names_the_delivery_and_its_driver_delivers_it(self):
        first = self.pickings[0]
        self._say("/entrega")
        reply = self._photo(codes=[first.name])

        self.assertEqual(first.state, "done")
        self.assertTrue(first.delivery_proof)
        self.assertEqual(first.delivery_proof_uid, self.seller_user)
        slip = self._last_slip()
        self.assertEqual(
            (slip.state, slip.outcome, slip.found_by), ("done", "delivered", "code")
        )
        self.assertEqual(slip.receipt_id.state, "draft")
        self.assertTrue(first.message_ids.attachment_ids, "The file is kept as sent.")
        self.assertIn("I validated it", reply)
        self.assertIn("Hand the paper in by", reply)

    def test_the_signed_code_finds_its_delivery_and_a_forged_one_nothing(self):
        first = self.pickings[0]
        code = first._get_delivery_slip_qr_value()
        Picking = self.env["stock.picking"]
        self.assertEqual(Picking._find_by_delivery_slip_qr([code]), first)
        prefix, picking_id, signature = code.split(":")
        self.assertFalse(
            Picking._find_by_delivery_slip_qr(
                [f"{prefix}:{int(picking_id) + 1}:{signature}"]
            )
        )
        self.assertFalse(
            Picking._find_by_delivery_slip_qr([f"{prefix}:{picking_id}:0"])
        )

    def test_the_printed_qr_decodes_back_to_its_delivery(self):
        first = self.pickings[0]
        code = first._get_delivery_slip_qr_value()
        image = self.env["ir.actions.report"].prepare_barcode(
            "QR", code, width=400, height=400
        )
        self.assertIn(code, Document(image, name="slip.png").barcodes)

    def test_the_signed_qr_names_the_delivery_and_its_driver_delivers_it(self):
        first = self.pickings[0]
        self._say("/entrega")
        reply = self._photo(codes=[first._get_delivery_slip_qr_value()])

        self.assertEqual(first.state, "done")
        slip = self._last_slip()
        self.assertEqual(
            (slip.state, slip.outcome, slip.found_by), ("done", "delivered", "qr")
        )
        self.assertIn("I validated it", reply)

    def test_the_signed_qr_wins_over_another_name_on_the_paper(self):
        first, second = self.pickings
        self._say("/entrega")
        self._photo(codes=[second.name, first._get_delivery_slip_qr_value()])

        self.assertEqual(self._last_slip().picking_id, first)
        self.assertEqual(second.state, "assigned")

    def test_the_model_reading_needs_the_customer_too(self):
        first = self.pickings[0]
        reading = {
            "delivery_order": first.name,
            "customer_name": "Someone Else",
            "customer_rfc": "",
        }
        self._say("/entrega")
        reply = self._photo(reading=reading)

        self.assertFalse(first.delivery_proof)
        self.assertEqual(self._last_slip().state, "pending")
        self.assertIn("Which one?", reply)

        reading["customer_name"] = "rancho  uno"
        self._photo(reading=reading)

        slip = self._last_slip()
        self.assertEqual((slip.state, slip.found_by), ("done", "model"))
        self.assertEqual(first.state, "done")

    def test_a_delivered_slip_is_listed_until_its_paper_arrives(self):
        first = self.pickings[0]
        self._say("/entrega")
        self._photo(codes=[first._get_delivery_slip_qr_value()])
        action = self.env.ref("stock_fleet_telegram.action_picking_delivered_slip")
        domain = ast.literal_eval(action.domain)

        pending = [("delivery_paper_received", "=", False)]
        self.assertIn(first, self.env["stock.picking"].search(domain + pending))
        first.with_user(self.reviewer).action_receive_delivery_paper()
        self.assertNotIn(first, self.env["stock.picking"].search(domain + pending))

    def test_the_number_with_its_customer_on_the_paper_identifies_it(self):
        first = self.pickings[0]
        self._say("/entrega")
        self._photo(text=f"Remision\n{first.name}\nRANCHO UNO\n")

        self.assertEqual(first.state, "done")
        self.assertEqual(self._last_slip().found_by, "text")

    def test_the_number_without_its_customer_designates_nothing(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        reply = self._photo(text=f"{first.name}\nOtro Cliente", chat=OFFICE_CHAT)

        self.assertFalse(first.delivery_proof)
        self.assertEqual(self._last_slip(OFFICE_CHAT).state, "error")
        self.assertIn("could not read", reply)

    def test_an_unreadable_slip_is_chosen_from_the_pending_deliveries(self):
        second = self.pickings[1]
        self._say("/entrega")
        reply = self._photo()
        self.assertIn("Which one", reply)
        slip = self._last_slip()
        self.assertEqual(slip.candidate_ids, self.pickings)

        self._press(f"ent:p:{slip.id}:{second.id}")

        self.assertEqual(second.state, "done")
        self.assertTrue(second.delivery_proof)
        self.assertEqual(slip.found_by, "choice")

    def test_none_of_the_offered_deliveries_files_nothing(self):
        self._say("/entrega")
        self._photo()
        slip = self._last_slip()

        reply = self._press(f"ent:x:{slip.id}")

        self.assertEqual(slip.state, "error")
        self.assertFalse(self.pickings.filtered("delivery_proof"))
        self.assertIn("Nothing filed", reply)

    def test_a_button_naming_a_delivery_not_offered_is_refused(self):
        self._say("/entrega")
        self._photo()
        slip = self._last_slip()
        stranger = self.pickings[0].copy()

        reply = self._press(f"ent:p:{slip.id}:{stranger.id}")

        self.assertIn("no longer valid", reply)
        self.assertFalse(stranger.delivery_proof)
        self.assertEqual(slip.state, "pending")

    def test_a_button_of_another_chat_is_refused(self):
        self._say("/entrega")
        self._photo()
        slip = self._last_slip()

        reply = self._press(f"ent:p:{slip.id}:{self.pickings[0].id}", chat=OFFICE_CHAT)

        self.assertIn("no longer valid", reply)
        self.assertFalse(self.pickings[0].delivery_proof)

    def test_the_last_delivery_does_not_close_a_trip_whose_vehicle_returns(self):
        self._say("/entrega")
        for picking in self.pickings:
            self._photo(codes=[picking.name])
        self.assertEqual(set(self.pickings.mapped("state")), {"done"})
        self.assertFalse(self.trip.date_return)

    def test_someone_off_the_trip_only_files_the_slip(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        reply = self._photo(codes=[first.name], chat=OFFICE_CHAT)

        self.assertEqual(first.state, "assigned")
        self.assertTrue(first.delivery_proof)
        self.assertEqual(first.delivery_proof_uid, self.office_user)
        self.assertEqual(self._last_slip(OFFICE_CHAT).outcome, "filed")
        self.assertIn("only the driver", reply)

    def test_the_driver_delivers_what_the_office_filed(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        self._photo(codes=[first.name], chat=OFFICE_CHAT)
        office_photo = first.delivery_proof

        self._say("/entrega")
        reply = self._photo(codes=[first.name])

        self.assertEqual(first.state, "done")
        self.assertEqual(first.delivery_proof, office_photo)
        self.assertIn("with the signed slip it already had", reply)

    def test_a_validation_that_does_not_go_through_keeps_the_slip(self):
        first = self.pickings[0]
        self._say("/entrega")

        def refuse(picking):
            raise UserError("Credit limit reached")

        with patch.object(type(first), "action_deliver", refuse):
            reply = self._photo(codes=[first.name])

        self.assertEqual(first.state, "assigned")
        self.assertTrue(first.delivery_proof)
        self.assertEqual(self._last_slip().outcome, "filed")
        self.assertIn("Credit limit reached", reply)

    def test_a_validation_that_asks_a_question_is_undone_and_said(self):
        first = self.pickings[0]
        self._say("/entrega")

        def open_wizard(picking):
            picking.move_ids.picked = True
            return {"type": "ir.actions.act_window", "res_model": "x"}

        with patch.object(type(first), "action_deliver", open_wizard):
            reply = self._photo(codes=[first.name])

        self.assertEqual(first.state, "assigned")
        self.assertFalse(any(first.move_ids.mapped("picked")), "Undone whole.")
        self.assertTrue(first.delivery_proof)
        self.assertIn("only Odoo asks", reply)

    def test_a_delivery_with_valid_evidence_is_not_filed_again(self):
        first = self.pickings[0]
        self._say("/entrega")
        self._photo(codes=[first.name])
        photo = first.delivery_proof

        self._say("/entrega", chat=OFFICE_CHAT)
        reply = self._photo(codes=[first.name], chat=OFFICE_CHAT)

        self.assertEqual(first.delivery_proof, photo)
        self.assertEqual(self._last_slip(OFFICE_CHAT).state, "error")
        self.assertIn("already has its signed slip", reply)

    def test_a_paper_already_received_is_not_touched(self):
        first = self.pickings[0]
        first.delivery_paper_received = True
        self._say("/entrega")
        reply = self._photo(codes=[first.name])

        self.assertFalse(first.delivery_proof)
        self.assertIn("already received the signed paper", reply)

    def test_the_same_file_is_not_filed_twice(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        self._photo(codes=[first.name], chat=OFFICE_CHAT, seed=7)
        reply = self._photo(codes=[first.name], chat=OFFICE_CHAT, seed=7)

        self.assertIn("same file was already filed", reply)
        self.assertEqual(
            self.Slip.search_count([("chat_id", "=", self._chat(OFFICE_CHAT).id)]), 1
        )

    def test_finish_hands_the_batch_to_administration(self):
        self._say("/entrega")
        for picking in self.pickings:
            self._photo(codes=[picking.name])

        reply = self._press("ent:fin")

        receipt = self.Receipt.search([("telegram_chat_id", "=", self._chat().id)])
        self.assertEqual(receipt.state, "submitted")
        self.assertEqual(receipt.delivered_by_id, self.seller_user)
        self.assertEqual(receipt.slip_ids.picking_id, self.pickings)
        self.assertFalse(self._chat().flow_owner)
        for picking in self.pickings:
            self.assertIn(picking.name, reply)

    def test_finish_still_hands_in_a_cancelled_session(self):
        self._say("/entrega")
        self._photo(codes=[self.pickings[0].name])
        self._say("/cancelar")

        self._press("ent:fin")

        receipt = self.Receipt.search([("telegram_chat_id", "=", self._chat().id)])
        self.assertEqual(receipt.state, "submitted")

    def _handed_in(self):
        self._say("/entrega")
        for picking in self.pickings:
            self._photo(codes=[picking.name])
        self._press("ent:fin")
        return self.Receipt.search([("telegram_chat_id", "=", self._chat().id)])

    def test_confirming_the_batch_receives_the_papers_in_hand(self):
        arrived, missing = self.pickings
        receipt = self._handed_in().with_user(self.reviewer)
        receipt.slip_ids.filtered(
            lambda slip: slip.picking_id == missing
        ).action_remove_from_receipt()

        action = receipt.action_confirm()

        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(receipt.state, "done")
        self.assertNotEqual(receipt.name, "/")
        self.assertTrue(arrived.delivery_paper_received)
        self.assertEqual(arrived.delivery_paper_received_uid, self.reviewer)
        self.assertFalse(missing.delivery_paper_received)

    def test_only_a_reviewer_confirms_the_batch(self):
        receipt = self._handed_in()
        with self.assertRaises(AccessError):
            receipt.with_user(self.seller_user).action_confirm()

    def test_cancelling_a_confirmed_batch_gives_the_papers_back(self):
        receipt = self._handed_in().with_user(self.reviewer)
        receipt.action_confirm()
        receipt.action_cancel()
        self.assertEqual(receipt.state, "cancel")
        self.assertFalse(self.pickings.filtered("delivery_paper_received"))

    def test_a_redirect_warning_keeps_the_slip_and_says_why(self):
        first = self.pickings[0]
        self._say("/entrega")

        def redirect(picking):
            raise RedirectWarning("Approval required", {"type": "x"}, "Open")

        with patch.object(type(first), "action_deliver", redirect):
            reply = self._photo(codes=[first.name])

        self.assertEqual(first.state, "assigned")
        self.assertTrue(first.delivery_proof)
        self.assertEqual(self._last_slip().outcome, "filed")
        self.assertIn("Approval required", reply)

    def test_a_failing_choice_writes_nothing_and_says_so(self):
        second = self.pickings[1]
        self._say("/entrega")
        self._photo()
        slip = self._last_slip()

        def explode(slip, picking, outcome):
            raise RuntimeError("boom")

        with (
            patch.object(type(self.Slip), "_done", explode),
            self.assertLogs(
                "odoo.addons.stock_fleet_telegram.models.telegram_handler", "ERROR"
            ),
        ):
            reply = self._press(f"ent:p:{slip.id}:{second.id}")

        self.assertIn("Something went wrong", reply)
        self.assertEqual(second.state, "assigned")
        self.assertFalse(second.delivery_proof)
        self.assertFalse(second.message_ids.attachment_ids)
        self.assertEqual(
            (slip.state, slip.picking_id), ("pending", self.env["stock.picking"])
        )

    def test_an_image_odoo_cannot_read_is_refused(self):
        first = self.pickings[0]
        self._say("/entrega")
        reply = self._document("image/png", b"not an image", codes=[first.name])

        self.assertFalse(first.delivery_proof)
        self.assertEqual(first.state, "assigned")
        self.assertEqual(self._last_slip().state, "error")
        self.assertIn("could not read", reply)
        self.assertEqual(self._chat().flow_owner, "telegram.handler.stock_fleet")

    def test_a_format_it_cannot_file_is_asked_again(self):
        self._say("/entrega")
        reply = self._document("image/heic", b"heic", codes=[self.pickings[0].name])
        self.assertIn("as a photo or a PDF", reply)
        self.assertFalse(self._last_slip())

    def test_a_pdf_slip_is_filed_as_its_first_page(self):
        first = self.pickings[0]
        self._say("/entrega")
        self._document("application/pdf", _pdf(3), codes=[first.name])

        self.assertEqual(first.state, "done")
        self.assertTrue(first.delivery_proof)
        self.assertEqual(
            first.message_ids.attachment_ids.mapped("name"), ["remision.pdf"]
        )

    def test_the_answer_speaks_the_chats_language(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"]._load_module_terms(
            ["stock_fleet_telegram"], ["es_MX"]
        )
        self.test_bot.write({"lang": "es_MX", "answer_in_bot_lang": True})
        first = self.pickings[0]
        self._say("/entrega")
        reply = self._photo(codes=[first.name])

        self.assertIn("la validé", reply)

    def test_a_rejected_photo_is_replaced_from_the_pending_list(self):
        first = self.pickings[0]
        self._say("/entrega")
        self._photo(codes=[first.name])
        rejected = first.delivery_proof
        first.with_user(self.reviewer).delivery_proof_ok = False

        self._photo()
        slip = self._last_slip()
        self.assertIn(first, slip.candidate_ids, "A rejected slip is pending again.")
        self._press(f"ent:p:{slip.id}:{first.id}")

        self.assertNotEqual(first.delivery_proof, rejected)
        self.assertTrue(first.delivery_proof_ok)
        self.assertEqual(slip.outcome, "filed")

    def test_a_delivery_signed_on_screen_takes_no_photo_from_the_office(self):
        first = self.pickings[0]
        first.signature = base64.b64encode(_png(11))
        self._say("/entrega", chat=OFFICE_CHAT)
        reply = self._photo(codes=[first.name], chat=OFFICE_CHAT)

        self.assertFalse(first.delivery_proof)
        self.assertIn("already has the customer's signature", reply)

    def test_several_codes_offer_their_deliveries(self):
        self._say("/entrega", chat=OFFICE_CHAT)
        reply = self._photo(codes=self.pickings.mapped("name"), chat=OFFICE_CHAT)

        self.assertIn("Which one", reply)
        self.assertEqual(self._last_slip(OFFICE_CHAT).candidate_ids, self.pickings)

    def test_a_button_of_a_resolved_slip_is_no_longer_valid(self):
        second = self.pickings[1]
        self._say("/entrega")
        self._photo()
        slip = self._last_slip()
        self._press(f"ent:p:{slip.id}:{second.id}")

        reply = self._press(f"ent:p:{slip.id}:{second.id}")

        self.assertIn("no longer valid", reply)

    def test_the_same_bytes_under_another_id_are_not_filed_twice(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        self._photo(codes=[first.name], chat=OFFICE_CHAT, seed=9, unique="a")
        reply = self._photo(codes=[first.name], chat=OFFICE_CHAT, seed=9, unique="b")

        self.assertIn("same file was already filed", reply)

    def test_the_driver_takes_over_the_paper_the_office_had_not_handed_in(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        self._photo(codes=[first.name], chat=OFFICE_CHAT)
        office_slip = self._last_slip(OFFICE_CHAT)
        self.assertTrue(office_slip.receipt_id)

        self._say("/entrega")
        self._photo(codes=[first.name])

        self.assertFalse(office_slip.receipt_id)
        self.assertTrue(self._last_slip().receipt_id)

    def test_a_paper_already_handed_in_stays_where_it_is(self):
        first = self.pickings[0]
        self._say("/entrega", chat=OFFICE_CHAT)
        self._photo(codes=[first.name], chat=OFFICE_CHAT)
        self._press("ent:fin", chat=OFFICE_CHAT)

        self._say("/entrega")
        reply = self._photo(codes=[first.name])

        self.assertEqual(first.state, "done")
        self.assertFalse(self._last_slip().receipt_id)
        self.assertIn("already awaits its paper from Office", reply)
        self.assertIn("with the signed slip it already had", reply)
