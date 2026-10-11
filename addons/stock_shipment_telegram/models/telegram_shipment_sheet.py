import hashlib
import logging
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.libs.documents import METERED
from odoo.libs.documents.document import Document
from odoo.tools import frozendict

from odoo.addons.extract.tools import run as extract

_logger = logging.getLogger(__name__)

OUT_LOOKBACK = timedelta(days=14)
IN_LOOKBACK = timedelta(days=30)


class SheetRefused(Exception):
    pass


class TelegramShipmentSheet(models.Model):

    _name = "telegram.shipment.sheet"
    _description = "Telegram Shipping Order"
    _order = "id desc"
    _rec_name = "tracking_ref"
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
            ("pending", "To Assign"),
            ("done", "Assigned"),
            ("error", "Refused"),
        ],
        default="pending",
        required=True,
    )
    tracking_ref = fields.Char(
        string="Tracking Number",
        index="btree_not_null",
    )
    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        ondelete="set null",
    )
    extracted = fields.Json(
        help="What was read off the sheet: route, service, date and amounts.",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Transfer",
        index="btree_not_null",
        ondelete="set null",
    )
    candidate_ids = fields.Many2many(
        comodel_name="stock.picking",
        relation="telegram_shipment_sheet_candidate_rel",
        string="Offered Transfers",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="picking_id.company_id",
    )
    file_id = fields.Char(help="Telegram's id to download the file.")
    file_name = fields.Char()
    file_unique_id = fields.Char(index="btree_not_null")
    checksum = fields.Char(
        index="btree_not_null",
        help="SHA-1 of the file's bytes: the same sheet sent again is recognised.",
    )
    error_message = fields.Char()

    @api.model
    def _find_resent(self, chat, file_unique_id):
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

    def _checksum_seen(self, content):
        self.check_singleton()
        self.checksum = hashlib.sha1(content).hexdigest()
        return self.search(
            [
                ("checksum", "=", self.checksum),
                ("state", "=", "done"),
                ("id", "!=", self.id),
            ],
            limit=1,
        )

    def _read_sheet(self, content) -> dict:
        self.check_singleton()
        document = Document(content, name=self.file_name or "sheet", read_up_to=METERED)
        try:
            return extract(document, "shipping_order", self.env, up_to=METERED).flat()
        except Exception:
            _logger.warning("Could not read shipping order %s", self.id, exc_info=True)
            return {}

    def _recognise(self, content) -> None:
        values = self._read_sheet(content)
        reference = (values.get("tracking_ref") or "").strip().upper()
        if not reference:
            raise SheetRefused(
                self.env._(
                    "I could not read the tracking number. Send the sheet again, "
                    "whole and in focus, with the barcode in view."
                )
            )
        carrier = (
            self.env["delivery.carrier"]
            .search([("tracking_ref_pattern", "!=", False)])
            .filtered(lambda c: re.fullmatch(c.tracking_ref_pattern, reference))[:1]
        )
        if not carrier:
            raise SheetRefused(
                self.env._(
                    "No carrier uses tracking numbers like %(ref)s.", ref=reference
                )
            )
        self.write(
            {
                "tracking_ref": reference,
                "carrier_id": carrier.id,
                "extracted": {
                    key: str(value) if key == "date" else value
                    for key, value in values.items()
                    if key != "tracking_ref" and value is not None
                },
            }
        )

    def _candidates(self, incoming=False, digits=None):
        self.check_singleton()
        lookback = IN_LOOKBACK if incoming else OUT_LOOKBACK
        domain = [
            ("picking_type_code", "=", "incoming" if incoming else "outgoing"),
            ("state", "!=", "cancel"),
            ("create_date", ">=", fields.Datetime.now() - lookback),
            "|",
            ("carrier_tracking_ref", "=", False),
            ("carrier_tracking_ref", "=ilike", self.tracking_ref),
        ]
        if not incoming:
            domain += [("carrier_id", "in", [self.carrier_id.id, False])]
        if digits:
            domain += [("name", "=like", f"%{digits}")]
        pickings = self.env["stock.picking"].search(domain, order="create_date desc")
        return pickings.sorted(
            lambda picking: (picking.carrier_tracking_ref or "") != self.tracking_ref
        )

    def _more_candidates(self, digits=None):
        self.check_singleton()
        incoming = self.picking_id.picking_type_code == "incoming"
        return self._candidates(incoming=incoming, digits=digits).filtered(
            lambda picking: (
                (picking.carrier_tracking_ref or "").strip().upper()
                != self.tracking_ref
            )
        )

    def _sibling(self):
        self.check_singleton()
        return self.create(
            {
                "bot_id": self.bot_id.id,
                "chat_id": self.chat_id.id,
                "tracking_ref": self.tracking_ref,
                "carrier_id": self.carrier_id.id,
                "extracted": self.extracted,
                "file_id": self.file_id,
                "file_name": self.file_name,
                "file_unique_id": self.file_unique_id,
                "checksum": self.checksum,
            }
        )

    def _assign(self, picking, content) -> list:
        self.check_singleton()
        current = (picking.carrier_tracking_ref or "").strip().upper()
        if current and current != self.tracking_ref:
            raise SheetRefused(
                self.env._(
                    "%(picking)s already carries tracking number %(other)s; I do "
                    "not write over it.",
                    picking=picking.name,
                    other=current,
                )
            )
        picking.write(
            {
                "carrier_id": self.carrier_id.id,
                "carrier_tracking_ref": self.tracking_ref,
            }
        )
        company_lang = picking.company_id.partner_id.lang
        picking.with_context(lang=company_lang).message_post(
            body=picking.with_context(lang=company_lang).env._(
                "Shipping order %(ref)s of %(carrier)s, sent over Telegram.",
                ref=self.tracking_ref,
                carrier=self.carrier_id.name,
            ),
            attachments=[(self._attachment_name(), content)],
        )
        self.write({"state": "done", "picking_id": picking.id, "error_message": False})
        return self._on_shipment_sheet_assigned(content)

    def _attachment_name(self) -> str:
        extension = (self.file_name or "").rpartition(".")[2] or "jpg"
        return f"hoja_embarque_{self.tracking_ref}.{extension}"

    def _on_shipment_sheet_assigned(self, content) -> list:
        return []

    def _refuse(self, reason) -> None:
        self.write({"state": "error", "error_message": reason})
