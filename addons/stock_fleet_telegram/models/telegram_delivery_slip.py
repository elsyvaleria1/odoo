import base64
import hashlib
import logging
import mimetypes

from odoo import api, fields, models
from odoo.exceptions import AccessError, RedirectWarning, UserError, ValidationError
from odoo.libs import json
from odoo.libs.documents import METERED
from odoo.libs.documents.document import Document
from odoo.tools import frozendict

from .stock_picking import out_names_in_text
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.llm_providers import get_provider

_logger = logging.getLogger(__name__)

# The model that reads the slip when no code and no printed text identify it;
# any model the ai module lists works, with the provider key set in Settings > AI.
_LLM_MODEL_PARAM = "stock_fleet_telegram.llm_model"
_LLM_MODEL_DEFAULT = "gpt-4.1-mini"
_LLM_PURPOSE = "telegram.delivery_slip"
_READ_SYSTEM_PROMPT = (
    "You read scanned or photographed delivery slips that a customer has "
    "signed. Extract the delivery order number, the customer's name and the "
    "customer's RFC exactly as printed. The delivery order number is printed "
    "as a warehouse code, OUT and numbers separated by slashes, such as "
    "CDG/OUT/25/07/0123. The customer is who the goods are delivered to, not "
    "the company that issued the slip. Leave a field empty when it is not "
    "legible."
)
_READ_USER_PROMPT = "Read the delivery order number, customer name and customer RFC."
_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "delivery_order": {"type": "string"},
        "customer_name": {"type": "string"},
        "customer_rfc": {"type": "string"},
    },
    "required": ["delivery_order", "customer_name", "customer_rfc"],
    "additionalProperties": False,
}


class SlipRefused(Exception):
    pass


