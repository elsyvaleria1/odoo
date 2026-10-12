from typing import TYPE_CHECKING

from odoo.tools import SQL

if TYPE_CHECKING:
    from odoo.db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    if not version:
        return
    cr.execute(
        SQL(
            "UPDATE approval_category SET escalate_overdue = TRUE "
            "WHERE escalate_overdue IS NOT TRUE"
        )
    )
