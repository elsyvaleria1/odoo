from odoo import Command
from odoo.tests.common import TransactionCase, new_test_user


class TestVoipCall(TransactionCase):
    def test_is_within_same_company_true_with_contacts_of_same_company(self):
        caller = new_test_user(self.env, login="test_user")
        company = self.env["res.partner"].create(
            {
                "name": "Test Company",
                "is_company": True,
            },
        )
        caller_partner = self.env["res.partner"].create(
            {
                "name": "Contact 1",
                "parent_id": company.id,
            },
        )
        callee_partner = self.env["res.partner"].create(
            {
                "name": "Contact 2",
                "parent_id": company.id,
            },
        )
        self.assertEqual(caller_partner.commercial_partner_id, company)
        self.assertEqual(callee_partner.commercial_partner_id, company)
        caller.partner_id = caller_partner
        call = self.env["phone.call"].create(
            {
                "phone_number": "+1234567890",
                "partner_id": callee_partner.id,
                "user_id": caller.id,
            },
        )
        self.assertTrue(call.is_within_same_company)

    def test_is_within_same_company_false_with_contacts_of_different_companies(self):
        caller = new_test_user(self.env, login="test_user")
        company_1 = self.env["res.partner"].create(
            {
                "name": "Test Company 1",
                "is_company": True,
            },
        )
        company_2 = self.env["res.partner"].create(
            {
                "name": "Test Company 2",
                "is_company": True,
            },
        )
        caller_partner = self.env["res.partner"].create(
            {
                "name": "Contact 1",
                "parent_id": company_1.id,
            },
        )
        callee_partner = self.env["res.partner"].create(
            {
                "name": "Contact 2",
                "parent_id": company_2.id,
            },
        )
        self.assertEqual(caller_partner.commercial_partner_id, company_1)
        self.assertEqual(callee_partner.commercial_partner_id, company_2)
        caller.partner_id = caller_partner
        call = self.env["phone.call"].create(
            {
                "phone_number": "+1234567890",
                "partner_id": callee_partner.id,
                "user_id": caller.id,
            },
        )
        self.assertFalse(call.is_within_same_company)

    def test_is_within_same_company_false_no_partner(self):
        caller = new_test_user(self.env, login="test_user")
        call = self.env["phone.call"].create(
            {
                "phone_number": "+1234567890",
                "user_id": caller.id,
            },
        )
        self.assertFalse(call.is_within_same_company)

    def test_is_within_same_company_false_user_no_partner(self):
        company = self.env["res.partner"].create(
            {
                "name": "Test Company",
                "is_company": True,
            },
        )
        caller = new_test_user(self.env, login="test_user")
        callee_partner = self.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "partner@example.com",
            },
        )
        callee_partner.commercial_partner_id = company
        call = self.env["phone.call"].create(
            {
                "phone_number": "+1234567890",
                "partner_id": callee_partner.id,
                "user_id": caller.id,
            },
        )
        self.assertFalse(call.is_within_same_company)

    def test_acquire_contact_info_with_voip_extension(self):
        user_with_extension = new_test_user(
            self.env, login="user_with_extension", voip_username="8888"
        )
        voip_user = new_test_user(self.env, login="voip_user")
        call = self.env["phone.call"].create(
            {
                "phone_number": "8888",
                "user_id": voip_user.id,
            }
        )
        store_data = call.with_user(voip_user).acquire_contact_info()

        self.assertEqual(
            store_data["res.partner"][0]["id"], user_with_extension.partner_id.id
        )

        self.assertEqual(call.partner_id, user_with_extension.partner_id)

    def test_acquire_contact_info_without_match_leaves_contact_empty(self):
        call = self.env["phone.call"].create(
            {"phone_number": "9876543210999", "user_id": self.env.uid}
        )
        self.assertIsNone(call.acquire_contact_info())
        self.assertFalse(call.partner_id)

    def test_an_answered_outgoing_call_takes_its_dialog_name(self):
        call = self.env["phone.call"].create(
            {
                "phone_number": "5512345678",
                "user_id": self.env.uid,
                "direction": "outgoing",
            }
        )
        call.start_call(sip_call_id="dialog@browser")
        self.assertEqual(call.sip_call_id, "dialog@browser")
        call.start_call(sip_call_id="another@browser")
        self.assertEqual(
            call.sip_call_id, "dialog@browser", "a named dialog stays named"
        )

    def test_acquire_contact_info_with_no_number_names_nobody(self):
        call = self.env["phone.call"].create(
            {"phone_number": False, "user_id": self.env.uid}
        )
        self.assertIsNone(call.acquire_contact_info())
        self.assertFalse(call.partner_id)

    def test_acquire_contact_info_matches_however_the_line_writes_the_number(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Rancho Xiuman",
                "phone_ids": [Command.create({"number": "+52 (55) 1234-5678"})],
            }
        )
        call = self.env["phone.call"].create(
            {"phone_number": "5215512345678", "user_id": self.env.uid}
        )
        call.acquire_contact_info()
        self.assertEqual(call.partner_id, partner)
