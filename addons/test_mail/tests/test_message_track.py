from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import Form, counting_statements, new_test_user, tagged, users
from odoo.tools import mute_logger

from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.test_mail.data.test_mail_data import MAIL_TEMPLATE


@tagged("mail_track")
class TestTracking(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        record = (
            cls.env["mail.test.ticket"]
            .with_user(cls.user_employee)
            .with_context(cls._test_context)
            .create(
                {
                    "name": "Test",
                }
            )
        )
        cls.record = record.with_context(mail_notrack=False)

    def test_message_track_author(self):
        with self.mock_mail_gateway():
            self.record._track_set_author(self.partner_admin)
            self.record.write(
                {
                    "customer_id": self.partner_employee.id,
                }
            )
            self.flush_tracking()

        self.assertEqual(len(self.record.message_ids), 1)
        self.assertEqual(len(self.record.message_ids.sudo().tracking_value_ids), 1)

        self.assertEqual(self.record.message_ids.author_id, self.partner_admin)

    def test_message_track_monetary_currency(self):
        record = (
            self.env["mail.test.track.monetary"]
            .with_context(
                self._test_context,
                mail_notrack=False,
            )
            .create(
                {
                    "company_id": self.env.company.id,
                    "revenue": 100.0,
                }
            )
        )
        self.flush_tracking()
        with self.mock_mail_gateway():
            record.write({"revenue": 250.0})
            self.flush_tracking()

        tracking = record.message_ids.sudo().tracking_value_ids.filtered(
            lambda t: t.field_id.name == "revenue"
        )
        self.assertEqual(len(tracking), 1)
        self.assertEqual(tracking.currency_id, self.env.company.currency_id)
        self.assertEqual(tracking.old_value_float, 100.0)
        self.assertEqual(tracking.new_value_float, 250.0)

    @users("employee")
    def test_message_track_default_message(self):

        record = (
            self.env["mail.test.track"]
            .with_context(self._test_context)
            .create(
                {
                    "name": "Test",
                    "track_enable_default_log": True,
                }
            )
            .with_context(mail_notrack=False)
        )
        self.flush_tracking()

        with self.mock_mail_gateway():
            record.user_id = self.user_admin
            self.flush_tracking()

        messages = record.message_ids
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages.body,
            '<p>There was a change on Test for fields "user_id"</p>',
            "Default message should be used",
        )

        with self.mock_mail_gateway():
            record._track_set_log_message("Hi")
            record.user_id = False
            self.flush_tracking()

        messages = record.message_ids - messages
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages.body,
            "<p>Hi</p>",
            "_track_set_log_message should take priority over default message",
        )

    @users("employee")
    def test_message_track_filter_for_display(self):
        field_dname = "Responsible"
        field_type = "many2one"
        original_user = self.user_admin
        new_user = self.user_employee

        records = self.env["mail.test.track"].create(
            [
                {
                    "name": "TestTrack Hide User Field",
                    "user_id": original_user.id,
                    "track_fields_tofilter": "user_id",
                },
                {
                    "name": "TestTrack Show All Fields",
                    "user_id": original_user.id,
                    "track_fields_tofilter": "",
                },
            ]
        )
        self.flush_tracking()

        records.write({"user_id": new_user.id})
        self.flush_tracking()

        for record in records:
            self.assertEqual(
                len(record.message_ids),
                2,
                "Should be a creation message and a tracking message",
            )
            self.assertTracking(
                record.message_ids[0],
                [("user_id", "many2one", original_user, new_user)],
            )
        message_0 = records[0].message_ids[0]
        formatted = Store().add(message_0).get_result()["mail.message"][0]
        self.assertEqual(
            formatted["trackingValues"], [], "Hidden values should not be formatted"
        )
        mail_render = records[0]._notify_by_email_prepare_rendering_context(
            message_0, {}
        )
        self.assertEqual(mail_render["tracking_values"], [])

        message_1 = records[1].message_ids[0]
        formatted = Store().add(message_1).get_result()["mail.message"][0]
        self.assertEqual(len(formatted["trackingValues"]), 1)
        self.assertDictEqual(
            formatted["trackingValues"][0],
            {
                "id": message_1.sudo().tracking_value_ids.id,
                "fieldInfo": {
                    "changedField": field_dname,
                    "currencyId": False,
                    "floatPrecision": None,
                    "fieldType": field_type,
                    "isPropertyField": False,
                },
                "newValue": new_user.display_name,
                "oldValue": original_user.display_name,
            },
        )
        mail_render = records[1]._notify_by_email_prepare_rendering_context(
            message_1, {}
        )
        self.assertEqual(
            mail_render["tracking_values"],
            [(field_dname, original_user.display_name, new_user.display_name)],
        )

    @users("employee")
    def test_message_track_filter_for_display_search(self):
        original_user = self.user_admin
        new_user = self.user_employee
        records = self.env["mail.test.track"].create(
            [
                {
                    "name": "TestTrack Hide User Field",
                    "user_id": original_user.id,
                    "track_fields_tofilter": "user_id",
                },
                {
                    "name": "TestTrack Show All Fields",
                    "user_id": original_user.id,
                    "track_fields_tofilter": "",
                },
            ]
        )
        self.flush_tracking()
        records.write({"user_id": new_user.id})
        self.flush_tracking()

        for record, expected in zip(records, (0, 1), strict=True):
            with self.subTest(record=record.name):
                found = self.env["mail.message"]._message_fetch(
                    domain=None, thread=record, search_term=new_user.display_name
                )["messages"]
                self.assertEqual(len(found), expected)

        formatted = Store().add(records.message_ids).get_result()["mail.message"]
        tracking_by_message = {
            values["id"]: values["trackingValues"] for values in formatted
        }
        self.assertEqual(tracking_by_message[records[0].message_ids[0].id], [])
        self.assertEqual(len(tracking_by_message[records[1].message_ids[0].id]), 1)

    @users("employee")
    def test_message_track_format_once_per_page(self):
        record = self.env["mail.test.track"].create({"name": "Paged"})
        self.flush_tracking()
        for user in (self.user_admin, self.user_employee) * 15:
            record.user_id = user
            self.flush_tracking()
        messages = record.message_ids.filtered(lambda m: m.sudo().tracking_value_ids)
        self.assertEqual(len(messages), 30)
        TrackingValue = self.registry["mail.tracking.value"]
        original = TrackingValue._tracking_value_format
        calls = []

        def traced(values_self):
            calls.append(len(values_self))
            return original(values_self)

        self.env.invalidate_all()
        with patch.object(TrackingValue, "_tracking_value_format", traced):
            with counting_statements(self.cr) as counted:
                result = Store().add(messages).get_result()["mail.message"]
                statements = counted.count
        self.assertEqual(calls, [30])
        self.assertTrue(all(len(values["trackingValues"]) == 1 for values in result))
        self.assertLess(statements, 60, "formatting a page must not scale per message")

    def test_message_track_message_type(self):
        self.record.message_subscribe(
            partner_ids=[self.user_admin.partner_id.id],
            subtype_ids=[self.env.ref("mail.mt_comment").id],
        )
        mail_templates = self.env["mail.template"].create(
            [
                {
                    "name": f"Template {n}",
                    "subject": f"Template {n}",
                    "model_id": self.env.ref("test_mail.model_mail_test_ticket").id,
                    "body_html": f"<p>Template {n}</p>",
                }
                for n in range(2)
            ]
        )

        def _track_subtype(self, init_values):
            return self.env.ref("mail.mt_note")

        self.patch(self.registry["mail.test.ticket"], "_track_subtype", _track_subtype)

        def _track_template(self, changes):
            if "email_from" in changes:
                return {"email_from": (mail_templates[0], {})}
            elif "container_id" in changes:
                return {
                    "container_id": (
                        mail_templates[1],
                        {"message_type": "notification"},
                    )
                }
            return {}

        self.patch(
            self.registry["mail.test.ticket"], "_track_template", _track_template
        )

        container = self.env["mail.test.container"].create({"name": "Container"})

        with self.mock_mail_gateway():
            self.record.email_from = "test@test.lan"
            self.flush_tracking()

        first_message = self.record.message_ids.filtered(
            lambda message: message.subject == "Template 0"
        )
        self.assertEqual(
            len(self.record.message_ids),
            2,
            "Should be one change message and one automated template",
        )
        self.assertEqual(first_message.message_type, "auto_comment")

        with self.mock_mail_gateway(mail_unlink_sent=False):
            self.record.container_id = container
            self.flush_tracking()

        second_message = self.record.message_ids.filtered(
            lambda message: message.subject == "Template 1"
        )
        self.assertEqual(
            len(self.record.message_ids),
            4,
            "Should have added one change message and one automated template",
        )
        self.assertEqual(second_message.message_type, "notification")

    def test_message_track_keeps_a_field_whose_old_value_was_unlinked(self):
        container_a, container_b = (
            self.env["mail.test.container"]
            .with_context(mail_create_nosubscribe=True)
            .create([{"name": "Container A"}, {"name": "Container B"}])
        )
        self.record.container_id = container_a
        self.flush_tracking()
        self.record.message_ids.unlink()
        container_a_id = container_a.id

        with self.assertLogs(
            "odoo.addons.mail.models.mail_tracking_value", level="WARNING"
        ) as logs:
            self.record.write(
                {"container_id": container_b.id, "email_from": "new@example.com"}
            )
            container_a.unlink()
            self.env.invalidate_all()
            self.flush_tracking()
        self.assertEqual(len(logs.output), 1)
        self.assertIn(str(container_a_id), logs.output[0])

        self.assertEqual(len(self.record.message_ids), 1, "one tracking message")
        tracking = self.record.message_ids.sudo().tracking_value_ids
        self.assertEqual(
            set(tracking.field_id.mapped("name")), {"container_id", "email_from"}
        )
        container_tracking = tracking.filtered(
            lambda track: track.field_id.name == "container_id"
        )
        self.assertEqual(container_tracking.old_value_integer, container_a_id)
        self.assertEqual(container_tracking.old_value_char, "")
        self.assertEqual(container_tracking.new_value_integer, container_b.id)
        self.assertEqual(container_tracking.new_value_char, "Container B")

    def test_message_track_multiple(self):
        container = (
            self.env["mail.test.container"]
            .with_context(mail_create_nosubscribe=True)
            .create({"name": "Container"})
        )
        self.record.name = "Zboub"
        self.record.customer_id = self.user_admin.partner_id
        self.record.user_id = self.user_admin
        self.record.container_id = container
        self.flush_tracking()

        self.assertEqual(
            len(self.record.message_ids), 1, "should have 1 tracking message"
        )
        self.assertEqual(self.record.message_ids.author_id, self.partner_employee)
        self.assertTracking(
            self.record.message_ids[0],
            [
                ("customer_id", "many2one", False, self.user_admin.partner_id),
                ("user_id", "many2one", False, self.user_admin),
                ("container_id", "many2one", False, container),
            ],
        )

    def test_message_track_no_subtype(self):
        customer = self.env["res.partner"].create(
            {"name": "Customer", "email": "cust@example.com"}
        )
        with self.mock_mail_gateway():
            self.record.write(
                {
                    "name": "Test2",
                    "customer_id": customer.id,
                }
            )
            self.flush_tracking()

        self.assertEqual(len(self.record.message_ids), 1)
        self.assertEqual(self.record.message_ids.author_id, self.partner_employee)
        self.assertEqual(
            self.record.message_ids.subtype_id, self.env.ref("mail.mt_note")
        )

        self.assertEqual(self.record.message_ids.partner_ids, self.env["res.partner"])
        self.assertEqual(
            self.record.message_ids.notified_partner_ids, self.env["res.partner"]
        )
        self.assertNotSentEmail()

        self.assertTracking(
            self.record.message_ids,
            [
                ("customer_id", "many2one", False, customer)
            ],
        )

    @users("employee")
    def test_message_track_no_tracking(self):
        record = self.record.with_env(self.env)
        record.write(
            {
                "name": "Tracking or not",
                "count": 32,
            }
        )
        self.flush_tracking()
        self.assertFalse(record.message_ids)

        record.with_context(mail_notrack=True).write(
            {"email_from": "new.from@test.example.com"}
        )
        self.flush_tracking()
        self.assertFalse(record.message_ids)

    def test_message_track_subtype(self):
        self.record.message_subscribe(
            partner_ids=[self.user_admin.partner_id.id],
            subtype_ids=[
                self.env.ref("test_mail.st_mail_test_ticket_container_upd").id
            ],
        )

        container = (
            self.env["mail.test.container"]
            .with_context(mail_create_nosubscribe=True)
            .create({"name": "Container"})
        )
        self.record.write(
            {
                "name": "Test2",
                "email_from": "noone@example.com",
                "container_id": container.id,
            }
        )
        self.flush_tracking()
        self.assertEqual(len(self.record.message_ids), 1)
        self.assertEqual(self.record.message_ids.author_id, self.partner_employee)
        self.assertEqual(
            self.record.message_ids.subtype_id,
            self.env.ref("test_mail.st_mail_test_ticket_container_upd"),
        )

        self.assertEqual(self.record.message_ids.partner_ids, self.env["res.partner"])
        self.assertEqual(
            self.record.message_ids.notified_partner_ids, self.user_admin.partner_id
        )

        self.assertTracking(
            self.record.message_ids,
            [
                ("container_id", "many2one", False, container)
            ],
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_track_template(self):
        self.record.write(
            {
                "mail_template": self.env.ref(
                    "test_mail.mail_test_ticket_tracking_tpl"
                ).id
            }
        )
        self.assertEqual(self.record.message_ids, self.env["mail.message"])

        with self.mock_mail_gateway():
            self.record.write(
                {
                    "name": "Test2",
                    "customer_id": self.user_admin.partner_id.id,
                }
            )
            self.flush_tracking()

        self.assertEqual(
            len(self.record.message_ids),
            2,
            "should have 2 new messages: one for tracking, one for template",
        )

        self.assertEqual(self.record.message_ids[0].author_id, self.partner_employee)
        self.assertEqual(self.record.message_ids[0].subject, "Test Template")
        self.assertEqual(self.record.message_ids[0].body, "<p>Hello Test2</p>")

        self.assertSentEmail(
            self.record.env.user.partner_id,
            [self.partner_admin],
            body="<p>Hello Test2</p>",
        )

        self.assertEqual(
            self.record.message_ids[1].subtype_id, self.env.ref("mail.mt_note")
        )
        self.assertTracking(
            self.record.message_ids[1],
            [
                (
                    "customer_id",
                    "many2one",
                    False,
                    self.user_admin.partner_id,
                )
            ],
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_track_template_at_create(self):

        Model = (
            self.env["mail.test.ticket"]
            .with_user(self.user_employee)
            .with_context(self._test_context)
        )
        Model = Model.with_context(mail_notrack=False)
        with self.mock_mail_gateway():
            record = Model.create(
                {
                    "name": "Test",
                    "customer_id": self.user_admin.partner_id.id,
                    "mail_template": self.env.ref(
                        "test_mail.mail_test_ticket_tracking_tpl"
                    ).id,
                }
            )
            self.flush_tracking()

        self.assertEqual(
            len(record.message_ids), 1, "should have 1 new messages for template"
        )
        self.assertEqual(record.message_ids[0].author_id, self.partner_employee)
        self.assertEqual(record.message_ids[0].subject, "Test Template")
        self.assertEqual(record.message_ids[0].body, "<p>Hello Test</p>")
        self.assertSentEmail(
            self.record.env.user.partner_id,
            [self.partner_admin],
            body="<p>Hello Test</p>",
        )

    @mute_logger(
        "odoo.addons.mail.models.mail_mail",
        "odoo.addons.mail.models.mixin_mail_thread",
        "odoo.addons.mail.models.mixin_mail_gateway",
    )
    def test_message_track_template_at_create_from_message(self):
        test_model = self.env["ir.model"]._get("mail.test.ticket")
        original_sender = self.user_admin.partner_id
        custom_values = {
            "name": "Test",
            "customer_id": original_sender.id,
            "mail_template": self.env.ref("test_mail.mail_test_ticket_tracking_tpl").id,
        }
        self.env["mail.alias"].create(
            {
                "alias_name": "groups",
                "alias_model_id": test_model.id,
                "alias_contact": "everyone",
                "alias_defaults": custom_values,
            }
        )
        record = self.format_and_process(
            MAIL_TEMPLATE,
            '"Sylvie Lelitre" <test.sylvie.lelitre@agrolait.com>',
            "groups@test.mycompany.com",
            target_field="customer_id",
            subject=custom_values["customer_id"],
            target_model="mail.test.ticket",
        )

        with self.mock_mail_gateway(mail_unlink_sent=False):
            self.flush_tracking()

        self.assertEqual(len(record.message_ids), 2)
        messages = list(record.message_ids)
        messages.sort(key=lambda msg: msg.id)
        trigger = messages[0]
        template = messages[1]
        self.assertIn(
            "Please call me as soon as possible this afternoon!", trigger.body
        )
        self.assertIn(f"Hello {custom_values['name']}", template.body)
        self.assertMailMail(
            original_sender,
            "sent",
            author=self.env.ref("base.partner_root"),
            email_values={
                "body_content": f"<p>Hello {custom_values['name']}</p>",
            },
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_message_track_template_create_partner_multicompany(self):
        company1 = self.env["res.company"].create({"name": "company1"})
        self.env.user.write({"company_ids": [(4, company1.id, False)]})
        self.assertNotEqual(self.env.company, company1)

        email_new_partner = "diamonds@rust.com"
        Partner = self.env["res.partner"]
        self.assertFalse(Partner.search([("email", "=", email_new_partner)]))

        template = self.env["mail.template"].create(
            {
                "model_id": self.env["ir.model"]._get("mail.test.track").id,
                "name": "AutoTemplate",
                "subject": "autoresponse",
                "email_from": self.env.user.email_formatted,
                "email_to": "{{ object.email_from }}",
                "body_html": "<div>A nice body</div>",
            }
        )

        def patched_message_track_post_template(*args, **kwargs):
            if args[0]._name == "mail.test.track":
                args[0].message_post_with_source(template)
            return True

        with patch(
            "odoo.addons.mail.models.mixin_mail_thread.MixinMailThread._message_track_post_template",
            patched_message_track_post_template,
        ):
            self.env["mail.test.track"].create(
                {
                    "email_from": email_new_partner,
                    "company_id": company1.id,
                    "user_id": self.env.user.id,
                }
            )
            self.flush_tracking()

        new_partner = Partner.search([("email", "=", email_new_partner)])
        self.assertTrue(new_partner)
        self.assertEqual(new_partner.company_id, company1)

    def test_message_track_template_defaults(self):
        magic_code = "Up-Up-Down-Down-Left-Right-Left-Right-Square-Triangle"

        mt_name_changed = self.env["mail.message.subtype"].create(
            {"name": "MAGIC CODE WOOP WOOP", "description": "SPECIAL CONTENT UNLOCKED"}
        )
        self.env["ir.model.data"].create(
            {
                "name": "mt_name_changed",
                "model": "mail.message.subtype",
                "module": "mail",
                "res_id": mt_name_changed.id,
            }
        )
        mail_template = self.env["mail.template"].create(
            {
                "name": "SPECIAL CONTENT UNLOCKED",
                "subject": "SPECIAL CONTENT UNLOCKED",
                "model_id": self.env.ref("test_mail.model_mail_test_container").id,
                "auto_delete": True,
                "body_html": """<div>WOOP WOOP</div>""",
            }
        )

        ContainerModel = self.registry["mail.test.container"]
        self.assertFalse(hasattr(ContainerModel.name, "tracking"))
        ContainerModel.name.tracking = True
        self.addCleanup(delattr, ContainerModel.name, "tracking")
        self.patch(
            ContainerModel,
            "_track_subtype",
            lambda self, init_values: (
                "mail.mt_name_changed"
                if "name" in init_values and init_values["name"] == magic_code
                else False
            ),
        )
        self.patch(
            ContainerModel,
            "_track_template",
            lambda self, changes: (
                {"name": (mail_template, {"composition_mode": "mass_mail"})}
                if "name" in changes
                else {}
            ),
        )

        test_mail_record = self.env["mail.test.container"].create(
            {
                "name": "Zizizatestmailname",
                "description": "Zizizatestmaildescription",
            }
        )
        test_mail_record.with_context(default_parent_id=2147483647).write(
            {"name": magic_code}
        )


@tagged("mail_track")
class TestTrackingInternals(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.record = (
            cls.env["mail.test.ticket"]
            .with_user(cls.user_employee)
            .create(
                {
                    "name": "Test",
                }
            )
        )
        cls.test_partner = cls.env["res.partner"].create(
            {
                "country_id": cls.env.ref("base.be").id,
                "email": "test.partner@test.example.com",
                "name": "Test Partner",
                "phone_ids": [
                    Command.create({"number": "0456001122", "type": "landline"})
                ],
            }
        )

        cls.properties_linked_records = cls.env["mail.test.ticket"].create(
            [{"name": f"Record {i}"} for i in range(3)]
        )
        cls.properties_parent_1, cls.properties_parent_2 = cls.env[
            "mail.test.track.all.properties.parent"
        ].create(
            [
                {
                    "definition_properties": [
                        {
                            "name": "property_char",
                            "string": "Property Char",
                            "type": "char",
                            "default": "char value",
                        },
                        {"name": "separator", "type": "separator"},
                        {
                            "name": "property_int",
                            "string": "Property Int",
                            "type": "integer",
                            "default": 1337,
                        },
                        {
                            "name": "property_m2o",
                            "string": "Property M2O",
                            "type": "many2one",
                            "default": (
                                cls.properties_linked_records[0].id,
                                cls.properties_linked_records[0].display_name,
                            ),
                            "comodel": "mail.test.ticket",
                        },
                    ],
                },
                {
                    "definition_properties": [
                        {
                            "name": "property_m2m",
                            "string": "Property M2M",
                            "type": "many2many",
                            "default": [
                                (rec.id, rec.display_name)
                                for rec in cls.properties_linked_records
                            ],
                            "comodel": "mail.test.ticket",
                        },
                        {
                            "name": "property_separator",
                            "string": "Separator",
                            "type": "separator",
                        },
                        {
                            "name": "property_tags",
                            "string": "Property Tags",
                            "type": "tags",
                            "default": ["aa", "bb"],
                            "tags": [("aa", "AA", 7), ("bb", "BB", 2), ("cc", "CC", 3)],
                        },
                        {
                            "name": "property_datetime",
                            "string": "Property Datetime",
                            "type": "datetime",
                            "default": "2024-01-02 12:59:01",
                        },
                        {
                            "name": "property_date",
                            "string": "Property Date",
                            "type": "date",
                            "default": "2024-01-03",
                        },
                    ],
                },
            ]
        )
        cls.properties_record_1, cls.properties_record_2 = cls.env[
            "mail.test.track.all"
        ].create(
            [
                {
                    "properties_parent_id": cls.properties_parent_1.id,
                },
                {
                    "properties_parent_id": cls.properties_parent_2.id,
                },
            ]
        )

    @users("employee")
    def test_mail_track_2many(self):
        test_tags = self.env["mail.test.track.all.m2m"].create(
            [
                {
                    "name": "Tag1",
                },
                {
                    "name": "Tag2",
                },
                {
                    "name": "Tag3",
                },
            ]
        )
        test_record = self.env["mail.test.track.all"].create(
            {
                "name": "Test 2Many fields tracking",
            }
        )
        self.flush_tracking()

        last_message = test_record.message_ids[0]
        self.assertFalse(last_message.sudo().tracking_value_ids)

        test_record.write(
            {
                "many2many_field": [(4, test_tags[0].id), (4, test_tags[1].id)],
            }
        )
        self.flush_tracking()
        last_message = test_record.message_ids[0]
        self.assertTracking(
            last_message,
            [
                (
                    "many2many_field",
                    "many2many",
                    "",
                    ", ".join(test_tags[:2].mapped("name")),
                )
            ],
        )

        test_record.write(
            {
                "many2many_field": [(3, test_tags[0].id), (4, test_tags[2].id)],
                "one2many_field": [
                    (0, 0, {"name": "Child1"}),
                    (0, 0, {"name": "Child2"}),
                    (0, 0, {"name": "Child3"}),
                    (0, 0, {"name": False}),
                ],
            }
        )
        child4_tracking = f"Unnamed Sub-model: pseudo tags for tracking ({test_record.one2many_field[3].id})"
        self.flush_tracking()
        last_message = test_record.message_ids[0]
        self.assertTracking(
            last_message,
            [
                (
                    "many2many_field",
                    "many2many",
                    ", ".join(test_tags[:2].mapped("name")),
                    ", ".join((test_tags[1] + test_tags[2]).mapped("name")),
                ),
                (
                    "one2many_field",
                    "one2many",
                    "",
                    f"Child1, Child2, Child3, {child4_tracking}",
                ),
            ],
        )

        test_record.write({"one2many_field": [(3, test_record.one2many_field[0].id)]})
        self.flush_tracking()
        last_message = test_record.message_ids[0]
        self.assertTracking(
            last_message,
            [
                (
                    "one2many_field",
                    "one2many",
                    f"Child1, Child2, Child3, {child4_tracking}",
                    f"Child2, Child3, {child4_tracking}",
                )
            ],
        )

    @users("employee")
    def test_mail_track_all_no2many(self):
        test_record = self.env["mail.test.track.all"].create(
            {
                "company_id": self.env.company.id,
            }
        )
        self.flush_tracking()
        self.assertEqual(test_record.currency_id, self.env.ref("base.USD"))
        messages = test_record.message_ids
        today = fields.Date.today()
        today_dt = fields.Datetime.to_datetime(today)
        now = fields.Datetime.now()

        test_record.write(
            {
                "boolean_field": True,
                "char_field": "char_value",
                "date_field": today,
                "datetime_field": now,
                "float_field": 3.22,
                "float_field_with_digits": 3.00001,
                "html_field": "<p>Html Value</p>",
                "integer_field": 42,
                "many2one_field_id": self.test_partner.id,
                "monetary_field": 42.42,
                "selection_field": "first",
                "text_field": "text_value",
            }
        )
        self.flush_tracking()
        new_message = test_record.message_ids - messages
        self.assertEqual(len(new_message), 1, "Should have generated a tracking value")
        tracking_value_list = [
            ("boolean_field", "boolean", 0, 1),
            ("char_field", "char", False, "char_value"),
            ("date_field", "date", False, today_dt),
            ("datetime_field", "datetime", False, now),
            ("float_field", "float", 0, 3.22),
            ("float_field_with_digits", "float", 0, 3.00001),
            ("integer_field", "integer", 0, 42),
            (
                "many2one_field_id",
                "many2one",
                self.env["res.partner"],
                self.test_partner,
            ),
            ("monetary_field", "monetary", False, (42.42, self.env.ref("base.USD"))),
            ("selection_field", "selection", "", "FIRST"),
            ("text_field", "text", False, "text_value"),
        ]
        self.assertTracking(new_message, tracking_value_list, strict=True)
        formatted_values_all = (
            new_message.sudo().tracking_value_ids._tracking_value_format()
        )
        for (field_name, field_type, _, _), formatted_vals in zip(
            tracking_value_list, formatted_values_all, strict=True
        ):
            currency = (
                self.env.ref("base.USD").id if field_type == "monetary" else False
            )
            precision = None if field_name != "float_field_with_digits" else (10, 8)
            with self.subTest(field_name=field_name):
                self.assertEqual(formatted_vals["fieldInfo"]["currencyId"], currency)
                self.assertEqual(
                    formatted_vals["fieldInfo"]["floatPrecision"], precision
                )

    @users("employee")
    def test_mail_track_compute(self):
        compute_record = self.env["mail.test.track.compute"].create({})
        self.flush_tracking()
        self.assertEqual(len(compute_record.message_ids), 1)
        self.assertEqual(
            len(compute_record.message_ids[0].sudo().tracking_value_ids), 0
        )

        partner_su = (
            self.env["res.partner"]
            .sudo()
            .create(
                {
                    "name": "Foo",
                    "email": "foo@example.com",
                    "phone_ids": [
                        Command.create({"number": "1234567890", "type": "landline"})
                    ],
                }
            )
        )
        compute_record.partner_id = partner_su
        self.flush_tracking()
        self.assertEqual(len(compute_record.message_ids), 2)
        self.assertEqual(
            len(compute_record.message_ids[0].sudo().tracking_value_ids), 4
        )
        self.assertEqual(compute_record.message_ids.author_id, self.partner_employee)
        self.assertTracking(
            compute_record.message_ids[0],
            [
                ("partner_id", "many2one", False, partner_su),
                ("partner_name", "char", False, "Foo"),
                ("partner_email", "char", False, "foo@example.com"),
                ("phone_ids", "many2many", "", "1234567890"),
            ],
        )

        partner_su.write({"name": "Fool"})
        self.flush_tracking()
        self.assertEqual(len(compute_record.message_ids), 3)
        self.assertEqual(
            len(compute_record.message_ids[0].sudo().tracking_value_ids), 1
        )
        self.assertTracking(
            compute_record.message_ids[0],
            [
                ("partner_name", "char", "Foo", "Fool"),
            ],
        )

        partner_su.write(
            {
                "name": "Bar",
                "email": "bar@example.com",
                "phone_ids": [
                    Command.clear(),
                    Command.create({"number": "0987654321", "type": "landline"}),
                ],
            }
        )
        self.assertEqual(compute_record.phone_ids.number, "0987654321")
        self.flush_tracking()
        self.assertEqual(len(compute_record.message_ids), 4)
        self.assertEqual(
            len(compute_record.message_ids[0].sudo().tracking_value_ids), 2
        )
        self.assertTracking(
            compute_record.message_ids[0],
            [
                ("partner_name", "char", "Fool", "Bar"),
                ("partner_email", "char", "foo@example.com", "bar@example.com"),
            ],
        )

    @users("employee")
    def test_mail_track_monetary(self):
        monetary_record = (
            self.env["mail.test.track.monetary"]
            .with_user(self.user_employee)
            .create(
                {
                    "company_id": self.user_employee.company_id.id,
                }
            )
        )
        self.flush_tracking()
        self.assertEqual(len(monetary_record.message_ids), 1)

        monetary_record.write(
            {
                "revenue": 100,
            }
        )
        self.flush_tracking()
        self.assertEqual(len(monetary_record.message_ids), 2)
        self.assertTracking(
            monetary_record.message_ids[0],
            [
                ("revenue", "monetary", 0, (100, self.env.company.currency_id)),
            ],
        )

        monetary_record.write(
            {
                "revenue": 200,
                "company_id": self.company_2.id,
            }
        )
        self.flush_tracking()
        self.assertEqual(len(monetary_record.message_ids), 3)
        self.assertTracking(
            monetary_record.message_ids[0],
            [
                ("revenue", "monetary", 100, (200, self.company_2.currency_id)),
                (
                    "company_currency",
                    "many2one",
                    self.user_employee.company_id.currency_id,
                    self.company_2.currency_id,
                ),
            ],
        )

    def _formatted_tracking_values(self, record):
        warm = record.mapped("message_ids.tracking_value_ids")._tracking_value_format()
        self.env.invalidate_all()
        cold = record.mapped("message_ids.tracking_value_ids")._tracking_value_format()
        self.assertEqual(
            [values["fieldInfo"]["changedField"] for values in warm],
            [values["fieldInfo"]["changedField"] for values in cold],
            "the rendered order must be the same in and out of the ORM cache",
        )
        return warm

    def test_mail_track_properties(self):
        record = self.properties_record_2
        record.properties_parent_id = self.properties_parent_1
        self.flush_tracking()
        formatted_values = self._formatted_tracking_values(record)
        self.assertEqual(len(formatted_values), 5)
        self.assertFalse(formatted_values[0]["fieldInfo"]["isPropertyField"])
        self.assertTrue(all(not f["newValue"] for f in formatted_values[1:]))
        self.assertTrue(
            all(f["fieldInfo"]["isPropertyField"] for f in formatted_values[1:])
        )
        self.assertEqual(
            formatted_values[0]["fieldInfo"]["changedField"], "Properties Parent"
        )
        self.assertEqual(
            formatted_values[1]["fieldInfo"]["changedField"], "Properties: Property M2M"
        )
        self.assertEqual(
            formatted_values[1]["oldValue"], "Record 0, Record 1, Record 2"
        )
        self.assertEqual(
            formatted_values[2]["fieldInfo"]["changedField"],
            "Properties: Property Tags",
        )
        self.assertEqual(formatted_values[2]["oldValue"], "AA, BB")
        self.assertEqual(
            formatted_values[3]["fieldInfo"]["changedField"],
            "Properties: Property Datetime",
        )
        self.assertEqual(formatted_values[3]["oldValue"], "2024-01-02 12:59:01Z")
        self.assertEqual(
            formatted_values[4]["fieldInfo"]["changedField"],
            "Properties: Property Date",
        )
        self.assertEqual(formatted_values[4]["oldValue"], "2024-01-03")

        record = self.properties_record_1
        record.properties_parent_id = self.properties_parent_2
        self.flush_tracking()
        formatted_values = self._formatted_tracking_values(record)
        self.assertEqual(len(formatted_values), 4)
        self.assertFalse(formatted_values[0]["fieldInfo"]["isPropertyField"])
        self.assertTrue(all(not f["newValue"] for f in formatted_values[1:]))
        self.assertTrue(
            all(f["fieldInfo"]["isPropertyField"] for f in formatted_values[1:])
        )
        self.assertEqual(
            formatted_values[0]["fieldInfo"]["changedField"], "Properties Parent"
        )
        self.assertEqual(
            formatted_values[1]["fieldInfo"]["changedField"],
            "Properties: Property Char",
        )
        self.assertEqual(formatted_values[1]["oldValue"], "char value")
        self.assertEqual(
            formatted_values[2]["fieldInfo"]["changedField"], "Properties: Property Int"
        )
        self.assertEqual(formatted_values[2]["oldValue"], 1337)
        self.assertEqual(
            formatted_values[3]["fieldInfo"]["changedField"], "Properties: Property M2O"
        )
        self.assertEqual(formatted_values[3]["oldValue"], "Record 0")

        with self.mock_mail_gateway():
            record.properties_parent_id = self.properties_parent_1
            record.properties_parent_id = self.properties_parent_2
            self.flush_tracking()
        self.assertFalse(self._new_mails)

        record.properties = {
            "property_m2m": False,
            "property_tags": ["aa"],
            "property_datetime": False,
            "property_date": False,
        }
        self.flush_tracking()
        record.message_ids.unlink()
        record.properties_parent_id = self.properties_parent_1
        self.flush_tracking()
        self.assertEqual(
            len(record.mapped("message_ids.tracking_value_ids")),
            2,
            "Only the parent and the tags property should have been tracked",
        )
        self.assertEqual(
            record._mail_track_get_field_sequence("properties"),
            100,
            "Properties field should have the same sequence as their parent",
        )

    @users("employee")
    def test_mail_track_selection_invalid(self):
        invalid_value = "I love writing tests!"
        record = self.env["mail.test.track.selection"].create(
            {
                "name": "Test Invalid Selection Values",
                "selection_type": "first",
            }
        )

        self.flush_tracking()
        self.env.cr.execute(
            """
            UPDATE mail_test_track_selection
               SET selection_type = %s
             WHERE id = %s
            """,
            [invalid_value, record.id],
        )
        record.invalidate_recordset()
        self.assertEqual(record.selection_type, invalid_value)

        record.selection_type = "second"

        self.flush_tracking()
        self.assertTracking(
            record.message_ids,
            [
                ("selection_type", "char", invalid_value, "Second"),
            ],
        )

    def test_track_groups(self):
        field = self.record._fields["email_from"]
        self.addCleanup(setattr, field, "groups", field.groups)
        field.groups = "base.group_erp_manager"

        self.record.sudo().write({"email_from": "X"})
        self.flush_tracking()

        msg_emp = Store().add(self.record.message_ids).get_result()
        msg_admin = (
            Store().add(self.record.with_user(self.user_admin).message_ids).get_result()
        )
        msg_sudo = Store().add(self.record.sudo().message_ids).get_result()

        tracking_values = self.env["mail.tracking.value"].search(
            [("mail_message_id", "=", self.record.message_ids[0].id)]
        )
        formatted_tracking_values = [
            {
                "id": tracking_values[0]["id"],
                "fieldInfo": {
                    "changedField": "Email From",
                    "currencyId": False,
                    "fieldType": "char",
                    "floatPrecision": None,
                    "isPropertyField": False,
                },
                "newValue": "X",
                "oldValue": False,
            }
        ]
        self.assertEqual(
            msg_emp["mail.message"][0].get("trackingValues"),
            [],
            "should not have protected tracking values",
        )
        self.assertEqual(
            msg_admin["mail.message"][0].get("trackingValues"),
            formatted_tracking_values,
            "should have protected tracking values",
        )
        self.assertEqual(
            msg_sudo["mail.message"][0].get("trackingValues"),
            formatted_tracking_values,
            "should have protected tracking values",
        )

        values_emp = self.record._notify_by_email_prepare_rendering_context(
            self.record.message_ids[0], {}
        )
        values_admin = self.record.with_user(
            self.user_admin
        )._notify_by_email_prepare_rendering_context(self.record.message_ids[0], {})
        values_sudo = self.record.sudo()._notify_by_email_prepare_rendering_context(
            self.record.message_ids[0], {}
        )
        self.assertFalse(
            values_emp.get("tracking_values"),
            "should not have protected tracking values",
        )
        self.assertTrue(
            values_admin.get("tracking_values"), "should have protected tracking values"
        )
        self.assertTrue(
            values_sudo.get("tracking_values"), "should have protected tracking values"
        )

        self.env.invalidate_all()
        self.env.registry.clear_cache()
        record_form = Form(self.record.with_user(self.user_employee))
        record_form.name = "TestDoNoCrash"
        record = record_form.save()
        self.assertEqual(record.name, "TestDoNoCrash")

    @users("employee")
    def test_track_invalid(self):
        test_record = self.env["mail.test.track.all"].create(
            {
                "company_id": self.env.company.id,
            }
        )
        self.flush_tracking()

        with self.assertRaises(ValueError):
            self.env["mail.tracking.value"]._prepare_tracking_values(
                "",
                "Test",
                "not_existing_field",
                {"string": "Test", "type": "char"},
                test_record,
            )

        with self.assertRaises(NotImplementedError):
            self.env["mail.tracking.value"]._prepare_tracking_values(
                "",
                "<p>Html</p>",
                "html_field",
                {"string": "HTML", "type": "html"},
                test_record,
            )

    @users("employee")
    def test_track_multi_models(self):
        main_track = self.env["mail.test.track.all"].create(
            {
                "name": "Multi Models Tracking",
                "char_field": "char_value",
            }
        )
        self.flush_tracking()
        self.assertEqual(len(main_track.message_ids), 1)
        self.assertFalse(main_track.message_ids.sudo().tracking_value_ids)

        sub_track = self.env["mail.test.track.groups"].create(
            {
                "name": "Groups",
                "secret": "secret",
            }
        )
        main_track.message_post(
            body="Custom Log with Tracking",
            tracking_value_ids=[
                (
                    0,
                    0,
                    {
                        "field_id": self.env["ir.model.fields"]
                        ._get(sub_track._name, "secret")
                        .id,
                        "new_value_char": "secret",
                        "old_value_char": False,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "field_id": False,
                        "new_value_integer": self.env.uid,
                        "old_value_integer": False,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "field_id": False,
                        "field_info": {
                            "desc": "Old integer",
                            "name": "Removed",
                            "sequence": 35,
                            "type": "integer",
                        },
                        "new_value_integer": 35,
                        "old_value_integer": 30,
                    },
                ),
            ],
        )
        trackings = main_track.message_ids.sudo().tracking_value_ids.sorted("id")
        self.assertEqual(len(trackings), 3)

        for tracking, exp_groups in zip(
            trackings,
            ["base.group_user", "base.group_system", "base.group_system"],
            strict=True,
        ):
            groups = "base.group_system"
            if tracking.field_id:
                field = self.env[tracking.field_id.model]._fields[
                    tracking.field_id.name
                ]
                groups = field.groups
            self.assertEqual(groups, exp_groups)

        formatted = trackings._tracking_value_format()
        self.assertEqual(
            formatted,
            [
                {
                    "id": trackings[0].id,
                    "fieldInfo": {
                        "changedField": "Secret",
                        "currencyId": False,
                        "fieldType": "char",
                        "floatPrecision": None,
                        "isPropertyField": False,
                    },
                    "newValue": "secret",
                    "oldValue": False,
                },
                {
                    "id": trackings[2].id,
                    "fieldInfo": {
                        "changedField": "Old integer",
                        "currencyId": False,
                        "fieldType": "integer",
                        "floatPrecision": None,
                        "isPropertyField": False,
                    },
                    "newValue": 35,
                    "oldValue": 30,
                },
                {
                    "id": trackings[1].id,
                    "fieldInfo": {
                        "changedField": "Unknown",
                        "currencyId": False,
                        "fieldType": "char",
                        "floatPrecision": None,
                        "isPropertyField": False,
                    },
                    "newValue": False,
                    "oldValue": False,
                },
            ],
        )

    @users("employee")
    def test_track_sequence(self):
        record = self.record.with_env(self.env)
        self.assertEqual(len(record.message_ids), 1)
        ordered_fnames = ["user_id", "customer_id", "container_id", "email_from"]

        record.write(
            {
                "container_id": self.env["mail.test.container"]
                .with_context(mail_create_nosubscribe=True)
                .create({"name": "Container"})
                .id,
                "customer_id": self.user_admin.partner_id.id,
                "email_from": "new.from@test.example.com",
                "name": "Zboub",
                "user_id": self.user_admin.id,
            }
        )
        self.flush_tracking()
        self.assertEqual(
            len(record.message_ids), 2, "should have 1 new tracking message"
        )
        tracking_values = (
            self.env["mail.tracking.value"]
            .sudo()
            .search([("mail_message_id", "=", record.message_ids[0].id)])
        )
        self.assertEqual(
            tracking_values.field_id.mapped("name"),
            ordered_fnames,
            "Track: order, based on ID DESC, should follow tracking sequence (or name) on field",
        )

        new_msg = record.message_post(
            body="Manual Hack of tracking",
            subtype_xmlid="mail.mt_note",
        )
        custom_order_fnames = ["container_id", "customer_id", "email_from", "user_id"]
        field_ids = [
            self.env["ir.model.fields"]._get(record._name, fname).id
            for fname in custom_order_fnames
        ]
        self.env["mail.tracking.value"].sudo().create(
            [
                {
                    "field_id": field_id,
                    "mail_message_id": new_msg.id,
                    "old_value_char": "unimportant",
                    "new_value_char": "unimportant",
                }
                for field_id in field_ids
            ]
        )
        tracking_values = (
            self.env["mail.tracking.value"]
            .sudo()
            .search([("mail_message_id", "=", record.message_ids[0].id)])
        )
        self.assertEqual(
            tracking_values.field_id.mapped("name"),
            list(reversed(custom_order_fnames)),
            "Tracking model: order, based on ID DESC, following reverted insertion",
        )
        tracking_formatted = tracking_values._tracking_value_format()
        self.assertEqual(
            [tracking_values.browse(t["id"]).field_id.name for t in tracking_formatted],
            ordered_fnames,
            "Track: formatted order is correctly based on field sequence definition",
        )

    @users("employee")
    def test_unlinked_model(self):
        record = self.record.with_env(self.env)
        record.write({"email_from": "new_value"})
        self.flush_tracking()
        self.assertTracking(
            record.message_ids[0],
            [("email_from", "char", False, "new_value")],
            strict=True,
        )

        fields_to_remove = (
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("model", "=", "mail.test.ticket"),
                ]
            )
        )

        model = self.env.registry.models.pop("mail.test.ticket")
        try:
            fields_to_remove.with_context(_force_unlink=True).unlink()
        finally:
            self.env.registry.models["mail.test.ticket"] = model

    @users("employee")
    def test_unlinked_field(self):
        record = self.record.with_env(self.env)
        record.write({"email_from": "new_value"})

        record_other = self.env["mail.test.ticket"].create({})
        self.flush_tracking()
        record_other.write({"email_from": "email.from.1@example.com"})
        self.flush_tracking()
        record_other.write(
            {
                "customer_id": self.test_partner.id,
                "email_from": "email.from.2@example.com",
                "user_id": self.env.user.id,
            }
        )
        self.flush_tracking()

        self.assertTracking(
            record.message_ids[0],
            [("email_from", "char", False, "new_value")],
            strict=True,
        )
        self.assertTracking(
            record_other.message_ids[0],
            [
                ("customer_id", "integer", False, self.test_partner.id),
                (
                    "email_from",
                    "char",
                    "email.from.1@example.com",
                    "email.from.2@example.com",
                ),
                ("user_id", "integer", False, self.env.user.id),
            ],
            strict=True,
        )
        self.assertTracking(
            record_other.message_ids[1],
            [("email_from", "char", False, "email.from.1@example.com")],
            strict=True,
        )

        trackings_all = (record + record_other).message_ids.sudo().tracking_value_ids
        email_from_trackings = trackings_all.filtered(
            lambda t: t.field_id.name == "email_from"
        ).sorted("id", reverse=True)
        trackings_all_sorted = [
            trackings_all.filtered(
                lambda t: t.field_id.name == "user_id"
            ),
            trackings_all.filtered(
                lambda t: t.field_id.name == "customer_id"
            ),
            *email_from_trackings,
        ]
        fields_info = [
            ("user_id", "many2one", "Responsible"),
            ("customer_id", "many2one", "Customer"),
            ("email_from", "char", "Email From"),
            ("email_from", "char", "Email From"),
            ("email_from", "char", "Email From"),
        ]
        values_info = [
            ("", self.env.user.name),
            ("", self.test_partner.name),
            *(
                (tracking.old_value_char, tracking.new_value_char)
                for tracking in email_from_trackings
            ),
        ]
        self.assertEqual(
            sorted(values_info[2:], key=repr),
            sorted(
                [
                    (False, "new_value"),
                    ("email.from.1@example.com", "email.from.2@example.com"),
                    (False, "email.from.1@example.com"),
                ],
                key=repr,
            ),
            "the three email_from trackings, whatever order they render in",
        )
        formatted = trackings_all._tracking_value_format()
        self.assertEqual(
            formatted,
            [
                {
                    "id": tracking.id,
                    "fieldInfo": {
                        "changedField": field_info[2],
                        "fieldType": field_info[1],
                        "floatPrecision": None,
                        "currencyId": False,
                        "isPropertyField": False,
                    },
                    "newValue": values[1],
                    "oldValue": values[0],
                }
                for tracking, field_info, values in zip(
                    trackings_all_sorted, fields_info, values_info, strict=True
                )
            ],
        )

        fields_toremove = (
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("model", "=", "mail.test.ticket"),
                    (
                        "name",
                        "in",
                        ("email_from", "user_id", "datetime"),
                    ),
                ]
            )
        )
        fields_toremove.with_context(_force_unlink=True).unlink()
        self.assertEqual(len(trackings_all.exists()), 5)

        formatted = trackings_all._tracking_value_format()
        self.assertEqual(
            formatted,
            [
                {
                    "id": tracking.id,
                    "fieldInfo": {
                        "changedField": field_info[2],
                        "fieldType": field_info[1],
                        "isPropertyField": False,
                        "currencyId": False,
                        "floatPrecision": None,
                    },
                    "newValue": values[1],
                    "oldValue": values[0],
                }
                for tracking, field_info, values in zip(
                    trackings_all_sorted, fields_info, values_info, strict=True
                )
            ],
        )


