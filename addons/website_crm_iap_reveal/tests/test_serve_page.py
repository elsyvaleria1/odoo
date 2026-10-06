from unittest.mock import PropertyMock, patch

from odoo.http.geoip import GeoIP
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestRevealServePage(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["crm.reveal.rule"].search([]).active = False
        cls.env["crm.reveal.view"].search([]).unlink()
        belgium = cls.env.ref("base.be")
        cls.rules = cls.env["crm.reveal.rule"].create(
            [
                {"name": "Reveal A", "country_ids": [(6, 0, belgium.ids)]},
                {"name": "Reveal B", "country_ids": [(6, 0, belgium.ids)]},
            ]
        )
        cls.page = cls.env["website.page"].create(
            {
                "url": "/reveal-page",
                "name": "Reveal page",
                "type": "qweb",
                "arch": '<t t-name="website_crm_iap_reveal.reveal_page">'
                '<t t-call="website.layout"><div id="wrap"/></t></t>',
                "key": "website_crm_iap_reveal.reveal_page",
                "is_published": True,
                "website_id": cls.env["website"].search([], limit=1).id,
            }
        )

    def _open_from(self, country_code):
        with patch.object(
            GeoIP, "country_code", new_callable=PropertyMock, return_value=country_code
        ):
            return self.url_open(self.page.url)

    def test_a_view_matching_two_rules_records_both(self):
        for readonly_enabled in (True, False):
            self.set_registry_readonly_mode(readonly_enabled)
            with self.subTest(readonly_enabled=readonly_enabled):
                self.env["crm.reveal.view"].search([]).unlink()
                self.opener.cookies.clear()
                response = self._open_from("BE")
                self.assertEqual(response.status_code, 200)
                views = self.env["crm.reveal.view"].search([])
                self.assertEqual(views.reveal_rule_id, self.rules)

                views.unlink()
                self.assertEqual(self._open_from("BE").status_code, 200)
                self.assertFalse(
                    self.env["crm.reveal.view"].search([]),
                    "the rule_ids cookie excludes the rules this visitor matched",
                )

    def test_a_view_from_a_country_no_rule_targets_records_nothing(self):
        response = self._open_from("FR")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.env["crm.reveal.view"].search([]))
        self.assertNotIn("rule_ids", response.cookies)
