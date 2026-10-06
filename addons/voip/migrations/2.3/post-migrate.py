from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    # upstream's AI call features kept a transcript and a summary on the call;
    # the recording's own words and the chatter keep them now
    cr.execute("UPDATE phone_call SET channel = 'softphone' WHERE channel IS NULL")
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["phone.call"]._absorb_retired_transcripts()
