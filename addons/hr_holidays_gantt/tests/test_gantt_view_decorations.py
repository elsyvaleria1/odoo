from datetime import datetime

from lxml import etree

from odoo.tools.safe_eval import safe_eval

from odoo.addons.hr_holidays.tests.common import TestHolidayContract


class TestGanttViewDecorations(TestHolidayContract):
    """Pill decorations of the Time Off Overview gantt.

    web_gantt evaluates the ``decoration-*`` expressions of the <gantt> node
    client-side, once per pill, against that record's own values (see
    ``evaluateBooleanExpr`` in web_gantt/static/src/gantt_renderer.js). Those
    expressions spell out state values by hand, so nothing but a test keeps
    them in step with the selection ``hr.leave.report.calendar.state``
    actually declares: a value that is not in the selection costs no error
    anywhere, it just yields a decoration that can never fire.
    """

    def _evaluate_decoration(self, decoration, report_row):
        """Evaluate one ``decoration-*`` expression the way the client does."""
        view = self.env.ref("hr_holidays_gantt.hr_leave_report_calendar_view_gantt")
        expression = etree.fromstring(view.arch).get(decoration)
        self.assertTrue(expression, f"{decoration} is missing from the gantt node")
        return bool(safe_eval(expression, {"state": report_row.state}))

    def _report_row_for(self, leave):
        """The Overview row the gantt would draw for ``leave``."""
        # hr.leave.report.calendar is a SQL view over hr_leave, so pending ORM
        # writes stay invisible to it until they actually reach the database.
        self.env.flush_all()
        row = self.env["hr.leave.report.calendar"].search(
            [("employee_id", "=", leave.employee_id.id)]
        )
        self.assertEqual(len(row), 1, "Expected exactly one Overview row")
        return row

    def _create_leave(self):
        # A Tuesday, covered by Jules' open-ended contract (from 2015-11-16).
        return self.create_leave(
            datetime(2025, 11, 11, 7, 0, 0),
            datetime(2025, 11, 11, 18, 0, 0),
            name="Doctor Appointment",
            employee_id=self.jules_emp.id,
        )

    def test_refused_time_off_is_decorated_as_danger(self):
        leave = self._create_leave()
        leave.action_refuse()
        row = self._report_row_for(leave)

        self.assertEqual(row.state, "refuse")
        self.assertTrue(
            self._evaluate_decoration("decoration-danger", row),
            "A refused time off must carry the danger decoration in the Time "
            "Off Overview. It is the only marker left on a narrow pill: below "
            "50px of width web_gantt hides the pill title, and with it the "
            "strike-through our own renderer puts on refused requests.",
        )

    def test_pending_time_off_is_not_decorated_as_danger(self):
        """Guard: the danger decoration must key on the refused state alone."""
        leave = self._create_leave()
        row = self._report_row_for(leave)

        self.assertEqual(row.state, "confirm")
        self.assertFalse(self._evaluate_decoration("decoration-danger", row))
        self.assertTrue(self._evaluate_decoration("decoration-info", row))
