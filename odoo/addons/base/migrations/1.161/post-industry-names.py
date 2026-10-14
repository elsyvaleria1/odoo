import logging

from odoo.tools import SQL

_logger = logging.getLogger(__name__)

FULL_NAMES = {
    "res_partner_industry_G": (
        "G - WHOLESALE AND RETAIL TRADE; REPAIR OF MOTOR VEHICLES AND MOTORCYCLES"
    ),
    "res_partner_industry_T": (
        "T - ACTIVITIES OF HOUSEHOLDS AS EMPLOYERS; UNDIFFERENTIATED GOODS- AND "
        "SERVICES-PRODUCING ACTIVITIES OF HOUSEHOLDS FOR OWN USE"
    ),
}


def migrate(cr, version):
    if not version:
        return
    for name, full_name in FULL_NAMES.items():
        cr.execute(
            SQL(
                """
                UPDATE res_partner_industry industry
                   SET full_name = jsonb_set(
                           industry.full_name, '{en_US}', to_jsonb(%(full_name)s::text)
                       )
                  FROM ir_model_data data
                 WHERE data.module = 'base'
                   AND data.name = %(name)s
                   AND data.model = 'res.partner.industry'
                   AND data.res_id = industry.id
                   AND industry.full_name->>'en_US' <> %(full_name)s
                   AND regexp_replace(industry.full_name->>'en_US', '\\s+', ' ', 'g')
                       = %(full_name)s
                """,
                full_name=full_name,
                name=name,
            )
        )
        if cr.rowcount:
            _logger.info(
                "Unwrapped the full name of base.%s, broken over two lines by a "
                "reformat of its data file",
                name,
            )
