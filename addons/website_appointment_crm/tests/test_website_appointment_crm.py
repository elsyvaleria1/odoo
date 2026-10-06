from odoo.tests import HttpCase, common

from odoo.addons.appointment_crm.tests.common import TestAppointmentCrmCommon
from odoo.addons.website.tests.test_website_visitor import MockVisitor


class WebsiteAppointmentCRMTest(TestAppointmentCrmCommon, MockVisitor):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.visitor_contact_1 = cls.env["website.visitor"].create(
            {
                "name": "Visitor identified",
                "partner_id": cls.contact_1.id,
                "access_token": cls.contact_1.id,
            }
        )
        cls.visitor_user_sales_leads = cls.env["website.visitor"].create(
            {
                "name": "Visitor identified",
                "partner_id": cls.user_sales_leads.partner_id.id,
                "access_token": cls.user_sales_leads.partner_id.id,
            }
        )
        cls.visitor_non_identified = cls.env["website.visitor"].create(
            {
                "name": "Visitor non identified",
                "access_token": "c8d20bd006c3bf46b875451defb5991d",
            }
        )

    def test_appointment_visitor_event_organizer(self):
        with self.mock_visitor_from_request(
            force_visitor=self.visitor_user_sales_leads
        ):
            meeting = self._create_meetings_from_appointment_type(
                self.appointment_type_create, self.user_sales_leads, self.contact_1
            )
            self.assertFalse(meeting.opportunity_id.visitor_ids)

    def test_appointment_visitor_identified(self):
        with self.mock_visitor_from_request(force_visitor=self.visitor_contact_1):
            meeting = self._create_meetings_from_appointment_type(
                self.appointment_type_create, self.user_sales_leads, self.contact_1
            )
            self.assertEqual(meeting.opportunity_id.visitor_ids, self.visitor_contact_1)

    def test_appointment_visitor_non_identified(self):
        with self.mock_visitor_from_request(force_visitor=self.visitor_non_identified):
            meeting = self._create_meetings_from_appointment_type(
                self.appointment_type_create, self.user_sales_leads, self.contact_1
            )
            self.assertEqual(
                meeting.opportunity_id.visitor_ids, self.visitor_non_identified
            )


@common.tagged("post_install", "-at_install")
class WebsiteAppointmentCRMHttpTest(TestAppointmentCrmCommon, HttpCase):
    def test_appointment_forced_staff_user_tour(self):
        self.start_tour(
            "/appointment", "appointment_crm_forced_staff_user_tour", login=None
        )
        created_lead = self.env["crm.lead"].search(
            [
                ("email_normalized", "=", "customer@odoo.com"),
                ("user_id", "=", self.user_sales_leads.id),
            ]
        )
        self.assertEqual(len(created_lead), 1)
        self.assertEqual(len(created_lead.calendar_event_ids), 2)

        self.assertTrue(
            all(
                staff_user == self.user_sales_leads
                for staff_user in created_lead.calendar_event_ids.user_id
            )
        )
