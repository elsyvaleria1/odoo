"""Pre-migration to 1.7: versioned log hashes, SMS codes kept only as hashes.

- ``sign.log.hash_version``: every entry written so far is version 1 and keeps
  verifying as it was hashed; the column is created here, before the ORM would
  fill it with the default (version 2) for existing rows.
- ``sign.log.token``: the signer's raw link token, which nothing read, goes.
- ``sign.request.item.sms_token``: a code still pending is void (the signer asks
  for a new one); a signer who signed with a code is recorded as having verified
  the phone, the number the code went to, on the signing date, which the
  certificate of completion prints.
"""

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
