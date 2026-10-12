from datetime import date, datetime, timedelta

from freezegun import freeze_time

from odoo import Command, exceptions
from odoo.fields import Datetime as FieldsDatetime
from odoo.tests import Form, tagged, users
from odoo.tools import mute_logger

from odoo.addons.event.tests.common import EventCase
from odoo.addons.mail.tests.common import mail_access_both_ways


class TestEventInternalsCommon(EventCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.event_type_complex = cls.env["event.type"].create(
            {
                "name": "Update Type",
                "has_seats_limitation": True,
                "seats_max": 30,
                "default_timezone": "Europe/Paris",
                "event_type_ticket_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "First Ticket",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Second Ticket",
                        },
                    ),
                ],
                "event_type_mail_ids": [
                    (
                        0,
                        0,
                        {
                            "interval_unit": "now",
                            "interval_type": "after_sub",
                            "template_ref": "mail.template,%i"
                            % cls.env["ir.model.data"]._xmlid_to_res_id(
                                "event.event_subscription"
                            ),
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "interval_nbr": 1,
                            "interval_unit": "day",
                            "interval_type": "before_event",
                            "template_ref": "mail.template,%i"
                            % cls.env["ir.model.data"]._xmlid_to_res_id(
                                "event.event_reminder"
                            ),
                        },
                    ),
                ],
            }
        )

        cls.reference_now = datetime(2020, 1, 31, 10, 0, 0)
        cls.reference_beg = datetime(2020, 2, 1, 8, 30, 0)
        cls.reference_end = datetime(2020, 2, 4, 18, 45, 0)

        cls.event_0 = cls.env["event.event"].create(
            {
                "date_begin": cls.reference_beg,
                "date_end": cls.reference_end,
                "date_tz": "Europe/Brussels",
                "name": "TestEvent",
            }
        )


