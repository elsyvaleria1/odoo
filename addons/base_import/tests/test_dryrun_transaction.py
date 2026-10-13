from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class DryRunLeavesNoTrace(TransactionCase):
    _OPTS = {"has_headers": True, "quoting": '"', "separator": ",", "encoding": "utf-8"}

    def _imp(self, csv, res_model="res.partner"):
        return self.env["base_import.import"].create(
            {
                "res_model": res_model,
                "file": csv,
                "file_type": "text/csv",
                "file_name": "dryrun.csv",
            }
        )

    def test_dryrun_keeps_a_pending_write_made_before_it(self):
        partner = self.env["res.partner"].create({"name": "Before"})
        self.env.flush_all()

        partner.name = "Pending"

        result = self._imp(b"name\nImported Row\n").execute_import(
            ["name"], ["Name"], dict(self._OPTS), dryrun=True
        )
        self.assertFalse(result["messages"])

        self.env.invalidate_all()
        self.assertEqual(
            partner.name,
            "Pending",
            "a dry-run import rolled back a write the caller made before it",
        )

    def test_dryrun_leaves_no_stale_value_in_cache(self):
        partner = self.env["res.partner"].create({"name": "Orig"})
        self.env.flush_all()

        csv = ("id,name\n%d,Updated\n" % partner.id).encode()
        result = self._imp(csv).execute_import(
            [".id", "name"], ["Id", "Name"], dict(self._OPTS), dryrun=True
        )
        self.assertFalse(result["messages"])

        self.assertEqual(
            partner.name,
            "Orig",
            "a dry-run import left the rolled-back value in env.cache",
        )
