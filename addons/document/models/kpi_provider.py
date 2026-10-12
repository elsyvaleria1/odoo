from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, LazyTranslate

_debug = DebugLog(__name__)
_lt = LazyTranslate(__name__)

INBOX_KPI_LABEL = _lt("Inbox")


class KpiProvider(models.AbstractModel):
    _inherit = "kpi.provider"

    @api.model
    def get_documents_kpi_summary(self) -> list[dict]:
        return get_kpi_summary(self.env.cr, self.env.uid)

    @api.model
    def get_kpi_summary(self) -> list[dict]:
        result = super().get_kpi_summary()
        result.extend(self.get_documents_kpi_summary())
        return result


def get_kpi_summary(cr: Any, uid: int) -> list[dict]:
    expected_columns = {
        "document_document.id",
        "document_document.folder_id",
        "document_document.parent_path",
        "document_document.type",
        "document_document.active",
    }

    cr.execute(
        SQL(
            """
        SELECT table_name || '.' || column_name
          FROM information_schema.columns
         WHERE table_name || '.' || column_name IN %(columns)s
    """,
            columns=tuple(expected_columns),
        )
    )
    existing_columns = {x[0] for x in cr.fetchall()}
    if expected_columns - existing_columns:
        _debug.logic("kpi_skipped", reason="module_absent")
        return []

    cr.execute(
        SQL("""
        SELECT document.parent_path
          FROM document_document document
          JOIN ir_model_data imd ON imd.model = 'document.document'
                                AND imd.res_id = document.id
         WHERE imd.module = 'document'
           AND imd.name = 'document_inbox_folder'
           AND document.active
    """)
    )
    row = cr.fetchone()
    if not row:
        _debug.logic("kpi_skipped", reason="no_inbox_folder")
        return []
    (inbox_path,) = row

    cr.execute(
        SQL(
            """
        SELECT COUNT(*)
          FROM document_document document
         WHERE document.type != 'folder'
           AND document.parent_path LIKE (%(inbox_path)s || '%%')
           AND document.active
    """,
            inbox_path=inbox_path,
        )
    )
    (count,) = cr.fetchone()

    cr.execute(
        SQL(
            """
        SELECT partner.lang
          FROM res_users u
          JOIN res_partner partner ON u.partner_id = partner.id
         WHERE u.id = %(uid)s
         LIMIT 1
    """,
            uid=uid,
        )
    )
    row = cr.fetchone()
    lang = (row[0] if row else None) or "en_US"

    _debug.perf.count("kpi_inbox_counted", count=count)
    return [
        {
            "id": "document.inbox",
            "name": INBOX_KPI_LABEL.translate(lang),
            "type": "integer",
            "value": count,
        }
    ]