@tagged("event_event")
class TestEventData(TestEventInternalsCommon):
    @users("user_eventmanager")
    def test_event_configuration_question_from_type(self):
        self.env["res.lang"].sudo()._activate_lang("nl_NL")

        event_type = self.event_type_questions.with_user(self.env.user)
        event_type_question_nl = self.event_question_1.with_context(lang="nl_NL")
        event_type_question_nl.title = "Vraag1"
        event_type_question_nl.answer_ids[0].name = "V1-Antwoord1"

        event = self.env["event.event"].create(
            {
                "name": "Event Update Type",
                "event_type_id": event_type.id,
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
            }
        )
        event.invalidate_recordset(["specific_question_ids", "general_question_ids"])

        self.assertEqual(
            sorted(event.question_ids.mapped("question_type")),
            ["email", "name", "phone", "simple_choice", "simple_choice", "text_box"],
        )
        self.assertEqual(
            event.specific_question_ids.filtered(
                lambda q: q.question_type in ["simple_choice", "text_box"]
            ).title,
            "Question1",
        )
        self.assertEqual(
            event.specific_question_ids.filtered(
                lambda q: q.question_type in ["name", "email", "phone", "company_name"]
            ).mapped("title"),
            ["Name", "Email", "Phone"],
        )
        self.assertEqual(
            set(
                event.specific_question_ids.filtered(
                    lambda q: q.question_type in ["simple_choice", "text_box"]
                ).mapped("answer_ids.name")
            ),
            {"Q1-Answer1", "Q1-Answer2"},
        )
        self.assertEqual(len(event.general_question_ids), 2)
        self.assertEqual(event.general_question_ids[0].title, "Question2")
        self.assertEqual(event.general_question_ids[1].title, "Question3")
        self.assertEqual(
            set(event.general_question_ids[0].mapped("answer_ids.name")),
            {"Q2-Answer1", "Q2-Answer2"},
        )
        event_question_nl = event.specific_question_ids.filtered_domain(
            [
                ("title", "=", self.event_question_1.title),
            ]
        ).with_context(lang="nl_NL")
        self.assertNotEqual(
            event_question_nl.title,
            self.event_question_1.title,
            "Translated title should differ from untranslated title.",
        )
        self.assertEqual(
            event_question_nl.title,
            event_type_question_nl.title,
            "Translated title should be copied.",
        )
        self.assertEqual(
            set(event_question_nl.answer_ids.mapped("name")),
            set(event_type_question_nl.answer_ids.mapped("name")),
            "Translated answer names should be copied.",
        )

    @users("user_eventmanager")
    @mute_logger("odoo.models.unlink")
    def test_event_configuration_from_type(self):
        self.assertEqual(self.env.user.tz, "Europe/Brussels")

        event_type = self.env["event.type"].browse(self.event_type_complex.id)

        event = self.env["event.event"].create(
            {
                "name": "Event Update Type",
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
                "event_mail_ids": False,
            }
        )
        self.assertEqual(event.date_tz, self.env.user.tz)
        self.assertFalse(event.seats_limited)
        self.assertEqual(event.event_mail_ids, self.env["event.mail"])
        self.assertEqual(event.event_ticket_ids, self.env["event.event.ticket"])

        self._create_registrations(event, 1)

        event_type.write(
            {
                "event_type_mail_ids": [
                    (5, 0),
                    (
                        0,
                        0,
                        {
                            "interval_nbr": 1,
                            "interval_unit": "day",
                            "interval_type": "before_event",
                            "template_ref": "mail.template,%i"
                            % self.env["ir.model.data"]._xmlid_to_res_id(
                                "event.event_reminder"
                            ),
                        },
                    ),
                ],
                "event_type_ticket_ids": [(5, 0), (0, 0, {"name": "TestRegistration"})],
            }
        )
        event.write({"event_type_id": event_type.id})
        self.assertEqual(event.date_tz, "Europe/Paris")
        self.assertTrue(event.seats_limited)
        self.assertEqual(event.seats_max, event_type.seats_max)
        self.assertEqual(len(event.event_mail_ids), 1)
        self.assertEqual(event.event_mail_ids.interval_nbr, 1)
        self.assertEqual(event.event_mail_ids.interval_unit, "day")
        self.assertEqual(event.event_mail_ids.interval_type, "before_event")
        self.assertEqual(
            event.event_mail_ids.template_ref, self.env.ref("event.event_reminder")
        )
        self.assertEqual(len(event.event_ticket_ids), 1)

        event_type.write({"has_seats_limitation": False})
        self.assertEqual(event_type.seats_max, 0)
        self.assertTrue(event.seats_limited)
        self.assertEqual(event.seats_max, 30)
        event.write({"event_type_id": False})
        self.assertEqual(event.event_type_id, self.env["event.type"])

        event.write({"event_type_id": event_type.id})
        self.assertFalse(event.seats_limited)
        self.assertEqual(event.seats_max, 0)
        self.assertEqual(len(event.event_ticket_ids), 1)
        event_ticket1 = event.event_ticket_ids[0]
        self.assertEqual(event_ticket1.name, "TestRegistration")

    @users("user_eventmanager")
    def test_event_configuration_mails_from_type(self):
        event_type_default = self.env["event.type"].create(
            {
                "name": "Type Default",
                "event_type_mail_ids": False,
            }
        )
        event_type_mails = self.env["event.type"].create(
            {
                "name": "Type Mails",
                "event_type_mail_ids": [
                    Command.clear(),
                    Command.create(
                        {
                            "interval_nbr": 77,
                            "interval_unit": "day",
                            "interval_type": "after_event",
                            "template_ref": "mail.template,%i"
                            % self.env["ir.model.data"]._xmlid_to_res_id(
                                "event.event_reminder"
                            ),
                        }
                    ),
                ],
            }
        )
        event = self.env["event.event"].create(
            {
                "name": "Event",
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
                "event_type_id": event_type_default.id,
            }
        )
        event.write(
            {
                "event_mail_ids": [
                    Command.clear(),
                    Command.create(
                        {
                            "interval_unit": "now",
                            "interval_type": "after_sub",
                            "template_ref": "mail.template,%i"
                            % self.env["ir.model.data"]._xmlid_to_res_id(
                                "event.event_subscription"
                            ),
                        }
                    ),
                ]
            }
        )
        mail = event.event_mail_ids[0]
        registration = self._create_registrations(event, 1)
        self.assertEqual(registration.state, "open")
        self.assertEqual(
            set(mail.mapped("mail_registration_ids.registration_id.id")),
            {registration.id},
        )
        event_form = Form(event)
        self.assertEqual(
            {m.get("id", None) for m in event_form.event_mail_ids._records}, {mail.id}
        )
        event_form.event_type_id = event_type_mails
        self.assertEqual(len(event_form.event_mail_ids._records), 2)
        self.assertTrue(
            filter(
                lambda m: m.get("id", None) == mail.id,
                event_form.event_mail_ids._records,
            )
        )
        computed_mail = next(
            filter(
                lambda m: m.get("id", None) != mail.id,
                event_form.event_mail_ids._records,
            ),
            {},
        )
        self.assertEqual(computed_mail.get("interval_nbr", None), 77)
        self.assertEqual(computed_mail.get("interval_unit", None), "day")
        self.assertEqual(computed_mail.get("interval_type", None), "after_event")
        event_form.event_type_id = event_type_default
        self.assertEqual(
            {m.get("id", None) for m in event_form.event_mail_ids._records}, {mail.id}
        )

    @users("user_eventmanager")
    def test_event_configuration_note_from_type(self):
        event_type = self.env["event.type"].browse(self.event_type_complex.id)

        event = self.env["event.event"].create(
            {
                "name": "Event Update Type Note",
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
            }
        )

        event.write({"note": "<p>Event Note</p>"})
        event_type.write({"note": "<p><br></p>"})
        event.write({"event_type_id": event_type.id})
        self.assertEqual(event.note, "<p>Event Note</p>")

        event.write({"event_type_id": False})
        event_type.write({"note": "<p>Event Type Note</p>"})
        event.write({"event_type_id": event_type.id})
        self.assertEqual(event.note, "<p>Event Type Note</p>")

    @users("user_eventmanager")
    def test_event_configuration_questions_from_type(self):
        (
            event_type_1_question,
            event_type_1_removed_question,
            event_type_2_question,
            event_type_common_question,
        ) = self.env["event.question"].create(
            [
                {"title": "Event Type 1 Question"},
                {"title": "Event Type 1 Removed Question"},
                {"title": "Event Type 2 Question"},
                {"title": "Event Type Common Question"},
            ]
        )
        event_type_1_questions = (
            event_type_1_question
            + event_type_1_removed_question
            + event_type_common_question
        )
        event_type_1, event_type_2 = self.env["event.type"].create(
            [
                {
                    "name": "Event Type 1",
                    "question_ids": [Command.set(event_type_1_questions.ids)],
                },
                {
                    "name": "Event Type 2",
                    "question_ids": [
                        Command.set(
                            (event_type_2_question + event_type_common_question).ids
                        )
                    ],
                },
            ]
        )
        event = self.env["event.event"].create(
            {
                "name": "Event",
                "event_type_id": event_type_1.id,
                "date_begin": self.reference_beg,
                "date_end": self.reference_end,
            }
        )
        self.assertEqual(event.question_ids, event_type_1.question_ids)

        event_type_1.question_ids = [Command.clear()]
        self.assertTrue(event.question_ids, event_type_1_questions)

        self.env["event.registration.answer"].create(
            {
                "question_id": event_type_1_question.id,
                "registration_id": self.env["event.registration"]
                .create({"event_id": event.id})
                .id,
                "value_text_box": "Value Registration Answer",
            }
        )
        event.write({"event_type_id": event_type_2.id})
        self.assertEqual(
            event.question_ids,
            event_type_1_question + event_type_2_question + event_type_common_question,
        )

    @users("user_eventmanager")
    def test_event_configuration_tickets_from_type(self):
        event_type_default = self.env["event.type"].create(
            {
                "name": "Type Default",
            }
        )
        event_type_tickets = self.env["event.type"].create(
            {
                "name": "Type Tickets",
            }
        )
        event_type_tickets.write(
            {
                "event_type_ticket_ids": [
                    Command.clear(),
                    Command.create(
                        {
                            "name": "Default Ticket",
                            "seats_max": 10,
                        }
                    ),
                ]
            }
        )
        event = self.env["event.event"].create(
            {
                "name": "Event",
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
                "event_type_id": event_type_default.id,
            }
        )
        event.write(
            {
                "event_ticket_ids": [
                    Command.clear(),
                    Command.create(
                        {
                            "name": "Registration Ticket",
                            "seats_max": 10,
                        }
                    ),
                ]
            }
        )
        ticket = event.event_ticket_ids[0]
        registration = self._create_registrations(event, 1)
        registration.write({"event_ticket_id": ticket.id})
        event_form = Form(event)
        self.assertEqual(
            {m.get("name", None) for m in event_form.event_ticket_ids._records},
            {"Registration Ticket"},
        )
        event_form.event_type_id = event_type_tickets
        self.assertEqual(
            {m.get("name", None) for m in event_form.event_ticket_ids._records},
            {"Registration Ticket", "Default Ticket"},
        )
        event_form.event_type_id = event_type_default
        self.assertEqual(
            {m.get("name", None) for m in event_form.event_ticket_ids._records},
            {"Registration Ticket"},
        )

    @users("user_eventmanager")
    def test_event_date_computation(self):
        event = self.event_0.with_user(self.env.user)
        with freeze_time(self.reference_now):
            event.write(
                {
                    "registration_ids": [
                        (
                            0,
                            0,
                            {"partner_id": self.event_customer.id, "name": "test_reg"},
                        )
                    ],
                    "date_begin": datetime(2020, 1, 31, 15, 0, 0),
                    "date_end": datetime(2020, 4, 5, 18, 0, 0),
                }
            )
            registration = event.registration_ids[0]
            self.assertEqual(registration.event_date_range, "today")

            event.date_begin = datetime(2020, 2, 1, 15, 0, 0)
            registration.invalidate_recordset(["event_date_range"])
            self.assertEqual(registration.event_date_range, "tomorrow")

            event.date_begin = datetime(2020, 2, 2, 6, 0, 0)
            registration.invalidate_recordset(["event_date_range"])
            self.assertEqual(registration.event_date_range, "in 2 days")

            event.date_begin = datetime(2020, 2, 20, 17, 0, 0)
            registration.invalidate_recordset(["event_date_range"])
            self.assertEqual(registration.event_date_range, "next month")

            event.date_begin = datetime(2020, 3, 1, 10, 0, 0)
            registration.invalidate_recordset(["event_date_range"])
            self.assertEqual(registration.event_date_range, "on Mar 1, 2020")

            event.write(
                {
                    "date_begin": datetime(2020, 1, 31, 14, 30, 0),
                    "date_end": datetime(2020, 2, 1, 2, 0, 0),
                    "date_tz": "America/Mexico_City",
                }
            )
            self.assertTrue(event.is_one_day)

        with freeze_time(datetime(2020, 6, 20, 20, 0, 0)):
            event.write(
                {
                    "date_begin": datetime(2020, 6, 27, 1, 0, 0),
                    "date_end": datetime(2020, 7, 8, 2, 0, 0),
                    "date_tz": "America/Los_Angeles",
                }
            )
            registration.invalidate_recordset(["event_date_range"])
            self.assertEqual(registration.event_date_range, "in 6 days")

        with freeze_time(datetime(2020, 6, 20, 13, 0, 0)):
            event.write(
                {
                    "date_begin": datetime(2020, 6, 25, 20, 0, 0),
                    "date_end": datetime(2020, 7, 8, 2, 0, 0),
                    "date_tz": "Australia/Sydney",
                }
            )
            registration.invalidate_recordset(["event_date_range"])
            self.assertEqual(registration.event_date_range, "in 6 days")

    @freeze_time("2020-01-31 10:00:00")
    @users("user_eventmanager")
    def test_event_date_timezone(self):
        event = self.event_0.with_user(self.env.user)
        event.write(
            {
                "date_begin": datetime(2020, 1, 31, 14, 30, 0),
                "date_end": datetime(2020, 2, 1, 2, 0, 0),
                "date_tz": "America/Mexico_City",
            }
        )
        self.assertTrue(event.is_one_day)
        self.assertFalse(event.is_ongoing)

        with freeze_time(self.reference_now):
            default_event = self.env["event.event"].create(
                {
                    "name": "Test Default Event",
                }
            )
        self.assertEqual(default_event.date_begin, self.reference_now)
        self.assertEqual(default_event.date_end, self.reference_now + timedelta(days=1))
        self.assertEqual(default_event.date_tz, self.user_eventmanager.tz)

    @users("user_eventmanager")
    def test_event_mail_default_config(self):
        event = self.env["event.event"].create(
            {
                "name": "Event Update Type",
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
            }
        )
        self.assertEqual(event.date_tz, self.env.user.tz)
        self.assertFalse(event.seats_limited)

        self.assertEqual(len(event.event_mail_ids), 3)
        self.assertEqual(event.event_mail_ids[0].interval_unit, "now")
        self.assertEqual(event.event_mail_ids[0].interval_type, "after_sub")
        self.assertEqual(
            event.event_mail_ids[0].template_ref,
            self.env.ref("event.event_subscription"),
        )
        self.assertEqual(event.event_mail_ids[1].interval_nbr, 1)
        self.assertEqual(event.event_mail_ids[1].interval_unit, "hour")
        self.assertEqual(event.event_mail_ids[1].interval_type, "before_event")
        self.assertEqual(
            event.event_mail_ids[1].template_ref, self.env.ref("event.event_reminder")
        )
        self.assertEqual(event.event_mail_ids[2].interval_nbr, 3)
        self.assertEqual(event.event_mail_ids[2].interval_unit, "day")
        self.assertEqual(event.event_mail_ids[2].interval_type, "before_event")
        self.assertEqual(
            event.event_mail_ids[2].template_ref, self.env.ref("event.event_reminder")
        )

        event.write({"event_mail_ids": False})
        self.assertEqual(event.event_mail_ids, self.env["event.mail"])

    def test_event_mail_filter_template_on_event(self):
        self.env["mail.template"].search(
            [("model", "=", "event.registration")]
        ).unlink()
        self.env["mail.template"].create(
            {
                "model_id": self.env["ir.model"]._get("event.registration").id,
                "name": "test template",
            }
        )
        self.env["mail.template"].create(
            {
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "name": "test template",
            }
        )
        templates = (
            self.env["mail.template"]
            .with_context(filter_template_on_event=True)
            .name_search("test template")
        )
        self.assertEqual(
            len(templates),
            1,
            "Should return only mail templates related to the event registration model",
        )
        templates = (
            self.env["mail.template"]
            .with_context(filter_template_on_event=True)
            .search([("name", "=", "test template")])
        )
        self.assertEqual(
            len(templates),
            1,
            "Should also return only mail templates related to the event registration model using search",
        )

    @users("user_eventmanager")
    def test_event_question_defaults(self):
        event_0, event_1 = self.env["event.event"].create(
            [
                {
                    "name": "TestEvent 0",
                    "date_begin": self.reference_beg,
                    "date_end": self.reference_end,
                },
                {
                    "name": "TestEvent 1",
                    "date_begin": self.reference_beg,
                    "date_end": self.reference_end,
                },
            ]
        )
        self.assertCountEqual(
            event_0.question_ids.mapped("question_type"), ["name", "email", "phone"]
        )
        self.assertEqual(event_0.question_ids, event_1.question_ids)

    @freeze_time("2020-01-31 10:00:00")
    @users("user_eventmanager")
    def test_event_registrable(self):
        event = self.event_0.with_user(self.env.user)
        event.write(
            {
                "date_begin": datetime(2020, 1, 30, 8, 0, 0),
                "date_end": datetime(2020, 1, 31, 8, 0, 0),
            }
        )
        self.assertFalse(event.event_registrations_open)
        event.write(
            {
                "date_end": datetime(2020, 2, 4, 8, 0, 0),
            }
        )
        self.assertTrue(event.event_registrations_open)

        ticket = self.env["event.event.ticket"].create(
            {
                "name": "TestTicket",
                "event_id": event.id,
            }
        )
        self.assertTrue(event.event_registrations_open)

        event.write(
            {
                "date_begin": datetime(2020, 1, 28, 15, 0, 0),
                "date_end": datetime(2020, 1, 30, 15, 0, 0),
            }
        )
        self.assertFalse(event.event_registrations_open)

        registration = self.env["event.registration"].create(
            {
                "name": "Albert Test",
                "event_id": event.id,
            }
        )
        event.write(
            {
                "date_end": datetime(2020, 2, 1, 15, 0, 0),
                "seats_max": 1,
                "seats_limited": True,
            }
        )
        self.assertEqual(event.seats_available, 0)
        self.assertFalse(event.event_registrations_open)

        registration.unlink()
        self.assertEqual(event.seats_available, 1)
        self.assertTrue(event.event_registrations_open)

        ticket.write({"end_sale_datetime": datetime(2020, 1, 30, 15, 0, 0)})
        self.assertTrue(ticket.is_expired)
        self.assertFalse(event.event_registrations_open)

    @freeze_time("2020-01-31 10:00:00")
    @users("user_eventmanager")
    def test_event_multi_slots_registrable(self):
        event = self.event_0.with_user(self.env.user)
        self.assertTrue(event.event_registrations_open)
        event.write(
            {
                "date_begin": datetime(2020, 1, 30, 8, 0, 0),
                "date_end": datetime(2020, 2, 4, 8, 0, 0),
                "is_multi_slots": True,
            }
        )
        self.assertFalse(event.event_ticket_ids)
        self.assertFalse(event.event_slot_ids)
        self.assertFalse(event.event_registrations_open)
        event.write(
            {
                "event_slot_ids": [
                    (
                        0,
                        0,
                        {
                            "date": date(2020, 1, 30),
                            "start_hour": 9,
                            "end_hour": 12,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "date": date(2020, 1, 31),
                            "start_hour": 14,
                            "end_hour": 16,
                        },
                    ),
                ]
            }
        )
        self.assertTrue(event.event_registrations_open)
        event.write(
            {
                "event_ticket_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Better",
                            "seats_limited": True,
                            "seats_max": 2,
                        },
                    ),
                ]
            }
        )
        self.assertTrue(event.event_registrations_open)
        event.write(
            {
                "seats_limited": True,
                "seats_max": 1,
            }
        )
        slot1 = event.event_slot_ids[0]
        slot2 = event.event_slot_ids[1]
        self.assertEqual(slot1.seats_available, 1)
        self.assertEqual(slot2.seats_available, 1)
        regs = self.env["event.registration"].create(
            [
                {
                    "event_id": event.id,
                    "name": "reg_open",
                    "event_slot_id": slot.id,
                }
                for slot in slot1 + slot2
            ]
        )
        self.assertTrue(slot1.is_sold_out)
        self.assertTrue(slot2.is_sold_out)
        self.assertFalse(event.event_registrations_open)
        regs.unlink()
        event.write({"seats_limited": False})
        self.assertTrue(event.event_registrations_open)
        regs = self.env["event.registration"].create(
            [
                {
                    "event_id": event.id,
                    "name": "reg_open",
                    "event_slot_id": slot.id,
                    "event_ticket_id": event.event_ticket_ids.id,
                }
                for slot in slot1 + slot2
                for _ in range(2)
            ]
        )
        self.assertFalse(event.event_registrations_open)

    @freeze_time("2020-01-31 10:00:00")
    @users("user_eventmanager")
    def test_event_ongoing(self):
        event_1 = self.env["event.event"].create(
            {
                "name": "Test Event 1",
                "date_begin": datetime(2020, 1, 25, 8, 0, 0),
                "date_end": datetime(2020, 2, 1, 18, 0, 0),
            }
        )
        self.assertTrue(event_1.is_ongoing)
        ongoing_events = self.env["event.event"].search([("is_ongoing", "=", True)])
        self.assertIn(event_1, ongoing_events)

        event_1.update({"date_begin": datetime(2020, 2, 1, 9, 0, 0)})
        self.assertFalse(event_1.is_ongoing)
        ongoing_events = self.env["event.event"].search([("is_ongoing", "=", True)])
        self.assertNotIn(event_1, ongoing_events)

        event_2 = self.env["event.event"].create(
            {
                "name": "Test Event 2",
                "date_begin": datetime(2020, 1, 25, 8, 0, 0),
                "date_end": datetime(2020, 1, 28, 8, 0, 0),
            }
        )
        self.assertFalse(event_2.is_ongoing)
        finished_or_upcoming_events = self.env["event.event"].search(
            [("is_ongoing", "=", False)]
        )
        self.assertIn(event_2, finished_or_upcoming_events)

        event_2.update({"date_end": datetime(2020, 2, 2, 8, 0, 1)})
        self.assertTrue(event_2.is_ongoing)
        finished_or_upcoming_events = self.env["event.event"].search(
            [("is_ongoing", "=", False)]
        )
        self.assertNotIn(event_2, finished_or_upcoming_events)

    @users("user_eventmanager")
    def test_event_seats(self):
        event_type = self.event_type_complex.with_user(self.env.user)
        event = self.env["event.event"].create(
            {
                "name": "Event Update Type",
                "event_type_id": event_type.id,
                "date_begin": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=1)
                ),
                "date_end": FieldsDatetime.to_string(
                    datetime.today() + timedelta(days=15)
                ),
            }
        )

        self.assertEqual(event.address_id, self.env.user.company_id.partner_id)
        self.assertTrue(event.seats_limited)
        self.assertEqual(event.seats_available, event.event_type_id.seats_max)
        self.assertEqual(event.seats_reserved, 0)
        self.assertEqual(event.seats_used, 0)
        self.assertEqual(event.seats_taken, 0)

        reg_open_multiple = self.env["event.registration"].create(
            [
                {
                    "event_id": event.id,
                    "name": "reg_open",
                }
                for _ in range(5)
            ]
        )
        self.assertEqual(set(reg_open_multiple.mapped("state")), {"open"})
        reg_open = reg_open_multiple[0]

        reg_draft = self.env["event.registration"].create(
            {
                "event_id": event.id,
                "name": "reg_draft",
            }
        )
        reg_draft.write({"state": "draft"})
        reg_done = self.env["event.registration"].create(
            {
                "event_id": event.id,
                "name": "reg_done",
            }
        )
        reg_done.write({"state": "done"})
        self.assertEqual(event.seats_available, event.event_type_id.seats_max - 6)
        self.assertEqual(event.seats_reserved, 5)
        self.assertEqual(event.seats_used, 1)
        self.assertEqual(event.seats_taken, 6)

        reg_open.action_archive()
        self.assertEqual(event.seats_reserved, 4)
        self.assertEqual(event.seats_available, event.event_type_id.seats_max - 5)
        self.assertEqual(event.seats_taken, 5)

        reg_draft.action_archive()
        self.assertEqual(event.seats_available, event.event_type_id.seats_max - 5)
        self.assertEqual(event.seats_taken, 5)

        reg_open.action_unarchive()
        self.assertEqual(event.seats_reserved, 5)
        self.assertEqual(event.seats_available, event.event_type_id.seats_max - 6)
        self.assertEqual(event.seats_taken, 6)

        reg_draft.action_unarchive()
        self.assertEqual(event.seats_available, event.event_type_id.seats_max - 6)
        self.assertEqual(event.seats_taken, 6)

        reg_open.action_archive()
        self.assertEqual(event.seats_reserved, 4)

        event.write({"seats_max": 5})
        with self.assertRaises(exceptions.ValidationError):
            reg_open.action_unarchive()

        event.write({"seats_max": 6})
        self.assertEqual(reg_open.state, "open")
        reg_open.action_unarchive()

        with self.assertRaises(exceptions.ValidationError):
            reg_draft.write({"state": "open"})

        new_open_registration = {
            "event_id": event.id,
            "name": "reg_open",
        }
        with self.assertRaises(exceptions.ValidationError):
            self.env["event.registration"].create(new_open_registration)

        event.write({"seats_limited": 0})
        self.env["event.registration"].create(new_open_registration)
        reg_draft.write({"state": "open"})


