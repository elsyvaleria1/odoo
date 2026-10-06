from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPayrollCopyTranslations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_MX")
        cls.structure_type = cls.env["hr.payroll.structure.type"].create(
            {"name": "Copy Translations Type"}
        )

    def _assert_every_language_is_marked(self, record, english, spanish):
        record.with_context(lang="es_MX").name = spanish
        copy = record.copy()
        self.env.flush_all()
        self.assertEqual(copy.name, f"{english} (copy)")
        in_spanish = copy.with_context(lang="es_MX")
        self.assertEqual(in_spanish.name, in_spanish.env._("%s (copy)", spanish))

    def test_a_copied_structure_is_marked_in_every_language(self):
        structure = self.env["hr.payroll.structure"].create(
            {"name": "Regular Pay", "type_id": self.structure_type.id}
        )
        self._assert_every_language_is_marked(structure, "Regular Pay", "Nómina")

    def test_a_copied_rule_is_marked_in_every_language(self):
        structure = self.env["hr.payroll.structure"].create(
            {"name": "Rule Holder", "type_id": self.structure_type.id}
        )
        rule = self.env["hr.salary.rule"].create(
            {
                "name": "Overtime",
                "code": "COPYTR",
                "category_id": self.env.ref("hr_payroll.ALW").id,
                "struct_id": structure.id,
            }
        )
        self._assert_every_language_is_marked(rule, "Overtime", "Horas extra")

    def test_a_copied_category_is_marked_in_every_language(self):
        category = self.env["hr.salary.rule.category"].create(
            {"name": "Bonuses", "code": "COPYTRCAT"}
        )
        self._assert_every_language_is_marked(category, "Bonuses", "Bonos")
