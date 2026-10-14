from odoo.exceptions import UserError


def check_company_unchanged(records, vals) -> None:
    if "company_id" not in vals:
        return
    if any(record.company_id.id != vals["company_id"] for record in records):
        raise UserError(
            records.env._(
                "Changing the company of this record is forbidden at this point, you should rather archive it and create a new one."
            )
        )