@tagged("event_registration")
class TestEventRegistrationData(TestEventInternalsCommon):
    @users("user_eventmanager")
    def test_registration_attended_log(self):
        with self.mock_datetime_and_now("2025-05-03 17:00:00"):
            event = self.env["event.event"].create(
                {
                    "name": "Test Event",
                    "date_begin": FieldsDatetime.to_string(datetime.now()),
                    "date_end": FieldsDatetime.to_string(
                        datetime.now() + timedelta(days=2)
                    ),
                }
            )
            attendee = self.env["event.registration"].create(
                {
                    "name": "Test Registration",
                    "event_id": event.id,
                    "state": "done",
                }
            )
            self.assertEqual(attendee.date_closed, datetime.now())

            attendee.action_set_done()
            message = "<p>Attended on 5/3/25</p>"
            self.assertTrue(
                message in attendee.message_ids.mapped("body"),
                'Expected a "Attended on 5/3/25" message in the chatter.',
            )
            self.assertEqual(
                attendee.message_ids.mapped("body").count(message),
                1,
                "Logged message when marked as attended.",
            )

            attendee.action_set_done()
            self.assertEqual(
                attendee.message_ids.mapped("body").count(message),
                2,
                "Logged message when marked as attended again.",
            )

        with self.mock_datetime_and_now("2025-05-04 17:00:00"):
            attendee.action_set_done()
            new_message = "<p>Attended on 5/4/25</p>"
            self.assertTrue(
                new_message in attendee.message_ids.mapped("body"),
                'Expected a "Attended on 5/4/25" message in the chatter.',
            )
            self.assertEqual(
                attendee.message_ids.mapped("body").count(new_message),
                1,
                "Logged a new message when marked as attended on a different day.",
            )

    @users("user_eventmanager")
    def test_registration_partner_sync(self):
        test_email = '"Nibbler In Space" <nibbler@futurama.example.com>'
        test_phone = "0456001122"
        test_phone_fmt = "+32456001122"

        event = self.env["event.event"].browse(self.event_0.ids)
        customer = self.env["res.partner"].browse(self.event_customer.id)

        event.write(
            {
                "registration_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": customer.id,
                        },
                    )
                ]
            }
        )
        new_reg = event.registration_ids[0]
        self.assertEqual(new_reg.partner_id, customer)
        self.assertEqual(new_reg.name, customer.name)
        self.assertEqual(new_reg.email, customer.email)
        self.assertEqual(
            new_reg._phone_get_number().number, customer._phone_get_number().number
        )

        event.write(
            {
                "registration_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": customer.id,
                            "name": "Nibbler In Space",
                            "email": test_email,
                        },
                    )
                ]
            }
        )
        new_reg = event.registration_ids.sorted()[0]
        self.assertEqual(new_reg.partner_id, customer)
        self.assertEqual(
            new_reg.name,
            "Nibbler In Space",
            "Registration should take user input over computed partner value",
        )
        self.assertEqual(
            new_reg.email,
            test_email,
            "Registration should take user input over computed partner value",
        )
        self.assertEqual(
            new_reg._phone_get_number().number,
            customer._phone_get_number().number,
            "Registration should take partner value if not user input",
        )

        event.write(
            {
                "registration_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Nibbler In Space",
                            "phone_ids": [
                                Command.create(
                                    {"number": test_phone, "type": "landline"}
                                )
                            ],
                        },
                    )
                ]
            }
        )
        new_reg = event.registration_ids.sorted()[0]
        self.assertEqual(new_reg.name, "Nibbler In Space")
        self.assertEqual(new_reg.email, False)
        self.assertEqual(new_reg._phone_get_number().number, test_phone_fmt)
        new_reg.write({"partner_id": customer.id})
        self.assertEqual(new_reg.partner_id, customer)
        self.assertEqual(new_reg.name, "Nibbler In Space")
        self.assertEqual(new_reg.email, customer.email)
        self.assertEqual(new_reg._phone_get_number().number, test_phone_fmt)

    @users("user_eventmanager")
    def test_registration_partner_sync_company(self):
        event = self.env["event.event"].browse(self.event_0.ids)
        customer = self.env["res.partner"].browse(self.event_customer.id)

        company = (
            self.env["res.partner"]
            .sudo()
            .create(
                {
                    "name": "Customer Company",
                    "is_company": True,
                    "type": "other",
                }
            )
        )
        customer.sudo().write({"type": "invoice", "parent_id": company.id})
        contact = (
            self.env["res.partner"]
            .sudo()
            .create(
                {
                    "name": "ContactName",
                    "parent_id": company.id,
                    "type": "contact",
                    "email": "ContactEmail <contact.email@test.example.com>",
                    "phone_ids": [
                        Command.create({"number": "+32456998877", "type": "landline"})
                    ],
                }
            )
        )

        event.write(
            {
                "registration_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": customer.id,
                        },
                    )
                ]
            }
        )
        new_reg = event.registration_ids[0]
        self.assertEqual(new_reg.partner_id, customer)
        self.assertEqual(new_reg.name, contact.name)
        self.assertEqual(new_reg.email, contact.email)
        self.assertEqual(
            new_reg._phone_get_number().number, contact._phone_get_number().number
        )


