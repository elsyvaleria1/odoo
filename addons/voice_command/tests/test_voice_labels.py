from odoo.tests import TransactionCase, new_test_user, tagged

SEARCH = """
<search>
    <filter name="draft" string="Draft" domain="[]"/>
    <filter name="by_country" string="Country" context="{'group_by': 'country_id'}"/>
    <filter name="created" string="Created" date="create_date"/>
    <field name="name"/>
</search>
"""
FORM = """
<form>
    <header>
        <button name="action_view_duplicates" type="object" string="Validate"
            spoken="finish the delivery"/>
    </header>
    <sheet>
        <field name="name"/>
        <field name="email" string="Mail"/>
    </sheet>
</form>
"""


@tagged("post_install", "-at_install")
class TestVoiceLabels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_MX")
        View = cls.env["ir.ui.view"]
        cls.search = View.create(
            {"name": "voice labels search", "model": "res.partner", "arch": SEARCH}
        )
        cls.form = View.create(
            {"name": "voice labels form", "model": "res.partner", "arch": FORM}
        )
        cls.search.update_field_translations(
            "arch_db", {"es_MX": {"Draft": "Borrador", "Country": "País"}}
        )
        cls.form.update_field_translations(
            "arch_db",
            {
                "es_MX": {
                    "Validate": "Validar",
                    "finish the delivery": "termina la entrega",
                    "Mail": "Correo",
                }
            },
        )
        cls.views = [[cls.search.id, "search"], [cls.form.id, "form"]]
        cls.user = new_test_user(cls.env, login="voice_labels", lang="es_MX")

    def _labels(self, lang):
        return (
            self.env["voice.labels"]
            .with_user(self.user)
            .with_context(lang=lang)
            .view_labels("res.partner", self.views)
        )

    def test_a_spanish_user_hears_the_english_label_of_each_term(self):
        english = self._labels("es_MX")["en_US"]
        self.assertEqual(english["filters"], {"draft": "Draft"})
        self.assertEqual(english["group_bys"], {"country_id": "Country"})
        self.assertEqual(english["date_filters"], {"created": "Created"})
        self.assertIn("name", english["search_fields"])
        self.assertEqual(english["form_fields"]["email"], "Mail")
        self.assertEqual(
            english["buttons"],
            {"action_view_duplicates": ["Validate", "finish the delivery"]},
        )

    def test_an_english_user_hears_the_spanish_label_of_each_term(self):
        spanish = self._labels("en_US")["es_MX"]
        self.assertEqual(spanish["filters"], {"draft": "Borrador"})
        self.assertEqual(spanish["group_bys"], {"country_id": "País"})
        self.assertEqual(
            spanish["buttons"],
            {"action_view_duplicates": ["Validar", "termina la entrega"]},
        )

    def test_menus_are_named_in_the_other_languages(self):
        menu = self.env.ref("base.menu_administration")
        menu.update_field_translations("name", {"es_MX": "Ajustes"})
        labels = (
            self.env["voice.labels"]
            .with_user(self.user)
            .with_context(lang="es_MX")
            .menu_labels([menu.id])
        )
        self.assertEqual(labels, {"en_US": {menu.id: "Settings"}})