@tagged("mail_track")
class TestTrackingBatchCost(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customers = cls.env["res.partner"].create(
            [
                {
                    "email": f"track.customer.{index}@test.example.com",
                    "name": f"Track Customer {index}",
                }
                for index in range(20)
            ]
        )

    def _tracked_write_on(self, count):
        records = (
            self.env["mail.test.ticket"]
            .with_user(self.user_employee)
            .create([{"name": f"Ticket {index}"} for index in range(count)])
        )
        self.flush_tracking()
        self.env.invalidate_all()
        with counting_statements(self.cr) as statements:
            for index, record in enumerate(records):
                record.customer_id = self.customers[index % len(self.customers)]
            self.flush_tracking()
            return statements.count, records

    def _tracking_messages_of(self, records):
        return (
            self.env["mail.message"]
            .search([("model", "=", "mail.test.ticket"), ("res_id", "in", records.ids)])
            .filtered("tracking_value_ids")
        )

    def test_tracking_a_batch_costs_no_query_per_record(self):
        few_queries, _few_records = self._tracked_write_on(2)
        many_queries, many_records = self._tracked_write_on(20)
        self.assertLessEqual(
            many_queries - few_queries,
            4,
            f"18 further tracked records cost {many_queries - few_queries} extra "
            f"queries (2 records: {few_queries}, 20 records: {many_queries})",
        )
        tracking_messages = self._tracking_messages_of(many_records)
        self.assertEqual(
            len(tracking_messages), 20, "every record still gets its own message"
        )
        self.assertEqual(
            len(tracking_messages.tracking_value_ids),
            20,
            "every message still carries its own tracking value",
        )
        self.assertEqual(
            {
                tracking.new_value_char
                for tracking in tracking_messages.tracking_value_ids
            },
            set(self.customers.mapped("name")),
            "each record records its own new customer, not a shared one",
        )

    def test_tracking_keeps_one_author_per_record(self):
        records = (
            self.env["mail.test.ticket"]
            .with_user(self.user_employee)
            .create([{"name": f"Author {index}"} for index in range(3)])
        )
        self.flush_tracking()
        for index, record in enumerate(records):
            record._track_set_author(self.customers[index])
            record.customer_id = self.customers[index]
        self.flush_tracking()
        tracking_messages = self._tracking_messages_of(records)
        messages_by_res_id = tracking_messages.grouped("res_id")
        self.assertEqual(
            [
                messages_by_res_id.get(record.id, tracking_messages.browse()).author_id
                for record in records
            ],
            [self.customers[index] for index in range(3)],
        )

    def _subtype_tracked_write_on(self, count, authors=None):
        containers = self.env["mail.test.container"].create(
            [{"name": f"Container {index}"} for index in range(3)]
        )
        records = (
            self.env["mail.test.ticket"]
            .with_user(self.user_employee)
            .create([{"name": f"Subtyped {index}"} for index in range(count)])
        )
        records.message_subscribe(partner_ids=self.customers[:3].ids)
        self.flush_tracking()
        self.env.invalidate_all()
        with counting_statements(self.cr) as statements:
            for index, record in enumerate(records):
                if authors:
                    record._track_set_author(authors[index % len(authors)])
                record.container_id = containers[index % len(containers)]
            self.flush_tracking()
            return statements.count, records

    def test_tracking_with_a_subtype_costs_no_query_per_record(self):
        few_queries, _few = self._subtype_tracked_write_on(2)
        many_queries, many_records = self._subtype_tracked_write_on(20)
        self.assertLessEqual(
            many_queries - few_queries,
            25,
            f"18 further subtype-tracked records cost {many_queries - few_queries} "
            f"extra queries (2 records: {few_queries}, 20 records: {many_queries})",
        )
        tracking_messages = self._tracking_messages_of(many_records)
        self.assertEqual(len(tracking_messages), 20)
        self.assertEqual(len(tracking_messages.tracking_value_ids), 20)
        self.assertEqual(
            tracking_messages.subtype_id,
            self.env.ref("test_mail.st_mail_test_ticket_container_upd"),
            "every message keeps the subtype `_track_subtype` returned",
        )
        self.assertEqual(
            len(tracking_messages.notification_ids),
            60,
            "three followers are still notified for each of the twenty records",
        )
        self.assertFalse(
            tracking_messages.filtered(lambda message: not message.reply_to),
            "every message still resolves its own reply-to",
        )

    def _logged_tracked_write_on(self, count, authors=None):
        records = (
            self.env["mail.test.ticket"]
            .with_user(self.user_employee)
            .create([{"name": f"Logged {index}"} for index in range(count)])
        )
        self.flush_tracking()
        self.env.invalidate_all()
        with counting_statements(self.cr) as statements:
            for index, record in enumerate(records):
                if authors:
                    record._track_set_author(authors[index % len(authors)])
                record.email_from = f"logged.{index}@test.example.com"
            self.flush_tracking()
            return statements.count, records

    def test_distinct_authors_cost_no_query_per_author(self):
        for label, writer in (
            ("posting", self._subtype_tracked_write_on),
            ("logging", self._logged_tracked_write_on),
        ):
            with self.subTest(exit=label):
                one_author, _ = writer(20, authors=self.customers[:1])
                many_authors, records = writer(20, authors=self.customers[:20])
                self.assertLessEqual(
                    many_authors - one_author,
                    10,
                    f"the {label} exit charged {many_authors - one_author} extra "
                    f"queries for 19 further distinct authors (1 author: "
                    f"{one_author}, 20 authors: {many_authors})",
                )
                messages = self._tracking_messages_of(records)
                self.assertEqual(len(messages), 20)
                self.assertEqual(
                    messages.mapped("author_id"),
                    self.customers[:20],
                    "each record keeps its own author",
                )

    def test_tracking_a_batched_write_costs_nothing_per_record(self):
        container = self.env["mail.test.container"].create({"name": "Shared"})

        def batched_write_on(count):
            records = (
                self.env["mail.test.ticket"]
                .with_user(self.user_employee)
                .create([{"name": f"Flat {index}"} for index in range(count)])
            )
            records.message_subscribe(partner_ids=self.customers[:3].ids)
            self.flush_tracking()
            self.env.invalidate_all()
            with counting_statements(self.cr) as statements:
                records.container_id = container
                self.flush_tracking()
                return statements.count, records

        few_queries, _few = batched_write_on(2)
        many_queries, many_records = batched_write_on(20)
        self.assertLessEqual(
            many_queries - few_queries,
            5,
            f"18 further records cost {many_queries - few_queries} extra queries "
            f"(2 records: {few_queries}, 20 records: {many_queries})",
        )
        tracking_messages = self._tracking_messages_of(many_records)
        self.assertEqual(len(tracking_messages), 20)
        self.assertEqual(len(tracking_messages.tracking_value_ids), 20)
        self.assertEqual(
            len(tracking_messages.notification_ids),
            60,
            "three followers are still notified for each of the twenty records",
        )

    def test_tracking_with_a_subtype_keeps_one_author_per_record(self):
        _queries, records = self._subtype_tracked_write_on(
            4, authors=self.customers[:2]
        )
        tracking_messages = self._tracking_messages_of(records)
        messages_by_res_id = tracking_messages.grouped("res_id")
        self.assertEqual(
            [
                messages_by_res_id.get(record.id, tracking_messages.browse()).author_id
                for record in records
            ],
            [self.customers[index % 2] for index in range(4)],
        )

    def test_tracking_creation_templates_post_once_per_change_set(self):
        template = self.env.ref("test_mail.mail_test_ticket_tracking_tpl")
        calls = []
        original = self.registry["mixin.mail.thread"]._message_track_post_template

        def traced(records_self, changes):
            calls.append((records_self.ids, sorted(changes or ())))
            return original(records_self, changes)

        with (
            patch(
                "odoo.addons.mail.models.mixin_mail_thread.MixinMailThread._message_track_post_template",
                traced,
            ),
            self.mock_mail_gateway(),
        ):
            records = (
                self.env["mail.test.ticket"]
                .with_user(self.user_employee)
                .create(
                    [
                        {
                            "name": f"Ticket {index}",
                            "mail_template": template.id,
                            "customer_id": self.customers[index].id,
                        }
                        for index in range(4)
                    ]
                    + [{"name": "Ticket user", "user_id": self.user_admin.id}]
                )
            )
            self.flush_tracking()

        self.assertCountEqual(
            calls,
            [(records[:4].ids, ["customer_id"]), (records[4:].ids, ["user_id"])],
        )
        self.assertEqual(len(self._new_mails), 4, "still one mail per record")

    def test_tracking_templates_run_in_each_writer_company(self):
        company_2 = self.env["res.company"].create({"name": "Tracking Company 2"})
        self.user_admin.company_ids = [Command.link(company_2.id)]
        records = self.env["mail.test.ticket"].create(
            [{"name": "Ticket C1"}, {"name": "Ticket C2"}]
        )
        self.flush_tracking()
        seen = {}

        def _track_template(record, changes):
            seen[record.id] = record.env.company
            return {}

        self.patch(
            self.registry["mail.test.ticket"], "_track_template", _track_template
        )
        records[0].with_user(self.user_employee).customer_id = self.customers[0]
        records[1].with_user(self.user_admin).with_company(
            company_2
        ).customer_id = self.customers[1]
        self.flush_tracking()

        self.assertEqual(seen[records[1].id], company_2)
        self.assertEqual(seen[records[0].id], self.user_employee.company_id)

    def _batch_template_tracking(self, count, patched_track_template=None):
        template = self.env.ref("test_mail.mail_test_ticket_tracking_tpl")
        records = (
            self.env["mail.test.ticket"]
            .with_user(self.user_employee)
            .create(
                [
                    {"name": f"Ticket {index}", "mail_template": template.id}
                    for index in range(count)
                ]
            )
        )
        self.flush_tracking()
        if patched_track_template:
            self.patch(
                self.registry["mail.test.ticket"],
                "_track_template",
                patched_track_template,
            )
        Thread = self.registry["mixin.mail.thread"]
        calls = {"mass_mail": [], "comment": []}
        original_mail = Thread.message_mail_with_source
        original_post = Thread.message_post_with_source

        def traced_mail(records_self, *args, **kwargs):
            calls["mass_mail"].append(records_self.ids)
            return original_mail(records_self, *args, **kwargs)

        def traced_post(records_self, *args, **kwargs):
            calls["comment"].append(records_self.ids)
            return original_post(records_self, *args, **kwargs)

        with (
            patch.object(Thread, "message_mail_with_source", traced_mail),
            patch.object(Thread, "message_post_with_source", traced_post),
            self.mock_mail_gateway(),
        ):
            records.write({"customer_id": self.customers[0].id})
            self.flush_tracking()
        return records, calls

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_tracking_templates_mass_mail_once_per_template_for_a_batch(self):
        records, calls = self._batch_template_tracking(5)
        self.assertEqual(
            calls["mass_mail"],
            [records.ids],
            "one mass mailing for the five records, not one per record",
        )
        self.assertEqual(calls["comment"], [])
        self.assertEqual(len(self._new_mails), 5, "still one mail per record")
        self.assertEqual(
            set(self._new_mails.mapped("res_id")),
            set(records.ids),
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_tracking_templates_post_once_per_template_for_a_batch(self):
        template = self.env.ref("test_mail.mail_test_ticket_tracking_tpl")

        def _track_template(self, changes):
            return {"customer_id": (template, {})} if "customer_id" in changes else {}

        records, calls = self._batch_template_tracking(5, _track_template)
        self.assertEqual(calls["comment"], [records.ids])
        self.assertEqual(calls["mass_mail"], [])
        for record in records:
            template_messages = record.message_ids.filtered(
                lambda message: message.subject == "Test Template"
            )
            self.assertEqual(len(template_messages), 1)
            self.assertEqual(template_messages.message_type, "auto_comment")
            self.assertEqual(template_messages.body, f"<p>Hello {record.name}</p>")


@tagged("mail_track")
class TestTrackingFieldsOfEveryWriter(MailCommon):
    def test_a_writer_who_cannot_see_a_field_does_not_hide_its_tracking(self):
        self._create_portal_user()
        self.env["ir.access"].create(
            {
                "name": "portal writes tracked groups",
                "model_id": self.env["ir.model"]._get_id("mail.test.track.groups"),
                "group_id": self.env.ref("base.group_portal").id,
                "kind": "permission",
                "operation": "ru",
            }
        )
        seen_by_portal, secret_holder = (
            self.env["mail.test.track.groups"]
            .sudo()
            .create([{"name": "Seen"}, {"name": "Holder", "secret": "before"}])
        )
        self.flush_tracking()
        seen_by_portal.with_user(self.user_portal).write({"name": "Seen twice"})
        secret_holder.sudo().write({"secret": "after"})
        self.flush_tracking()
        tracked = secret_holder.message_ids.sudo().tracking_value_ids
        self.assertIn("secret", tracked.field_id.mapped("name"))

    def test_the_fields_a_user_tracks_follow_its_groups(self):
        self._create_portal_user()
        tracked = self.env["mail.test.track.groups"].with_user(self.user_portal)
        self.assertEqual(tracked._track_get_fields(), {"name"})
        self.user_portal.group_ids = [
            Command.unlink(self.env.ref("base.group_portal").id),
            Command.link(self.env.ref("base.group_user").id),
        ]
        self.assertEqual(tracked._track_get_fields(), {"name", "partner_id", "secret"})


@tagged("mail_track")
class TestTrackingFieldReadOnSomeRecords(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_other = cls.env["res.company"].create({"name": "Tracking B"})
        companies = cls.env.company | cls.company_other
        cls.scoped_admin = new_test_user(
            cls.env,
            login="tracking_scoped_admin",
            groups="base.group_user",
            company_ids=[Command.set(companies.ids)],
        )
        cls.env["res.users.grant"].create(
            {
                "user_id": cls.scoped_admin.id,
                "group_id": cls.env.ref("base.group_system").id,
                "company_ids": [Command.set(cls.env.company.ids)],
            }
        )
        cls.records = (
            cls.env["mail.test.track"]
            .with_context(mail_notrack=False)
            .create(
                [
                    {"name": f"In {company.name}", "company_id": company.id}
                    for company in companies
                    for _ in range(2)
                ]
            )
        )
        cls.env.flush_all()
        cls.cr.flush()
        cls.records.with_user(cls.user_admin).admin_note = "noted"
        cls.env.flush_all()
        cls.cr.flush()

    def _visible(self, records):
        env = self.env(
            user=self.scoped_admin,
            context={"allowed_company_ids": self.records.company_id.ids},
        )
        trackings = records.message_ids.sudo().tracking_value_ids
        return trackings._filtered_has_field_access(env).mail_message_id.mapped(
            lambda message: message.res_id
        )

    def test_its_tracking_shows_on_the_records_the_group_reaches(self):
        in_a, in_b = self.records[:2], self.records[2:]
        self.assertEqual(sorted(self._visible(self.records)), sorted(in_a.ids))
        self.assertFalse(self._visible(in_b))

    def test_the_records_are_judged_at_once(self):
        env = self.env(
            user=self.scoped_admin,
            context={"allowed_company_ids": self.records.company_id.ids},
        )

        def queries(records):
            trackings = records.message_ids.sudo().tracking_value_ids
            self.env.invalidate_all()
            with counting_statements(self.cr) as statements:
                trackings._filtered_has_field_access(env)
                return statements.count

        queries(self.records)
        self.assertEqual(queries(self.records), queries(self.records[:1]))

    def test_a_message_moved_off_its_record_hides_it(self):
        simple = self.env["mail.test.simple"].create({"name": "Moved to"})
        self.records.message_ids.sudo().write(
            {"model": simple._name, "res_id": simple.id}
        )
        self.assertFalse(self._visible(simple))
        trackings = simple.message_ids.sudo().tracking_value_ids
        self.assertEqual(len(trackings._filtered_has_field_access(self.env)), 4)


@tagged("mail_track")
class TestTrackingCompanyDependent(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_other = cls.env["res.company"].create({"name": "Tracking B"})
        cls.record_a, cls.record_b = (
            cls.env["mail.test.track"]
            .with_context(mail_notrack=False)
            .create([{"name": "In A"}, {"name": "In B"}])
        )
        cls.record_b.with_company(cls.company_other).company_amount = 5.0
        cls.env.flush_all()
        cls.cr.flush()

    def test_each_record_is_compared_in_the_company_it_was_written_in(self):
        messages_b = self.record_b.message_ids
        self.record_a.with_company(self.env.company).company_amount = 1.0
        self.record_b.with_company(self.company_other).company_amount = 5.0
        self.flush_tracking()
        self.assertEqual(self.record_b.message_ids, messages_b)
        tracked = self.record_a.message_ids[0].sudo().tracking_value_ids
        self.assertEqual(tracked.field_id.name, "company_amount")
        self.assertEqual(tracked.new_value_float, 1.0)
