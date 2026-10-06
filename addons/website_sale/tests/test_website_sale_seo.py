import re

from odoo.fields import Command
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase

from odoo.addons.website_sale.tests.common import WebsiteSaleCommon


class WebsiteSaleSEO(HttpCase, WebsiteSaleCommon):
    def test_website_sale_user_designer_can_edit_seo(self):
        public_categ = self.env["product.public.category"].create(
            {"name": "Website Category"}
        )
        self.product.write({"public_categ_ids": [Command.link(public_categ.id)]})
        internal_user = self.env["res.users"].create(
            {
                "name": "Web Designer",
                "login": "internal_user",
                "group_ids": [
                    Command.link(self.ref("website.group_website_designer")),
                    Command.link(self.ref("base.group_user")),
                ],
            }
        )
        self.authenticate(internal_user.login, internal_user.login)
        res = self.call_jsonrpc(
            "/website/get_seo_data",
            {"res_id": public_categ.id, "res_model": "product.public.category"},
        )
        self.assertTrue(res["can_edit_seo"])


class TestOrganizationMarkup(HttpCase, WebsiteSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.website.company_id
        cls.page = cls.env["website.page"].create(
            {
                "url": "/organization_markup",
                "name": "Organization Markup",
                "type": "qweb",
                "arch": '<t t-name="website_sale.organization_markup">'
                '<t t-call="website.layout"><div id="wrap"/></t></t>',
                "key": "website_sale.organization_markup",
                "is_published": True,
                "website_id": cls.website.id,
            }
        )

    def _get_organization_markup(self):
        html = self.url_open(self.page.url).text
        markups = [
            markup
            for script in re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html,
                re.DOTALL,
            )
            if isinstance(markup := json_loads(script), dict)
            and markup.get("@type") == "Organization"
        ]
        self.assertEqual(len(markups), 1)
        return markups[0]

    def test_organization_markup_prints_the_company_name_as_written(self):
        self.assertEqual(self._get_organization_markup()["name"], self.company.name)

        self.company.name = 'Renamed & "Quoted" <Co>'
        self.assertEqual(
            self._get_organization_markup()["name"], 'Renamed & "Quoted" <Co>'
        )

        self.company.partner_id.name = "Renamed through its partner"
        self.assertEqual(
            self._get_organization_markup()["name"], "Renamed through its partner"
        )
