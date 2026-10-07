from odoo.tests import TransactionCase, tagged

from odoo.addons.integration_github.tools import repository_domain

REPOSITORY = "Agro-Marin/odoo"
SHA = "a" * 40


@tagged("post_install", "-at_install")
class TestDeliveryOrder(TransactionCase):
    """GitHub redelivers and reorders: an older word never undoes a newer one."""

    def _pull(self, updated_at, **pr):
        return self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 3,
                "title": "t",
                "state": "open",
                "updated_at": updated_at,
                "head": {"ref": "b", "sha": SHA, "repo": {"full_name": REPOSITORY}},
                **pr,
            },
        )

    def test_a_late_opened_delivery_does_not_reopen_a_merged_pull_request(self):
        self._pull("2026-10-07T10:00:00Z")
        merged = self._pull(
            "2026-10-07T11:00:00Z",
            state="closed",
            merged=True,
            merged_at="2026-10-07T11:00:00Z",
            merge_commit_sha="b" * 40,
        )
        self._pull("2026-10-07T10:30:00Z")
        self.assertEqual(merged.pull_state, "merged")
        self.assertTrue(merged.date_merged)

    def _check(self, **run):
        return self.env["integration.github.check"]._record(
            REPOSITORY,
            "check_run:7",
            {
                "name": "ci",
                "head_sha": SHA,
                "source": "check_run",
                "check_status": run.get("status", "in_progress"),
                "conclusion": run.get("conclusion", False),
                "date_github": run["at"],
            },
        )

    def test_a_late_in_progress_delivery_does_not_undo_a_completed_check(self):
        check = self._check(at="2026-10-07 10:00:00")
        self._check(at="2026-10-07 10:05:00", status="completed", conclusion="success")
        self._check(at="2026-10-07 10:01:00")
        self.assertEqual(
            (check.check_status, check.conclusion), ("completed", "success")
        )

    def test_a_rerun_moves_the_check_forward_again(self):
        check = self._check(
            at="2026-10-07 10:05:00", status="completed", conclusion="failure"
        )
        self._check(at="2026-10-07 11:00:00", status="queued")
        self.assertEqual(check.check_status, "queued")

    def test_a_repository_is_matched_whatever_its_case_and_literally(self):
        Pull = self.env["integration.github.pull"]
        pull = self._pull("2026-10-07T10:00:00Z")
        self.assertEqual(
            Pull.search(repository_domain("repository", "agro-marin/ODOO")), pull
        )
        self.assertFalse(
            Pull.search(repository_domain("repository", "Agro-Marin/od_o"))
        )
        self.assertFalse(Pull.search(repository_domain("repository", "Agro-Marin/%")))
