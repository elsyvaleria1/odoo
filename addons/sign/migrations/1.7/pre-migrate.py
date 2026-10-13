
from odoo.db.schema import column_exists


def migrate(cr, version):
    if not version:
        return
    if not column_exists(cr, "sign_log", "hash_version"):
        cr.execute("ALTER TABLE sign_log ADD COLUMN hash_version integer")
        cr.execute("UPDATE sign_log SET hash_version = 1")
    cr.execute("ALTER TABLE sign_log DROP COLUMN IF EXISTS token")

    if column_exists(cr, "sign_request_item", "sms_token"):
        if not column_exists(cr, "sign_request_item", "sms_verified_date"):
            cr.execute(
                "ALTER TABLE sign_request_item"
                " ADD COLUMN sms_verified_date timestamp without time zone"
            )
        if not column_exists(cr, "sign_request_item", "sms_verified_number"):
            cr.execute(
                "ALTER TABLE sign_request_item ADD COLUMN sms_verified_number varchar"
            )
        cr.execute(
            """
            UPDATE sign_request_item
               SET sms_verified_date = signing_date::timestamp,
                   sms_verified_number = sms_number
             WHERE sms_token IS NOT NULL
               AND state = 'completed'
               AND NOT COALESCE(signed_without_extra_auth, false)
            """
        )
        cr.execute("ALTER TABLE sign_request_item DROP COLUMN sms_token")
