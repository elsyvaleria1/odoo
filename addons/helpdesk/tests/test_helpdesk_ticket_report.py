from .common import HelpdeskCommon


class TestHelpdeskTicketReportReadsTheTransaction(HelpdeskCommon):
    def test_a_priority_changed_in_the_transaction_is_reported(self):
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Stale", "team_id": self.test_team.id, "priority": "0"}
        )
        self.env.flush_all()
        ticket.priority = "3"
        rows = self.env["helpdesk.ticket.report.analysis"].search(
            [("ticket_id", "=", ticket.id)]
        )
        self.assertEqual(rows.mapped("priority"), ["3"])