@tagged("event_registration", "phone_number")
class TestEventRegistrationPhone(EventCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_event_address = cls.env["res.partner"].create(
            {
                "city": "Gandhinagar",
                "country_id": cls.env.ref("base.in").id,
                "name": "Odoo In",
                "zip": "382007",
            }
        )
        cls.test_event = cls.env["event.event"].create(
            {
                "address_id": cls.test_event_address.id,
                "company_id": cls.company_admin.id,
                "date_begin": datetime(2023, 6, 5, 8, 0, 0),
                "date_end": datetime(2023, 6, 8, 18, 0, 0),
                "name": "Test Phone Format",
            }
        )

    @users("user_eventregistrationdesk")
    def test_assert_initial_values(self):
        customer = self.event_customer.with_env(self.env)
        customer2 = self.event_customer2.with_env(self.env)
        event = self.test_event.with_env(self.env)

        self.assertEqual(customer._phone_get_number().number, "0485112233")
        self.assertEqual(customer2._phone_get_number().number, "0456987654")

        self.assertEqual(event.company_id.country_id, self.env.ref("base.be"))
        self.assertEqual(event.country_id, self.env.ref("base.in"))

    @users("user_eventregistrationdesk")
    def test_registration_form_phone(self):
        event = self.test_event.with_user(self.env.user)

        reg_form = Form(self.env["event.registration"])
        reg_form.event_id = event
        reg_form.name = "Phone Form"
        reg_form.phone_ids.add(
            self.env["phone.number"].create({"number": "+917200000000"})
        )
        registration = reg_form.save()
        self.assertEqual(registration._phone_get_number().number, "+917200000000")

    @users("user_eventregistrationdesk")
    def test_registration_phone_format(self):
        event = self.test_event.with_user(self.env.user)

        sources = [
            (self.event_customer.id, None),
            (self.event_customer2.id, None),
            (self.event_customer2.id, "0456001122"),
            (False, "0456778899"),
            (False, "7200000000"),
            (False, "+917200000088"),
        ]
        expected = [
            "0485112233",
            "0456987654",
            "+32456001122",
            "0456778899",
            "+917200000000",
            "+917200000088",
        ]
        for (partner_id, phone), exp_phone in zip(sources, expected, strict=True):
            with self.subTest(partner_id=partner_id, phone=phone):
                create_vals = {
                    "event_id": event.id,
                    "partner_id": partner_id,
                }
                if phone is not None:
                    create_vals["phone_ids"] = [
                        Command.create({"number": phone, "type": "landline"})
                    ]
                reg = self.env["event.registration"].create(create_vals)
                self.assertEqual(reg._phone_get_number().number, exp_phone)

        self.test_event.write({"address_id": False})
        sources = [
            (self.event_customer.id, None),
            (self.event_customer2.id, None),
            (self.event_customer2.id, "0456001133"),
            (False, "0456778800"),
            (False, "7200000011"),
            (False, "+917200000099"),
        ]
        expected = [
            "0485112233",
            "0456987654",
            "+32456001133",
            "+32456778800",
            "7200000011",
            "+917200000099",
        ]
        for (partner_id, phone), exp_phone in zip(sources, expected, strict=True):
            with self.subTest(partner_id=partner_id, phone=phone):
                create_vals = {
                    "event_id": event.id,
                    "partner_id": partner_id,
                }
                if phone is not None:
                    create_vals["phone_ids"] = [
                        Command.create({"number": phone, "type": "landline"})
                    ]
                reg = self.env["event.registration"].create(create_vals)
                self.assertEqual(reg._phone_get_number().number, exp_phone)


@tagged("event_ticket")
class TestEventTicketData(TestEventInternalsCommon):
    @freeze_time("2020-01-31 10:00:00")
    @users("user_eventmanager")
    def test_event_ticket_fields(self):
        INITIAL_TICKET_SEATS_MAX = 30
        event = self.event_0.with_user(self.env.user)
        event.write(
            {
                "event_ticket_ids": [
                    (5, 0),
                    (
                        0,
                        0,
                        {
                            "name": "First Ticket",
                            "seats_max": INITIAL_TICKET_SEATS_MAX,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Second Ticket",
                            "start_sale_datetime": datetime(2020, 1, 10, 0, 0, 0),
                            "end_sale_datetime": datetime(2020, 2, 10, 23, 59, 59),
                        },
                    ),
                ],
            }
        )
        first_ticket = event.event_ticket_ids.filtered(
            lambda t: t.name == "First Ticket"
        )
        second_ticket = event.event_ticket_ids.filtered(
            lambda t: t.name == "Second Ticket"
        )

        self.assertTrue(first_ticket.seats_limited)
        self.assertTrue(first_ticket.sale_available)
        self.assertFalse(first_ticket.is_expired)

        self.assertFalse(second_ticket.seats_limited)
        self.assertTrue(second_ticket.sale_available)
        self.assertFalse(second_ticket.is_expired)
        second_ticket.write({"end_sale_datetime": datetime(2020, 1, 20, 23, 59, 59)})
        self.assertFalse(second_ticket.sale_available)
        self.assertTrue(second_ticket.is_expired)
        second_ticket.write(
            {
                "start_sale_datetime": datetime(2020, 2, 10, 0, 0, 0),
                "end_sale_datetime": datetime(2020, 2, 20, 23, 59, 59),
            }
        )
        self.assertFalse(second_ticket.sale_available)
        self.assertFalse(second_ticket.is_expired)
        second_ticket.write(
            {
                "start_sale_datetime": datetime(2020, 1, 31, 0, 0, 0),
                "end_sale_datetime": datetime(2020, 2, 20, 23, 59, 59),
            }
        )
        self.assertTrue(second_ticket.sale_available)
        self.assertTrue(second_ticket.is_launched)
        self.assertFalse(second_ticket.is_expired)
        with self.assertRaises(exceptions.UserError):
            second_ticket.write(
                {"end_sale_datetime": datetime(2020, 1, 20, 23, 59, 59)}
            )

        second_ticket.write({"start_sale_datetime": datetime(2020, 1, 31, 11, 0, 0)})
        self.assertFalse(second_ticket.sale_available)
        self.assertFalse(second_ticket.is_launched)

        second_ticket.write(
            {
                "start_sale_datetime": datetime(2020, 1, 31, 7, 0, 0),
                "end_sale_datetime": datetime(2020, 2, 27, 13, 0, 0),
            }
        )

        self.assertTrue(second_ticket.sale_available)
        self.assertTrue(second_ticket.is_launched)
        self.assertFalse(second_ticket.is_expired)

        second_ticket.write({"end_sale_datetime": datetime(2020, 1, 31, 9, 0, 0)})

        self.assertFalse(second_ticket.sale_available)
        self.assertTrue(second_ticket.is_expired)

        reg_draft_multiple = self.env["event.registration"].create(
            [
                {
                    "event_id": event.id,
                    "name": f"reg_draft #{idx}",
                    "event_ticket_id": first_ticket.id,
                }
                for idx in range(3)
            ]
        )
        reg_draft_multiple.state = "draft"
        reg_draft = reg_draft_multiple[0]

        reg_open = self.env["event.registration"].create(
            {
                "event_id": event.id,
                "name": "reg_open",
                "event_ticket_id": first_ticket.id,
            }
        )

        reg_done = self.env["event.registration"].create(
            {
                "event_id": event.id,
                "name": "reg_done",
                "event_ticket_id": first_ticket.id,
            }
        )
        reg_done.action_set_done()

        self.assertEqual(first_ticket.seats_reserved, 1)
        self.assertEqual(first_ticket.seats_used, 1)
        self.assertEqual(first_ticket.seats_available, INITIAL_TICKET_SEATS_MAX - 2)

        reg_done.action_archive()
        self.assertEqual(first_ticket.seats_used, 0)
        self.assertEqual(first_ticket.seats_available, INITIAL_TICKET_SEATS_MAX - 1)

        reg_open.action_archive()
        self.assertEqual(first_ticket.seats_reserved, 0)
        self.assertEqual(first_ticket.seats_available, INITIAL_TICKET_SEATS_MAX)

        reg_open.action_unarchive()
        self.assertEqual(first_ticket.seats_reserved, 1)
        self.assertEqual(first_ticket.seats_available, INITIAL_TICKET_SEATS_MAX - 1)

        reg_done.action_unarchive()
        self.assertEqual(first_ticket.seats_used, 1)
        self.assertEqual(first_ticket.seats_available, INITIAL_TICKET_SEATS_MAX - 2)

        reg_open.action_archive()
        first_ticket.write({"seats_max": 1})

        with self.assertRaises(exceptions.ValidationError):
            reg_open.action_unarchive()

        self.assertEqual(event.seats_available, 0)
        with self.assertRaises(exceptions.ValidationError):
            self.env["event.registration"].create(
                {
                    "event_id": event.id,
                    "name": "New registration with auto confirm",
                    "event_ticket_id": first_ticket.id,
                }
            )

        with self.assertRaises(exceptions.ValidationError):
            reg_draft.write({"state": "open"})


@tagged("event_event")
class TestEventTypeData(TestEventInternalsCommon):
    @users("user_eventmanager")
    def test_event_type_fields(self):
        event_type = self.env["event.type"].create(
            {
                "name": "Testing fields computation",
                "has_seats_limitation": True,
                "seats_max": 30,
            }
        )
        self.assertTrue(event_type.has_seats_limitation)
        self.assertEqual(event_type.seats_max, 30)

        event_type.write({"has_seats_limitation": False})
        self.assertFalse(event_type.has_seats_limitation)
        self.assertEqual(event_type.seats_max, 0)


class TestEventMessageAccess(EventCase):
    def test_desk_posting_is_one_rule_both_ways(self):
        events = self.env["event.event"].create(
            [
                {
                    "name": f"Event {index}",
                    "date_begin": datetime(2026, 1, 1, 10),
                    "date_end": datetime(2026, 1, 2, 10),
                }
                for index in range(2)
            ]
        )
        for user in (
            self.user_eventregistrationdesk,
            self.user_eventuser,
            self.user_eventmanager,
            self.user_employee,
        ):
            for operation in ("read", "create", "write"):
                with self.subTest(user=user.login, operation=operation):
                    per_record, by_domain = mail_access_both_ways(
                        events.with_user(user), operation
                    )
                    self.assertEqual(by_domain, per_record)
        per_record, __ = mail_access_both_ways(
            events.with_user(self.user_eventregistrationdesk), "create"
        )
        self.assertEqual(per_record, set(events.ids))
