from odoo.modules import neutralize
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "neutralize")
class TestMailNeutralize(TransactionCase):
    def test_a_neutralized_copy_fetches_no_preview_and_offers_no_ice_host(self):
        self.env["mail.ice.server"].create({"uri": "turn.production.example.com"})
        self.env.flush_all()
        for query in neutralize.get_neutralization_queries(["mail"]):
            self.env.cr.execute(query)
        self.env.invalidate_all()
        self.env.registry.clear_cache("stable")
        self.assertFalse(self.env["mail.link.preview"]._is_link_preview_enabled())
        self.assertFalse(self.env["mail.ice.server"].sudo().search([]))
