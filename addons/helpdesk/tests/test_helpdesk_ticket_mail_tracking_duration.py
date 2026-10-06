from odoo.tests import tagged

from odoo.addons.mail.tests.common_tracking import MailTrackingDurationMixinCase


@tagged("is_query_count")
class TestHelpdeskTicketMailTrackingDuration(MailTrackingDurationMixinCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass("helpdesk.ticket")

    def test_helpdesk_ticket_mail_tracking_duration(self):
        self._test_record_duration_tracking()

    def test_helpdesk_ticket_mail_tracking_duration_batch(self):
        self._test_record_duration_tracking_batch()

    def test_helpdesk_ticket_queries_batch_mail_tracking_duration(self):
        self._test_queries_batch_duration_tracking()
