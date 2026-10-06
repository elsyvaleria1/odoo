import base64

from odoo.tests.common import TransactionCase, new_test_user


class TestSepomexImportWizard(TransactionCase):
    def test_an_administrator_imports_the_catalogue_through_the_privilege(self) -> None:
        admin = new_test_user(
            self.env, login="sepomex_admin", groups="base.group_system"
        )
        header = (
            "d_codigo|d_asenta|d_tipo_asenta|D_mnpio|d_estado|d_ciudad|d_CP|"
            "c_estado|c_oficina|c_CP|c_tipo_asenta|c_mnpio|id_asenta_cpcons|"
            "d_zona|c_cve_ciudad"
        )
        row = "99971|Wizard|Colonia|X|Sinaloa||80001|25|80001||09|999|0001|Urbano|"
        content = f"Licence line\r\n{header}\r\n{row}".encode("latin-1")
        wizard = (
            self.env["wizard.l10n_mx.postal_code.import"]
            .with_user(admin)
            .create({"sepomex_file": base64.b64encode(content)})
        )
        wizard.action_import()
        self.assertTrue(
            self.env["l10n_mx.postal_code"].search([("code", "=", "99971")])
        )
