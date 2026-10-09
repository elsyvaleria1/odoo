from odoo import tools
from odoo.db.errors import PG_USER_FAULT_EXCEPTIONS
from odoo.exceptions import UserError


def unlink_where_possible(records, delete):
    if not records:
        return records
    try:
        with records.env.cr.savepoint(), tools.mute_logger("odoo.db"):
            delete(records)
    except (UserError, *PG_USER_FAULT_EXCEPTIONS):
        if len(records) == 1:
            return records
        middle = len(records) // 2
        return unlink_where_possible(records[:middle], delete) | (
            unlink_where_possible(records[middle:], delete)
        )
    return records.browse()


def write_and_reorder(records, vals, write):
    reordered = "sequence" in vals and any(
        record.sequence != vals["sequence"] for record in records
    )
    result = write(vals)
    if reordered:
        records.env.flush_all()
        records.env.invalidate_all()
    return result
