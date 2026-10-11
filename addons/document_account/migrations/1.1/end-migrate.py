import io
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.pdf import PdfReader, PdfReadError

_logger = logging.getLogger(__name__)


def _printed_by_odoo(attachment) -> bool:
    if not (raw := attachment.raw):
        return False
    try:
        metadata = PdfReader(io.BytesIO(raw), strict=False).metadata
    except PdfReadError:
        _logger.warning("unreadable PDF %s is filed as issued", attachment.id)
        return False
    return bool(metadata) and metadata.get("/Creator") == "Odoo"


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    attachments = env["ir.attachment"].search(
        [
            ("res_model", "=", "account.bank.statement"),
            ("res_field", "=", False),
            ("mimetype", "=", "application/pdf"),
        ]
    )
    statement_ids = set(
        env["account.bank.statement"]
        .browse(set(attachments.mapped("res_id")))
        .exists()
        .ids
    )
    for res_id, statement_attachments in attachments.grouped("res_id").items():
        if res_id not in statement_ids:
            continue
        bank_issued = statement_attachments.filtered(
            lambda attachment: not _printed_by_odoo(attachment)
        )
        if bank_issued:
            bank_issued._create_document("account.bank.statement", res_id)
