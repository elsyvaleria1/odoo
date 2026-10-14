from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestKpiProvider(TransactionCase):
    def test_only_an_administrator_reads_the_database_s_key_figures(self):
        Provider = self.env["kpi.provider"]
        for login, groups in (
            ("kpi_portal", "base.group_portal"),
            ("kpi_employee", "base.group_user"),
        ):
            user = new_test_user(self.env, login=login, groups=groups)
            with self.subTest(login), self.assertRaises(AccessError):
                Provider.with_user(user).get_kpi_summary()
        admin = new_test_user(self.env, login="kpi_admin", groups="base.group_system")
        self.assertEqual(Provider.with_user(admin).get_kpi_summary(), [])
