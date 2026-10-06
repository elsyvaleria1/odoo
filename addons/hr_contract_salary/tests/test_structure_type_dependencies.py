from odoo.tests.common import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestStructureTypeDependencies(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_a = cls.env.ref("base.be")
        cls.country_b = cls.env.ref("base.lu")
        cls.company = cls.env["res.company"].create(
            {"name": "Moves abroad", "country_id": cls.country_a.id}
        )
        company_b = cls.env["res.company"].create(
            {"name": "Moves further", "country_id": cls.country_b.id}
        )
        StructureType = cls.env["hr.payroll.structure.type"].with_context(
            allowed_company_ids=(cls.company | company_b).ids
        )
        cls.type_a = StructureType.create({"name": "A", "country_id": cls.country_a.id})
        cls.type_b = StructureType.create({"name": "B", "country_id": cls.country_b.id})
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Moves along", "company_id": cls.company.id}
        )

    def test_structure_type_follows_the_job_template(self):
        template = self.env["hr.version"].create(
            {"name": "Template", "structure_type_id": self.type_a.id}
        )
        job = self.env["hr.job"].create(
            {"name": "Templated", "contract_template_id": template.id}
        )
        version = self.employee.version_id
        version.job_id = job
        template.structure_type_id = self.type_b
        self.assertEqual(version.structure_type_id, self.type_b)
