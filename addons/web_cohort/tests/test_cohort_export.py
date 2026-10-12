import io
import re
import zipfile
from urllib.parse import urlencode

from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _payload(timeline="forward"):
    return {
        "title": "Subscriptions",
        "model": "x_cohort_stuff",
        "timeline": timeline,
        "date_start_string": "Start Date",
        "date_stop_string": "End Date",
        "interval_string": "Month",
        "measure_string": "Count",
        "report": {
            "rows": [
                {
                    "date": "March 2026",
                    "value": 3,
                    "columns": [
                        {"percentage": 100.0},
                        {"percentage": 66.7},
                        {"percentage": "-"},
                    ],
                }
            ],
            "avg": {
                "avg_value": 3.0,
                "columns_avg": {
                    "0": {"percentage": 100.0, "count": 1},
                    "1": {"percentage": 66.7, "count": 1},
                    "2": {"percentage": 0, "count": 0},
                },
            },
        },
    }


@tagged("post_install", "-at_install")
class TestCohortExport(HttpCase):
    def _export(self, timeline="forward"):
        query = urlencode({"data": json_dumps(_payload(timeline))})
        return self.url_open(f"/web/cohort/export?{query}")

    def _shared_strings(self, response):
        with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
            xml = workbook.read("xl/sharedStrings.xml").decode()
        return re.findall(r"<t[^>]*>([^<]*)</t>", xml)

    def test_export_returns_a_spreadsheet(self):
        self.authenticate("admin", "admin")

        response = self._export()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], XLSX_MIMETYPE)
        with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
            self.assertIn("xl/worksheets/sheet1.xml", workbook.namelist())

    def test_export_names_the_file_after_the_report(self):
        self.authenticate("admin", "admin")

        response = self._export()

        disposition = response.headers["Content-Disposition"]
        self.assertIn("Subscriptions", disposition)
        self.assertIn("x_cohort_stuff", disposition)
        self.assertIn(".xlsx", disposition)

    def test_export_supports_the_backward_timeline(self):
        self.authenticate("admin", "admin")

        forward = self._export()
        backward = self._export(timeline="backward")

        self.assertEqual(backward.status_code, 200)
        forward_strings = self._shared_strings(forward)
        backward_strings = self._shared_strings(backward)
        self.assertLessEqual({"+0", "+1", "+2"}, set(forward_strings))
        self.assertLessEqual({"-2", "-1", "0"}, set(backward_strings))
        self.assertNotIn("+0", backward_strings)

    def test_export_requires_an_authenticated_user(self):
        response = self._export()

        self.assertEqual(response.status_code, 200)
        self.assertIn("/web/login", response.url)
