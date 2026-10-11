from odoo.libs.sql.builder import SQL
from odoo.tests import TransactionCase, tagged

from odoo.addons.integration.tools.exchange_queue import keep_rows


@tagged("at_install", "-post_install")
class TestRowsOfARolledBackTransaction(TransactionCase):
    def _kept(self, url):
        with self.registry.cursor() as cr:
            cr.execute(
                SQL(
                    "SELECT company_id, channel_id, user_id FROM integration_exchange"
                    " WHERE request_url = %s",
                    url,
                )
            )
            return cr.fetchall()

    def _forget(self, url):
        with self.registry.cursor() as cr:
            cr.execute(
                SQL("DELETE FROM integration_exchange WHERE request_url = %s", url)
            )

    def _gone(self, model):
        self.env.cr.execute(
            SQL(
                "SELECT COALESCE(MAX(id), 0) + 1000 FROM %s",
                SQL.identifier(self.env[model]._table),
            )
        )
        return self.env.cr.fetchone()[0]

    def test_a_row_naming_records_the_rollback_took_away_is_kept_without_them(self):
        admin = self.env.ref("base.user_admin")
        service = self._gone("integration.service")
        url = "https://example.com/rolled-back"
        self.addCleanup(self._forget, url)

        keep_rows(
            self.registry,
            [
                {
                    "direction": "outbound",
                    "request_url": url,
                    "channel_id": f"integration.service,{service}",
                    "company_id": self._gone("res.company"),
                    "connection_id": self._gone("integration.connection"),
                    "user_id": admin.id,
                }
            ],
        )

        self.assertEqual(
            self._kept(url), [(None, f"integration.service,{service}", admin.id)]
        )

    def test_a_row_naming_lasting_records_keeps_them(self):
        admin = self.env.ref("base.user_admin")
        company = self.env.ref("base.main_company")
        url = "https://example.com/lasting"
        self.addCleanup(self._forget, url)

        keep_rows(
            self.registry,
            [
                {
                    "direction": "inbound",
                    "request_url": url,
                    "channel_id": f"integration.service,{self._gone('integration.service')}",
                    "company_id": company.id,
                    "user_id": admin.id,
                }
            ],
        )

        self.assertEqual(self._kept(url)[0][::2], (company.id, admin.id))
