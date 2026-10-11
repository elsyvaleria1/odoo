from lxml import etree

import odoo.tests


@odoo.tests.tagged("-at_install", "post_install")
class TestUi(odoo.tests.HttpCase):
    def test_set_defaults(self):
        website_field = self.env["res.partner"]._fields["website"]
        self.assertFalse(website_field.readonly)
        action_context = self.env["ir.actions.actions"]._eval_action_context(
            self.env.ref("partner.action_partner").context
        )
        self.assertNotIn("default_website", action_context)
        self.assertTrue(action_context.get("default_is_company"))
        self.env["ir.default"].search(
            [
                ("field_id", "=", self.env.ref("base.field_res_partner__website").id),
            ]
        ).unlink()
        self.assertFalse(
            self.env["res.partner"].with_context(**action_context).new().website
        )

        self.start_tour("/odoo", "debug_menu_set_defaults", login="admin")

    def test_vat_label_string(self):
        partner = self.env["res.partner"].create({"name": "Jean"})
        partner.get_view()

        self.env.user.company_id.country_id = self.env.ref("base.us")
        self.env.user.company_id.country_id.vat_label = "TVA"
        view = partner.get_view()

        arch = etree.fromstring(view["arch"])
        for node in arch.iterfind(".//field[@name='vat']"):
            self.assertEqual(node.get("string"), "TVA")
        for node in arch.iterfind(".//label[@for='vat']"):
            self.assertEqual(node.get("string"), "TVA")
