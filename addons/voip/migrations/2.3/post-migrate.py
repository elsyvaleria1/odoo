from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE phone_call SET channel = 'softphone' WHERE channel IS NULL")
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["phone.call"]._absorb_retired_transcripts()
