import html
import re

from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged, users

from odoo.addons.calendar.tests.booking.common import AppointmentCommon
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.project.tests.test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectAppointmentTask(TestProjectCommon, AppointmentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.project = cls.env["project.project"].create(
            {
                "name": "Project Test APT",
                "company_id": cls.env.company.id,
            }
        )

        cls.test_user_1 = mail_new_test_user(
            cls.env,
            login="test1",
            name="Test User 1",
            email="test1@example.com",
            groups="base.group_user",
        )
        cls.test_user_2 = mail_new_test_user(
            cls.env,
            login="test2",
            name="Test User 2",
            email="test2@example.com",
            groups="base.group_user",
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Project Test APT Product",
                "company_id": cls.env.company.id,
                "project_id": cls.project.id,
                "type": "service",
                "list_price": 100,
                "service_policy": "ordered_prepaid",
                "service_tracking": "task_global_project",
                "service_type": "manual",
            }
        )

        paid_apt_common_values = {
            "appointment_tz": "UTC",
            "has_payment_step": True,
            "min_schedule_hours": 1.0,
            "max_schedule_days": 2,
            "product_id": cls.product.id,
            "slot_ids": [
                Command.create(
                    {
                        "weekday": str(cls.reference_monday.isoweekday()),
                        "start_hour": 14,
                        "end_hour": 17,
                    }
                )
            ],
            "allow_guests": True,
        }

        cls.appointment_users, cls.appointment_resources = cls.env[
            "appointment.type"
        ].create(
            [
                {
                    "name": "Test Paid Appointment Type - Users",
                    "schedule_based_on": "users",
                    "staff_user_ids": [(4, cls.staff_user_bxls.id)],
                    **paid_apt_common_values,
                },
                {
                    "name": "Test Paid Appointment Type - Resource",
                    "manage_capacity": True,
                    "schedule_based_on": "resources",
                    **paid_apt_common_values,
                },
            ]
        )

        cls.resource_1, cls.resource_2 = cls.env["resource.resource"].create(
            [
                {
                    "appointment_type_ids": cls.appointment_resources.ids,
                    "capacity": 3,
                    "name": "APT Resource 1",
                },
                {
                    "appointment_type_ids": cls.appointment_resources.ids,
                    "capacity": 2,
                    "name": "APT Resource 2",
                    "booking_exclusive": False,
                },
            ]
        )

        cls.start_slot = cls.reference_monday.replace(hour=14)
        cls.stop_slot = cls.reference_monday.replace(hour=15)

        (
            cls.appointment_question_single_line_text,
            cls.appointment_question_dropdown,
            cls.appointment_question_radio,
            cls.appointment_question_checkbox,
        ) = cls.env["survey.question"].create(
            [
                {
                    "appointment_type_ids": cls.appointment_users.ids,
                    "title": "How are you ?",
                    "question_type": "char_box",
                },
                {
                    "appointment_type_ids": cls.appointment_users.ids,
                    "title": "How do you feel?",
                    "question_type": "dropdown",
                    "suggested_answer_ids": [
                        Command.create({"value": name})
                        for name in ["Happy", "Sad", "Neutral"]
                    ],
                },
                {
                    "appointment_type_ids": cls.appointment_users.ids,
                    "title": "Don't answer this",
                    "question_type": "simple_choice",
                    "suggested_answer_ids": [
                        Command.create({"value": name})
                        for name in ["Ok", "Not Ok", "Maybe Ok"]
                    ],
                },
                {
                    "appointment_type_ids": cls.appointment_users.ids,
                    "title": "Select multiple",
                    "question_type": "multiple_choice",
                    "suggested_answer_ids": [
                        Command.create({"value": name})
                        for name in ["odoo", "oqoo", "opoo", "oboo"]
                    ],
                },
            ]
        )

    @freeze_time("2022-02-13 20:00:00")
    @users("apt_manager")
    def test_project_user_appointment_type_task_population_on_confirmed_so(self):
        appointment_type = self.appointment_users

        appointment_answer_single_line_text_input_values = {
            "question_id": self.appointment_question_single_line_text.id,
            "value_char_box": "I am <strong>Good</strong> & ready",
            "answer_type": "char_box",
        }
        appointment_answer_dropdown_input_values = {
            "question_id": self.appointment_question_dropdown.id,
            "answer_type": "suggestion",
            "suggested_answer_id": self.appointment_question_dropdown.suggested_answer_ids.filtered(
                lambda a: a.value == "Happy"
            ).id,
        }
        appointment_answer_checkbox_input_values = [
            {
                "question_id": self.appointment_question_checkbox.id,
                "answer_type": "suggestion",
                "suggested_answer_id": answer.id,
            }
            for answer in self.appointment_question_checkbox.suggested_answer_ids
            if answer.value != "odoo"
        ]

        user_answers = {
            self.appointment_question_single_line_text.id: "I am <strong>Good</strong> & ready",
            self.appointment_question_dropdown.id: "Happy",
            self.appointment_question_radio.id: "",
            self.appointment_question_checkbox.id: ["oqoo", "opoo", "oboo"],
        }

        booking_values = {
            "appointment_type_id": appointment_type.id,
            "appointment_response_ids": [
                Command.create(
                    {
                        "appointment_type_id": appointment_type.id,
                        "predefined_question_ids": [
                            Command.set(appointment_type.question_ids.ids)
                        ],
                        "user_input_line_ids": [
                            Command.create(
                                appointment_answer_single_line_text_input_values
                            ),
                            Command.create(appointment_answer_dropdown_input_values),
                        ]
                        + [
                            Command.create(values)
                            for values in appointment_answer_checkbox_input_values
                        ],
                    }
                )
            ],
            "booking_line_ids": [
                Command.create(
                    {
                        "appointment_user_id": self.staff_user_bxls.id,
                        "capacity_reserved": 1,
                        "capacity_used": 1,
                    }
                )
            ],
            "partner_id": self.apt_manager.partner_id.id,
            "product_id": self.product.id,
            "staff_user_id": self.staff_user_bxls.id,
            "start": self.start_slot,
            "stop": self.stop_slot,
            "guest_ids": [
                self.test_user_1.partner_id.id,
                self.test_user_2.partner_id.id,
            ],
        }
        calendar_booking = self.env["calendar.booking"].create(booking_values)
        self.appointment_question_single_line_text.active = False

        sale_order = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": calendar_booking.partner_id.id,
                    "company_id": self.env.company.id,
                }
            )
        )
        self.assertFalse(
            calendar_booking._filter_unavailable_bookings(),
            "No unavailable booking should be found",
        )

        cart_values = sale_order._cart_add(
            product_id=appointment_type.product_id.id,
            quantity=1,
            calendar_booking_id=calendar_booking.id,
        )
        self.assertEqual(
            cart_values["quantity"],
            1,
            "Cart should successfully add 1 product (the appointment)",
        )

        sale_order_line = sale_order.line_ids.filtered(
            lambda line: line.id == cart_values["line_id"]
        )
        self.assertTrue(
            sale_order_line,
            "Sale order line should be created after adding the product to the cart",
        )
        self.assertEqual(
            sale_order_line.calendar_booking_ids,
            calendar_booking,
            "Sale order line should be linked to the calendar booking",
        )
        self.assertFalse(sale_order_line.calendar_event_id)

        sale_order.action_confirm()
        task = sale_order_line.task_id
        event = task.calendar_event_id
        self.assertTrue(task, "Task should be created after confirming the sale order")
        self.assertTrue(
            event, "Calendar event should be created after confirming the sale order"
        )
        self.assertEqual(
            event,
            calendar_booking.calendar_event_id,
            "Calendar event of the task should be linked to the calendar booking",
        )
        self.assertEqual(
            task.user_ids.ids,
            calendar_booking.staff_user_id.ids,
            "Staff users of the booking should be added as users on the task",
        )
        self.assertEqual(
            task.planned_hours,
            event.duration,
            "Planned hours of the task should be equal to the duration of the event",
        )
        self.assertEqual(
            task.date_start,
            event.start,
            "Planned date begin of the task should be equal to the start of the event",
        )
        self.assertEqual(
            task.date_end,
            event.stop,
            "Date deadline of the task should be equal to the stop of the event",
        )

        followers_ids = set(task.message_partner_ids.ids)
        followers_ids.difference_update(
            {self.staff_user_bxls.partner_id.id, self.apt_manager.partner_id.id}
        )
        self.assertEqual(
            followers_ids,
            set(calendar_booking.guest_ids.ids),
            "Invited guests should be followers of the task",
        )

        questions = calendar_booking.appointment_response_ids.predefined_question_ids

        reg_pattern = r"<dt><h3>(.*?)<\/h3><\/dt>[\s\S]*?<dd>(.*?)<\/dd>"
        matches = re.findall(reg_pattern, str(task.description))

        self.assertEqual(len(matches), len(questions))
        self.assertIn("&lt;strong&gt;Good&lt;/strong&gt;", task.description)
        questions_by_title = questions.grouped("title")
        for match in matches:
            task_question_name, task_answer_value = map(html.unescape, match)
            question = questions_by_title.get(task_question_name, questions.browse())
            self.assertTrue(
                question,
                f"Question {task_question_name} not found in description of task",
            )

            answer_value = user_answers.get(question.id)
            if not answer_value:
                self.assertEqual(
                    task_answer_value,
                    "/",
                    "When no answer was provided by user, the value should be '/'",
                )
            elif question.question_type == "multiple_choice":
                self.assertEqual(
                    set(task_answer_value.split(", ")),
                    set(answer_value),
                    "For multiple answers, the values should be comma-separated",
                )
            else:
                self.assertEqual(
                    task_answer_value,
                    answer_value,
                    "The answer value should be equal to the value provided by the user",
                )

    @freeze_time("2022-02-13 20:00:00")
    def test_project_resource_appointment_type_task_population_on_confirmed_so(self):
        appointment_type = self.appointment_resources

        booking_values = {
            "appointment_type_id": appointment_type.id,
            "partner_id": self.partner_1.id,
            "product_id": self.product.id,
            "name": "Project Appointment Booking Resource test",
            "booking_line_ids": [
                Command.create(
                    {
                        "resource_id": self.resource_1.id,
                        "capacity_reserved": 1,
                        "capacity_used": 2,
                    }
                ),
                Command.create(
                    {
                        "resource_id": self.resource_2.id,
                        "capacity_reserved": 1,
                    }
                ),
            ],
            "start": self.start_slot,
            "stop": self.stop_slot,
        }
        calendar_booking = self.env["calendar.booking"].create(booking_values)

        sale_order = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": self.partner_1.id,
                    "company_id": self.env.company.id,
                }
            )
        )
        self.assertFalse(
            calendar_booking._filter_unavailable_bookings(),
            "No unavailable booking should be found",
        )

        cart_values = sale_order._cart_add(
            product_id=appointment_type.product_id.id,
            quantity=1,
            calendar_booking_id=calendar_booking.id,
        )
        self.assertEqual(
            cart_values["quantity"],
            1,
            "Cart should successfully add 1 product (the appointment)",
        )

        sale_order_line = sale_order.line_ids.filtered(
            lambda line: line.id == cart_values["line_id"]
        )
        self.assertTrue(
            sale_order_line,
            "Sale order line should be created after adding the product to the cart",
        )
        self.assertEqual(
            sale_order_line.calendar_booking_ids,
            calendar_booking,
            "Sale order line should be linked to the calendar booking",
        )
        self.assertFalse(sale_order_line.calendar_event_id)

        sale_order.action_confirm()
        task = sale_order_line.task_id
        event = task.calendar_event_id
        self.assertTrue(task, "Task should be created after confirming the sale order")
        self.assertTrue(
            event, "Calendar event should be created after confirming the sale order"
        )
        self.assertEqual(
            event,
            calendar_booking.calendar_event_id,
            "Calendar event of the task should be linked to the calendar booking",
        )
        self.assertEqual(
            set(task.tag_ids.mapped("name")),
            set(calendar_booking.booking_line_ids.resource_id.mapped("name")),
            "Selected resources should be added as tags on the task",
        )
        self.assertEqual(
            task.planned_hours,
            event.duration,
            "Planned hours of the task should be equal to the duration of the event",
        )
        self.assertEqual(
            task.date_start,
            event.start,
            "Planned date begin of the task should be equal to the start of the event",
        )
        self.assertEqual(
            task.date_end,
            event.stop,
            "Date deadline of the task should be equal to the stop of the event",
        )
