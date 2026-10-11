from freezegun import freeze_time

from .test_common import TestQualityCommon
from odoo.addons.spreadsheet_edition.tests.spreadsheet_test_case import (
    SpreadsheetTestCase,
)


class TestQualitySpreadsheet(TestQualityCommon, SpreadsheetTestCase):
    def test_delete_history_after_inactivity(self):
        with freeze_time("2018-01-01"):
            spreadsheet = self.env["quality.check.spreadsheet"].create(
                {
                    "name": "My spreadsheet",
                    "check_cell": "A1",
                }
            )
            spreadsheet.dispatch_spreadsheet_message(
                self.new_revision_data(spreadsheet)
            )
            snapshot = {"revisionId": "next-revision"}
            self.snapshot(
                spreadsheet,
                spreadsheet.current_revision_uuid,
                "next-revision",
                snapshot,
            )
            revisions = spreadsheet.with_context(
                active_test=False
            ).spreadsheet_revision_ids
            revisions.write_date = "2018-01-01"

            self.env["quality.check.spreadsheet"]._gc_spreadsheet_history()
            self.assertTrue(
                spreadsheet.with_context(active_test=False).spreadsheet_revision_ids
            )

        with freeze_time("2018-01-02"):
            self.env["quality.check.spreadsheet"]._gc_spreadsheet_history()
            self.assertFalse(
                spreadsheet.with_context(active_test=False).spreadsheet_revision_ids
            )
