from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for website in env["website"].with_context(active_test=False).search([]):
        if key := website._get_held_secret("google_places_api_key"):
            website._set_held_secrets(
                {"address_autocomplete_key": key, "google_places_api_key": False}
            )
