from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    terms = env["account.payment.term"].with_context(active_test=False).search([])
    env.add_to_compute(terms._fields["is_immediate"], terms)
    env.flush_all()
