from odoo.fields import Domain
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.ir_access import reads_only_refs

MODEL = "res.partner.industry"


@tagged("post_install", "-at_install")
class TestFixedRecordDomains(TransactionCase):
    def _row(self, domain):
        return self.env["ir.access"].create(
            {
                "name": "fixed record",
                "model_id": self.env["ir.model"]._get_id(MODEL),
                "group_id": self.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
                "domain": domain,
            }
        )

    def test_a_domain_of_literal_xml_ids_names_fixed_records(self):
        for domain in (
            "[('id', '=', ref('base.res_partner_industry_A'))]",
            "[('id', 'in', [ref('a.b'), ref('c.d')]), ('name', '!=', False)]",
        ):
            with self.subTest(domain=domain):
                self.assertTrue(reads_only_refs(domain))

    def test_a_domain_reading_anything_else_is_not_fixed(self):
        for domain in (
            "",
            "[('name', '!=', False)]",
            "[('id', '=', ref('a.b')), ('create_uid', '=', user.id)]",
            "[('id', '=', ref(xmlid))]",
            "[('id', '=', ref('a.b', True))]",
            "[('id', 'in', company_ids)]",
            "[('id', '=', ref)]",
        ):
            with self.subTest(domain=domain):
                self.assertFalse(reads_only_refs(domain))

    def test_a_fixed_record_domain_resolves_once(self):
        row = self._row("[('id', '=', ref('base.res_partner_industry_A'))]")
        [info] = self.env["ir.access"]._access_infos(row)[MODEL]
        industry = self.env.ref("base.res_partner_industry_A")
        self.assertEqual(info.domain, Domain("id", "=", industry.id))

    def test_an_xml_id_not_loaded_yet_stays_evaluated_per_principal(self):
        domain = "[('id', '=', ref('base.no_such_record'))]"
        row = self._row("[('name', '!=', False)]")
        self.env.cr.execute(
            "UPDATE ir_access SET domain = %s WHERE id = %s", [domain, row.id]
        )
        row.invalidate_recordset(["domain"])
        [info] = self.env["ir.access"]._access_infos(row)[MODEL]
        self.assertEqual(info.domain, domain)