class TelegramDeliverySlip(models.Model):
    _name = "telegram.delivery.slip"
    _description = "Telegram Delivery Slip"
    _order = "id desc"
    _rec_name = "picking_id"
    _access_anchors = frozendict({"partner": "chat_id.account_id.partner_id"})

    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        required=True,
        ondelete="cascade",
    )
    chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        index=True,
        required=True,
        ondelete="cascade",
    )
    state = fields.Selection(
        selection=[
            ("pending", "To Identify"),
            ("done", "Recorded"),
            ("error", "Refused"),
        ],
        default="pending",
        required=True,
    )
    outcome = fields.Selection(
        selection=[
            ("delivered", "Delivered"),
            ("filed", "Slip Filed"),
        ],
        help="Delivered: the bot validated the delivery order with the slip. "
        "Slip Filed: the slip is on it, and whoever validates it no longer "
        "lacks it.",
    )
    found_by = fields.Selection(
        selection=[
            ("qr", "Signed QR code"),
            ("code", "Code on the slip"),
            ("text", "Number and customer printed"),
            ("model", "Number and customer read by the model"),
            ("choice", "Chosen by the sender"),
        ],
        help="How the delivery order was found on the file.",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery Order",
        index="btree_not_null",
        ondelete="set null",
    )
    candidate_ids = fields.Many2many(
        comodel_name="stock.picking",
        relation="telegram_delivery_slip_candidate_rel",
        string="Offered Delivery Orders",
        help="The delivery orders the sender was offered to choose from: a "
        "button names one of these or none.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="picking_id.partner_id",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="picking_id.company_id",
    )
    file_id = fields.Char(help="Telegram's id to download the file.")
    file_name = fields.Char()
    file_unique_id = fields.Char(
        index="btree_not_null",
        help="Telegram's id for the file's content, the same however many times "
        "it is sent: a file sent again is recognized and not read twice.",
    )
    checksum = fields.Char(
        index="btree_not_null",
        help="SHA-1 of the file's bytes: the same photo sent again from the "
        "gallery gets a new Telegram id but the same checksum.",
    )
    error_message = fields.Char()
    receipt_id = fields.Many2one(
        comodel_name="stock.delivery.slip.receipt",
        string="Receipt Batch",
        index="btree_not_null",
        ondelete="set null",
        help="The batch whose paper administration receives this slip in.",
    )
    date_done = fields.Datetime(
        related="picking_id.date_done",
        string="Validated On",
    )
    origin = fields.Char(
        related="picking_id.origin",
        string="Source Document",
    )

    @api.model
    def _find_resent(self, chat, file_unique_id) -> TelegramDeliverySlip:
        if not file_unique_id:
            return self.browse()
        return self.search(
            [
                ("chat_id", "=", chat.id),
                ("file_unique_id", "=", file_unique_id),
                ("state", "=", "done"),
            ],
            limit=1,
        )

    def _identify(self, content, pending):
        self.check_singleton()
        Picking = self.env["stock.picking"]
        document = Document(content, name=self.file_name or "slip")
        codes = self._read(document, "barcodes", [])
        found = Picking._find_by_delivery_slip_qr(codes)
        if len(found) == 1:
            return found, "qr", Picking
        if found:
            return Picking, "", found
        found = Picking._find_delivery_orders_by_name(codes)
        if len(found) == 1:
            return found, "code", Picking
        if found:
            return Picking, "", found

        text = self._read(
            Document(content, name=self.file_name or "slip", read_up_to=METERED),
            "text",
            "",
        )
        found = Picking._find_delivery_orders_by_name(out_names_in_text(text))
        named = found.filtered(lambda picking: picking._customer_in_text(text))
        if len(named) == 1:
            return named, "text", Picking
        if named:
            return Picking, "", named

        reading = self._read_with_model(content)
        found = Picking._find_delivery_orders_by_name(
            out_names_in_text(reading.get("delivery_order"))
        )
        if len(found) == 1 and found._customer_matches(
            reading.get("customer_name"), reading.get("customer_rfc")
        ):
            return found, "model", Picking
        return Picking, "", pending()

    def _read_with_model(self, content) -> dict:
        model = (
            self.env["ir.config_parameter"]
            .with_privilege(
                "stock_fleet_telegram.privilege_read_delivery_slips",
                reason="a Telegram upload reads which model reads its slips",
            )
            .get_param(_LLM_MODEL_PARAM, _LLM_MODEL_DEFAULT)
        )
        mimetype = mimetypes.guess_type(self.file_name or "")[0] or "image/jpeg"
        try:
            service = LLMApiService(
                self.env, get_provider(self.env, model), purpose=_LLM_PURPOSE
            )
            responses = service.request_llm(
                model,
                [_READ_SYSTEM_PROMPT],
                [_READ_USER_PROMPT],
                files=[
                    {
                        "mimetype": mimetype,
                        "value": base64.b64encode(content).decode(),
                        "file_ref": "<file_#1>",
                    }
                ],
                schema=_READ_SCHEMA,
                temperature=0,
            )
            reading = json.loads(responses[-1]) if responses else {}
        except Exception:
            _logger.warning(
                "Could not read %s with %s", self.file_name, model, exc_info=True
            )
            return {}
        return {key: (value or "").strip() for key, value in reading.items()}

    def _read(self, document, representation, empty):
        try:
            return getattr(document, representation) or empty
        except Exception:
            _logger.warning(
                "Could not read %s off %s",
                representation,
                self.file_name,
                exc_info=True,
            )
            return empty

    def _offer(self, candidates) -> None:
        self.write({"candidate_ids": [fields.Command.set(candidates.ids)]})

    def _record(self, picking, found_by, content) -> str:
        self.check_singleton()
        self.write({"picking_id": picking.id, "found_by": found_by})
        blocker = (
            picking._telegram_delivery_blocker(self.env.user)
            if picking.state == "assigned"
            else ""
        )
        self._check_takes_slip(picking, blocker)
        filed = not (picking.delivery_proof and picking.delivery_proof_ok)
        if filed:
            self._file_proof(picking, content)
        company_lang = picking.company_id.partner_id.lang
        picking.with_context(lang=company_lang).message_post(
            body=picking.with_context(lang=company_lang).env._(
                "Signed delivery slip received through Telegram."
            ),
            attachments=[(self.file_name or "slip", content)],
        )
        reason = blocker
        delivered = False
        if picking.state == "assigned" and not blocker:
            reason = self._deliver(picking)
            delivered = not reason
        awaiting = self._done(picking, "delivered" if delivered else "filed")
        text = self._recorded_message(picking, delivered, filed, reason)
        if awaiting:
            text += " " + self.env._(
                "Administration already awaits its paper from %(user)s.",
                user=awaiting.delivered_by_id.name or "-",
            )
        return text

    def _file_proof(self, picking, content) -> None:
        try:
            picking.delivery_proof = base64.b64encode(self._proof_image(content))
        except UserError as error:
            _logger.info("Undecodable delivery slip %s: %s", self.file_name, error)
            raise SlipRefused(
                self.env._(
                    "I could not read %(file)s as an image; send it as a photo.",
                    file=self.file_name or self.env._("the file"),
                )
            ) from error

    def _check_takes_slip(self, picking, blocker) -> None:
        if picking.picking_type_code != "outgoing":
            raise SlipRefused(
                self.env._("%(picking)s is not a delivery.", picking=picking.name)
            )
        if picking.state not in ("assigned", "done"):
            raise SlipRefused(
                self.env._(
                    "%(picking)s is not ready to deliver: the step before it has "
                    "not been validated in the warehouse.",
                    picking=picking.name,
                )
            )
        if picking.delivery_paper_received:
            raise SlipRefused(
                self.env._(
                    "Administration already received the signed paper of "
                    "%(picking)s; I did not file the photo.",
                    picking=picking.name,
                )
            )
        if picking.delivery_proof_ok and (picking.state == "done" or blocker):
            values = {
                "picking": picking.name,
                "user": picking.delivery_proof_uid.name or "-",
            }
            message = (
                self.env._(
                    "%(picking)s already has its signed slip, from %(user)s; I "
                    "did not file the photo.",
                    **values,
                )
                if picking.delivery_proof
                else self.env._(
                    "%(picking)s already has the customer's signature, from "
                    "%(user)s; I did not file the photo.",
                    **values,
                )
            )
            if blocker:
                message += " " + self.env._(
                    "It is still to be validated: %(reason)s.", reason=blocker
                )
            raise SlipRefused(message)

    def _deliver(self, picking) -> str:
        try:
            with self.env.cr.savepoint():
                picking.action_deliver()
                if picking.state != "done":
                    raise UserError(
                        self.env._(
                            "it needs an answer only Odoo asks; validate it there"
                        )
                    )
        except (UserError, RedirectWarning, ValidationError, AccessError) as error:
            return str(error.args[0] if error.args else error)
        return ""

    def _recorded_message(self, picking, delivered, filed, reason) -> str:
        values = {
            "picking": picking.name,
            "partner": picking.partner_id.display_name or "",
        }
        if delivered and filed:
            text = self.env._(
                "%(picking)s (%(partner)s) delivered: I validated it and filed the "
                "signed slip on it.",
                **values,
            )
        elif delivered:
            text = self.env._(
                "%(picking)s (%(partner)s) delivered: I validated it with the "
                "signed slip it already had.",
                **values,
            )
        elif picking.state == "done":
            text = self.env._("%(picking)s (%(partner)s): signed slip filed.", **values)
        else:
            text = self.env._(
                "%(picking)s (%(partner)s): signed slip filed. It is still to be "
                "validated: %(reason)s.",
                reason=reason,
                **values,
            )
        due = picking.state == "done" and picking._get_delivery_paper_due_date()
        if due:
            text += " " + self.env._(
                "Hand the paper in by %(due)s.", due=due.strftime("%d/%m/%Y")
            )
        return text

    def _done(self, picking, outcome):
        Receipt = self.env["stock.delivery.slip.receipt"]
        earlier = self.search(
            [
                ("picking_id", "=", picking.id),
                ("id", "!=", self.id),
                ("receipt_id.state", "in", ("draft", "submitted")),
            ]
        )
        awaiting = earlier.receipt_id.filtered(
            lambda receipt: receipt.state == "submitted"
        )[:1]
        earlier.filtered(
            lambda slip: slip.receipt_id.state == "draft"
        ).receipt_id = False
        receipt = Receipt
        if not awaiting:
            receipt = Receipt._get_or_create_open_receipt_for_chat(
                self.chat_id, picking.company_id, self.env.user
            )
        self.write(
            {
                "state": "done",
                "outcome": outcome,
                "receipt_id": receipt.id,
                "candidate_ids": [fields.Command.clear()],
            }
        )
        return awaiting

    @staticmethod
    def _proof_image(content) -> bytes:
        if content[:5] != b"%PDF-":
            return content
        images = Document(content, name="slip.pdf").images
        return images[0] if images else content

    def _refuse(self, message) -> None:
        self.write(
            {
                "state": "error",
                "error_message": message[:255],
                "candidate_ids": [fields.Command.clear()],
            }
        )

    def _checksum_seen(self, content) -> TelegramDeliverySlip:
        self.checksum = hashlib.sha1(content).hexdigest()
        return self.search(
            [
                ("chat_id", "=", self.chat_id.id),
                ("checksum", "=", self.checksum),
                ("id", "!=", self.id),
                ("state", "=", "done"),
            ],
            limit=1,
        )

    def action_open_picking(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }

    def action_remove_from_receipt(self) -> None:
        self.filtered(
            lambda slip: slip.receipt_id.state in ("draft", "submitted")
        ).receipt_id = False
