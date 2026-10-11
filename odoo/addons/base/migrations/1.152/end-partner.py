from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE phone_number SET country_inferred = country_id IS NULL")
    cr.execute(
        """
        SELECT phone.id, phone.number, phone.sanitized,
               array_agg(
                   partner.country_id
                   ORDER BY NOT partner.active, partner.complete_name, partner.id DESC
               ) FILTER (WHERE partner.country_id IS NOT NULL)
          FROM phone_number AS phone
          JOIN res_partner_phone_number_rel AS rel ON rel.phone_number_id = phone.id
          JOIN res_partner AS partner ON partner.id = rel.partner_id
         WHERE phone.country_id IS NULL
         GROUP BY phone.id
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    Phone, Country = env["phone.number"], env["res.country"]
    pinned: dict[int, int] = {}
    for phone_id, number, sanitized, country_ids in cr.fetchall():
        for country_id in dict.fromkeys(country_ids or ()):
            if Phone._normalize_number(number, Country.browse(country_id)) == sanitized:
                pinned[phone_id] = country_id
                break
    cr.execute(
        """
        UPDATE phone_number AS phone
           SET country_id = pinned.country_id
          FROM unnest(%s::int[], %s::int[]) AS pinned(id, country_id)
         WHERE phone.id = pinned.id
        """,
        (list(pinned), list(pinned.values())),
    )
