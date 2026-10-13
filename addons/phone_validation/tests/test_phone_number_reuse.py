from odoo import Command
from odoo.tests import Form, TransactionCase, new_test_user, tagged

from odoo.addons.phone_validation import post_init_hook, uninstall_hook


@tagged("post_install", "-at_install")
class TestPhoneNumberReuse(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.romania = cls.env.ref("base.ro")
        cls.first = cls.env["res.partner"].create(
            {
                "name": "Bucharest office",
                "country_id": cls.romania.id,
                "phone_ids": [Command.create({"number": "(021) 209.99.99"})],
            }
        )

    def test_a_local_number_added_to_a_second_contact_reuses_the_first(self):
        second = self.env["res.partner"].create(
            {"name": "Bucharest branch", "country_id": self.romania.id}
        )
        second.phone_ids = [Command.create({"number": "(021) 209.99.99"})]
        self.env.flush_all()
        self.assertEqual(second.phone_ids, self.first.phone_ids)
        self.assertEqual(second.phone_ids.sanitized, "+40212099999")
        self.assertEqual(
            self.env["phone.number"].search_count([("sanitized", "=", "+40212099999")]),
            1,
        )

    def test_a_contact_rewriting_its_own_number_keeps_one_row(self):
        self.first.write({"phone_ids": [Command.create({"number": "(021) 209.99.99"})]})
        self.env.flush_all()
        self.assertEqual(len(self.first.phone_ids), 1)

    def test_a_bank_reuses_its_partners_number_through_the_inherited_field(self):
        bank = self.env["res.bank"].create(
            {"name": "Alpha Bank", "country_id": self.romania.id}
        )
        bank.write({"phone_ids": [Command.create({"number": "(021) 209.99.99"})]})
        self.env.flush_all()
        self.assertEqual(bank.phone_ids, self.first.phone_ids)
        self.assertIn(bank.partner_id, bank.phone_ids.partner_ids)

    def test_a_contact_whose_country_is_corrected_has_its_number_reread(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Mislabelled office",
                "country_id": self.romania.id,
                "phone_ids": [Command.create({"number": "02 209 99 99"})],
            }
        )
        self.env.flush_all()

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids.sanitized, "+3222099999")

    def _mislabelled(self, **extra):
        contact = self.env["res.partner"].create(
            {
                "name": "Mislabelled office",
                "country_id": self.romania.id,
                "phone_ids": [Command.create({"number": "02 209 99 99"})],
                **extra,
            }
        )
        self.env.flush_all()
        return contact

    def _brussels_number(self):
        brussels = self.env["res.partner"].create(
            {
                "name": "Brussels office",
                "country_id": self.env.ref("base.be").id,
                "phone_ids": [
                    Command.create({"number": "+32 2 209 99 99", "note": "Desk 4"})
                ],
            }
        )
        self.env.flush_all()
        return brussels.phone_ids

    def test_a_corrected_country_that_rereads_into_a_held_number_links_to_it(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        duplicate = contact.phone_ids

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, held)
        self.assertEqual(held.sanitized, "+3222099999")
        self.assertFalse(duplicate.exists())
        self.assertEqual(contact.main_mobile_id, held)

    def test_a_merged_number_stays_preferred_by_its_contact(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        contact.preferred_phone_id = contact.phone_ids

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.preferred_phone_id, held)

    def test_a_shared_number_is_not_reread_when_one_contact_moves(self):
        contact = self._mislabelled()
        phone = contact.phone_ids
        sanitized = phone.sanitized
        self.env["res.partner"].create(
            {
                "name": "Mislabelled branch",
                "country_id": self.romania.id,
                "phone_ids": [Command.link(phone.id)],
            }
        )

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(phone.sanitized, sanitized)
        self.assertEqual(phone.country_id, self.romania)

    def test_a_chosen_country_is_not_reread(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Chosen office",
                "country_id": self.romania.id,
                "phone_ids": [
                    Command.create(
                        {"number": "021 209 99 98", "country_id": self.romania.id}
                    )
                ],
            }
        )
        self.env.flush_all()

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids.sanitized, "+40212099998")

    def test_a_number_typed_before_its_contact_reads_the_contacts_country(self):
        phone = self.env["phone.number"].create({"number": "02 209 99 98"})
        contact = self.env["res.partner"].create(
            {
                "name": "Brussels annex",
                "country_id": self.env.ref("base.be").id,
                "phone_ids": [Command.link(phone.id)],
            }
        )
        self.env.flush_all()

        self.assertEqual(contact.phone_ids.sanitized, "+3222099998")

    def test_a_portal_user_cannot_pull_a_number_it_cannot_read_onto_itself(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        mine = contact.phone_ids
        portal = new_test_user(
            self.env,
            login="mislabelled_portal",
            groups="base.group_portal",
            partner_id=contact.id,
        )
        self.assertFalse(held.with_user(portal).has_access("read"))

        contact.with_user(portal).sudo().write(
            {"country_id": self.env.ref("base.be").id}
        )
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, mine)
        self.assertNotIn(contact, held.partner_ids)

    def test_a_contact_writer_who_may_not_delete_numbers_still_merges(self):
        held = self._brussels_number()
        held.active = False
        contact = self._mislabelled()
        writers = self.env["res.groups"].create({"name": "Contact writers"})
        self.env["ir.access"].create(
            {
                "name": "Contact writers write contacts",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "group_id": writers.id,
                "kind": "permission",
                "operation": "cu",
            }
        )
        writer = new_test_user(
            self.env, login="contact_writer", groups="base.group_user"
        )
        writer.group_ids = [Command.link(writers.id)]
        self.assertFalse(contact.phone_ids.with_user(writer).has_access("unlink"))

        contact.with_user(writer).country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, held)
        self.assertTrue(held.active)

    def test_a_number_stored_before_validation_is_rekeyed_into_its_holder(self):
        held = self.first.phone_ids
        local = self.env["res.partner"].create(
            {
                "name": "Bucharest annex",
                "country_id": self.romania.id,
                "phone_ids": [Command.create({"number": "+40 21 209 99 90"})],
            }
        )
        stale = local.phone_ids
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE phone_number SET number = %s, sanitized = %s WHERE id = %s",
            ["021 209 99 99", "0212099999", stale.id],
        )
        self.env.invalidate_all()

        post_init_hook(self.env)

        self.assertFalse(stale.exists())
        self.assertEqual(local.phone_ids, held)
        self.assertEqual(
            self.env["phone.number"].create(
                {"number": "021 209 99 99", "country_id": self.romania.id}
            ),
            held,
        )

    def test_uninstalling_rekeys_numbers_for_the_base_normalizer(self):
        held = self.first.phone_ids
        international = self.env["phone.number"].create(
            {"number": "+40 21 209 99 98", "country_id": self.romania.id}
        )
        self.assertEqual(held.sanitized, "+40212099999")

        uninstall_hook(self.env)

        self.assertEqual(held.sanitized, "0212099999")
        self.assertEqual(international.sanitized, "+40212099998")
        self.assertEqual(
            self.env["phone.number"].search(
                [
                    (
                        "sanitized",
                        "=",
                        held._normalize_number_without_validation(
                            "021 209 99 99", self.romania
                        ),
                    )
                ]
            ),
            held,
        )

    def _a_local_number_stored_by_another_company(self):
        self.env.company.country_id = self.env.ref("base.us")
        paris = self.env["res.company"].create(
            {"name": "Paris office", "country_id": self.env.ref("base.fr").id}
        )
        contact = (
            self.env["res.partner"]
            .with_company(paris)
            .create(
                {
                    "name": "Paris desk",
                    "phone_ids": [Command.create({"number": "06 12 34 56 78"})],
                }
            )
        )
        self.env.flush_all()
        self.assertFalse(contact.phone_ids.country_id)
        self.assertEqual(contact.phone_ids.sanitized, "+33612345678")
        return contact.phone_ids

    def test_rekeying_keeps_a_local_number_keyed_by_another_companys_country(self):
        phone = self._a_local_number_stored_by_another_company()
        self.env["phone.blacklist"].add("+33 6 12 34 56 78")
        self.assertTrue(phone.blacklisted)

        post_init_hook(self.env)

        self.assertEqual(phone.sanitized, "+33612345678")
        self.assertTrue(phone.blacklisted)

    def test_uninstalling_rekeys_a_local_number_keyed_by_another_companys_country(
        self,
    ):
        phone = self._a_local_number_stored_by_another_company()

        uninstall_hook(self.env)

        self.assertEqual(phone.sanitized, "0612345678")

    def test_a_rekeyed_number_refreshes_its_contacts_sanitized_phone(self):
        phone = self.first.phone_ids
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE phone_number SET sanitized = %s WHERE id = %s",
            ["0212099999", phone.id],
        )
        self.env.cr.execute(
            "UPDATE res_partner SET phone_sanitized = %s WHERE id = %s",
            ["0212099999", self.first.id],
        )
        self.env.invalidate_all()

        post_init_hook(self.env)

        self.assertEqual(phone.sanitized, "+40212099999")
        self.assertEqual(self.first.phone_sanitized, "+40212099999")

    def _stored_before_validation(self, phone):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE phone_number SET country_id = NULL, sanitized = %s WHERE id = %s",
            [phone._normalize_number_without_validation(phone.number), phone.id],
        )
        self.env.invalidate_all()

    def _contact_of(self, company, number):
        contact = (
            self.env["res.partner"]
            .with_company(company)
            .create(
                {
                    "name": f"{company.name} desk",
                    "company_id": company.id,
                    "phone_ids": [Command.create({"number": number})],
                }
            )
        )
        self._stored_before_validation(contact.phone_ids)
        return contact.phone_ids

    def test_rekeying_reads_a_local_number_under_its_contacts_company(self):
        self.env.company.country_id = self.env.ref("base.us")
        mexico = self.env["res.company"].create(
            {"name": "Monterrey office", "country_id": self.env.ref("base.mx").id}
        )
        american = self.env["phone.number"].create({"number": "+1 202 555 0123"})
        mexican = self._contact_of(mexico, "202 555 0123")
        valid = self._contact_of(mexico, "55 1234 5678")
        self.assertEqual(mexican.sanitized, "2025550123")

        post_init_hook(self.env)

        self.assertTrue(mexican.exists())
        self.assertEqual(mexican.sanitized, "2025550123")
        self.assertEqual(american.sanitized, "+12025550123")
        self.assertEqual(valid.sanitized, "+525512345678")

    def test_rekeying_keeps_a_local_number_whose_contacts_disagree(self):
        self.env.company.country_id = self.env.ref("base.fr")
        paris = self.env["res.company"].create(
            {"name": "Paris office", "country_id": self.env.ref("base.fr").id}
        )
        phone = self._contact_of(paris, "06 12 34 56 79")
        self.env["res.partner"].create(
            {
                "name": "Bucharest contact",
                "country_id": self.romania.id,
                "phone_ids": [Command.link(phone.id)],
            }
        )
        self._stored_before_validation(phone)

        post_init_hook(self.env)

        self.assertEqual(phone.sanitized, "0612345679")

    def test_rekeying_merges_a_number_without_losing_what_it_held(self):
        held = self.first.phone_ids
        held.note = "Reception"
        stale = self.env["phone.number"].create(
            {
                "number": "+40 21 209 99 90",
                "country_id": self.romania.id,
                "type": "landline",
                "label": "Switchboard",
                "note": "Ask for Ana",
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE phone_number SET number = %s, sanitized = %s WHERE id = %s",
            ["021 209 99 99", "0212099999", stale.id],
        )
        self.env.invalidate_all()

        post_init_hook(self.env)

        self.assertFalse(stale.exists())
        self.assertEqual(held.type, "mobile")
        self.assertEqual(held.label, "Switchboard")
        self.assertEqual(held.note, "Reception\n\nAsk for Ana")

    def test_a_reread_merge_keeps_what_the_merged_number_held(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        contact.phone_ids.write({"label": "Front desk", "note": "Desk 4"})

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, held)
        self.assertEqual(held.label, "Front desk")
        self.assertEqual(held.note, "Desk 4")

    def test_a_number_typed_before_its_company_had_a_country_follows_it(self):
        company = self.env["res.company"].create({"name": "Countryless office"})
        typed = (
            self.env["res.partner"]
            .with_company(company)
            .create(
                {
                    "name": "Countryless desk",
                    "company_id": company.id,
                    "phone_ids": [Command.create({"number": "021 209 99 77"})],
                }
            )
            .phone_ids
        )
        self.env.flush_all()
        self.assertEqual(typed.sanitized, "0212099977")

        company.country_id = self.romania

        self.assertEqual(typed.sanitized, "+40212099977")
        self.assertEqual(
            self.env["phone.number"]
            .with_company(company)
            .create({"number": "021 209 99 77"}),
            typed,
        )

    def test_a_company_country_set_on_its_partner_rekeys_its_numbers(self):
        company = self.env["res.company"].create({"name": "Countryless office"})
        typed = self._contact_of(company, "021 209 99 74")
        self.assertEqual(typed.sanitized, "0212099974")

        company.partner_id.country_id = self.romania

        self.assertEqual(typed.sanitized, "+40212099974")

    def test_a_company_country_set_by_a_non_merger_keeps_colliding_numbers(self):
        company = self.env["res.company"].create({"name": "Countryless office"})
        held = self.env["phone.number"].create({"number": "+40 21 209 99 76"})
        typed = self._contact_of(company, "021 209 99 76")
        moving = self._contact_of(company, "021 209 99 75")
        manager = new_test_user(
            self.env,
            login="company_manager",
            groups="base.group_user,base.group_erp_manager",
            company_ids=[Command.set([self.env.company.id, company.id])],
        )
        self.assertFalse(held.with_user(manager).has_access("unlink"))

        company.with_user(manager).country_id = self.romania

        self.assertTrue(typed.exists())
        self.assertEqual(typed.sanitized, "0212099976")
        self.assertEqual(moving.sanitized, "+40212099975")

    def test_a_number_created_with_a_default_country_is_keyed_by_it(self):
        self.env.company.country_id = self.env.ref("base.fr")
        phone_id, _ = (
            self.env["phone.number"]
            .with_context(default_country_id=self.env.ref("base.us").id)
            .name_create("202 555 0777")
        )

        self.assertEqual(
            self.env["phone.number"].browse(phone_id).sanitized, "+12025550777"
        )

    def _typed_on(self, form, number, fname="phone_ids"):
        phone_id, _ = (
            self.env["phone.number"]
            .with_context(form._get_context(fname))
            .name_create(number)
        )
        return self.env["phone.number"].browse(phone_id)

    def test_a_number_typed_on_a_base_form_takes_the_records_country(self):
        self.env.company.country_id = self.env.ref("base.fr")
        us = self.env.ref("base.us")
        partner = self.env["res.partner"].create({"name": "Desk", "country_id": us.id})
        user = new_test_user(self.env, login="desk_user", country_id=us.id)
        company = self.env["res.company"].create({"name": "DC", "country_id": us.id})
        bank = self.env["res.bank"].create({"name": "DC bank", "country_id": us.id})
        typed_on = [
            (partner, "base.view_partner_form"),
            (partner, "base.view_partner_simple_form"),
            (user, "base.view_users_form"),
            (user, "base.view_users_simple_form"),
            (company, "base.view_company_form"),
            (bank, "base.view_res_bank_form"),
        ]
        for line, (record, view) in enumerate(typed_on):
            with self.subTest(view=view):
                phone = self._typed_on(Form(record, view=view), f"202 555 07{line:02d}")
                self.assertEqual(phone.sanitized, f"+120255507{line:02d}")
