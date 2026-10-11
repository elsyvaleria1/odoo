from ast import literal_eval

from odoo import Command, exceptions
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import users
from odoo.tools import mute_logger

from odoo.addons.integration_twilio.tests.common import MockSmsTwilioApi
from odoo.addons.phone_validation.tools import phone_validation
from odoo.addons.test_mass_mailing.tests.common import TestMassSMSCommon


@tagged("mass_mailing", "mass_mailing_sms")
class TestMassSMSInternals(TestMassSMSCommon):
    @users("user_marketing")
    def test_mass_sms_domain(self):
        mailing = self.env["mailing.mailing"].create(
            {
                "name": "Xmas Spam",
                "subject": "Xmas Spam",
                "mailing_model_id": self.env["ir.model"]._get("mail.test.sms").id,
                "mailing_type": "sms",
            }
        )
        self.assertEqual(literal_eval(mailing.mailing_domain), [])

        mailing = self.env["mailing.mailing"].create(
            {
                "name": "Xmas Spam",
                "subject": "Xmas Spam",
                "mailing_model_id": self.env["ir.model"]._get("mail.test.sms.bl").id,
                "mailing_type": "sms",
            }
        )
        self.assertEqual(literal_eval(mailing.mailing_domain), [])

    @users("user_marketing")
    def test_mass_sms_internals(self):
        with self.with_user("user_marketing"):
            mailing = self.env["mailing.mailing"].create(
                {
                    "name": "Xmas Spam",
                    "subject": "Xmas Spam",
                    "mailing_model_id": self.env["ir.model"]._get("mail.test.sms").id,
                    "mailing_type": "sms",
                    "mailing_domain": "%s" % repr([("name", "ilike", "MassSMSTest")]),
                    "sms_template_id": self.sms_template.id,
                    "sms_allow_unsubscribe": False,
                }
            )

            self.assertEqual(mailing.mailing_model_real, "mail.test.sms")
            self.assertEqual(
                mailing.medium_id, self.env.ref("mass_mailing_sms.utm_medium_sms")
            )
            self.assertEqual(mailing.body_plaintext, self.sms_template.body)

            remaining_res_ids = mailing._get_remaining_recipients()
            self.assertEqual(set(remaining_res_ids), set(self.records.ids))

            with self.mockSMSGateway():
                mailing.action_send_sms()

        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "content": "Dear %s this is a mass SMS." % record.display_name,
                }
                for i, record in enumerate(self.records)
            ],
            mailing,
            self.records,
        )

    @users("user_marketing")
    def test_mass_sms_internals_errors(self):
        new_record_1 = self.env["mail.test.sms"].create(
            {
                "name": "MassSMSTest_nr1",
                "customer_id": self.partners[0].id,
                "phone_nbr_ids": [Command.create({"number": "0456999999"})],
            }
        )
        void_record = self.env["mail.test.sms"].create(
            {
                "name": "MassSMSTest_void",
                "customer_id": False,
                "phone_nbr_ids": False,
            }
        )
        falsy_record_1 = self.env["mail.test.sms"].create(
            {
                "name": "MassSMSTest_falsy_1",
                "customer_id": False,
                "phone_nbr_ids": [Command.create({"number": "abcd"})],
            }
        )
        falsy_record_2 = self.env["mail.test.sms"].create(
            {
                "name": "MassSMSTest_falsy_2",
                "customer_id": False,
                "phone_nbr_ids": [Command.create({"number": "04561122"})],
            }
        )
        bl_record_1 = self.env["mail.test.sms"].create(
            {
                "name": "MassSMSTest_bl_1",
                "customer_id": False,
                "phone_nbr_ids": [Command.create({"number": "0456110011"})],
            }
        )
        self.env["phone.blacklist"].sudo().create({"number": "0456110011"})
        country_be_id = self.env.ref("base.be").id
        nr2_partner = self.env["res.partner"].create(
            {
                "name": "Partner_nr2",
                "country_id": country_be_id,
                "phone_ids": [
                    Command.create({"number": "0456449999", "type": "landline"})
                ],
            }
        )
        new_record_2 = self.env["mail.test.sms"].create(
            {
                "name": "MassSMSTest_nr2",
                "customer_id": nr2_partner.id,
                "phone_nbr_ids": [
                    Command.create({"number": self.records[0].phone_nbr_ids.number})
                ],
            }
        )
        records_numbers = self.records_numbers + ["+32456999999"]

        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)
        mailing.write(
            {
                "sms_force_send": False,
                "keep_archives": True,
            }
        )
        with self.with_user("user_marketing"):
            with self.mockSMSGateway():
                mailing.action_send_sms()

        valid_records = self.records | new_record_1
        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": records_numbers[i],
                    "content": "Dear %s this is a mass SMS" % record.display_name,
                }
                for i, record in enumerate(self.records | new_record_1)
            ],
            mailing,
            valid_records,
        )
        self.assertEqual(
            len(
                self.env["mail.message"].search(
                    [
                        ("res_id", "in", valid_records.ids),
                        ("model", "=", "mail.test.sms"),
                        ("id", "in", self._new_sms.mail_message_id.ids),
                    ]
                )
            ),
            len(valid_records),
            "Only not canceled message must be logged in the chatter",
        )
        self.assertSMSTraces(
            [
                {
                    "partner": new_record_2.customer_id,
                    "number": self.records_numbers[0],
                    "content": "Dear %s this is a mass SMS" % new_record_2.display_name,
                    "trace_status": "cancel",
                    "failure_type": "sms_duplicate",
                }
            ],
            mailing,
            new_record_2,
        )
        self.assertSMSTraces(
            [
                {
                    "partner": self.env["res.partner"],
                    "number": phone_validation.phone_format(
                        bl_record_1.phone_nbr_ids.number,
                        "BE",
                        "32",
                        force_format="E164",
                    ),
                    "content": "Dear %s this is a mass SMS" % bl_record_1.display_name,
                    "trace_status": "cancel",
                    "failure_type": "sms_blacklist",
                }
            ],
            mailing,
            bl_record_1,
        )
        self.assertSMSTraces(
            [
                {
                    "partner": self.env["res.partner"],
                    "number": False,
                    "content": "Dear %s this is a mass SMS" % void_record.display_name,
                    "trace_status": "cancel",
                    "failure_type": "sms_number_missing",
                }
            ],
            mailing,
            void_record,
        )
        self.assertSMSTraces(
            [
                {
                    "partner": self.env["res.partner"],
                    "number": record.phone_nbr_ids.number,
                    "content": "Dear %s this is a mass SMS" % record.display_name,
                    "trace_status": "cancel",
                    "failure_type": "sms_number_format",
                }
                for record in falsy_record_1 + falsy_record_2
            ],
            mailing,
            falsy_record_1 + falsy_record_2,
        )
        self.assertEqual(mailing.canceled, 5)

        mailing_no_blacklist = mailing.copy()
        mailing_no_blacklist.use_exclusion_list = False
        with self.with_user("user_marketing"):
            with self.mockSMSGateway():
                mailing_no_blacklist.action_send_sms()

        self.assertSMSTraces(
            [
                {
                    "partner": bl_record_1.customer_id,
                    "number": phone_validation.phone_format(
                        bl_record_1.phone_nbr_ids.number,
                        "BE",
                        "32",
                        force_format="E164",
                    ),
                    "content": "Dear %s this is a mass SMS" % bl_record_1.display_name,
                }
            ],
            mailing_no_blacklist,
            bl_record_1,
        )
        self.assertEqual(mailing_no_blacklist.canceled, 4)

    @users("user_marketing")
    def test_mass_sms_internals_done_ids(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)
        mailing.write(
            {
                "sms_force_send": False,
                "keep_archives": True,
            }
        )

        with self.with_user("user_marketing"):
            with self.mockSMSGateway():
                mailing.action_send_sms(res_ids=self.records[:5].ids)

        traces = self.env["mailing.trace"].search(
            [("mass_mailing_id", "in", mailing.ids)]
        )
        self.assertEqual(len(traces), 5)
        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "content": "Dear %s this is a mass SMS" % record.display_name,
                }
                for i, record in enumerate(self.records[:5])
            ],
            mailing,
            self.records[:5],
        )

        with self.with_user("user_marketing"):
            with self.mockSMSGateway():
                mailing.action_send_sms(res_ids=self.records.ids)

        traces.unlink()
        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "content": "Dear %s this is a mass SMS" % record.display_name,
                    "trace_status": "cancel",
                    "failure_type": "sms_duplicate",
                }
                for i, record in enumerate(self.records[:5])
            ],
            mailing,
            self.records[:5],
        )
        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i + 5],
                    "content": "Dear %s this is a mass SMS" % record.display_name,
                }
                for i, record in enumerate(self.records[5:])
            ],
            mailing,
            self.records[5:],
        )

    @users("user_marketing")
    def test_mass_sms_processing_with_force_send(self):
        with self.with_user("user_marketing"):
            mailing = self.env["mailing.mailing"].create(
                {
                    "name": "Xmas Spam",
                    "subject": "Xmas Spam",
                    "mailing_model_id": self.env["ir.model"]._get("mail.test.sms").id,
                    "mailing_type": "sms",
                    "mailing_domain": "%s" % repr([("name", "ilike", "MassSMSTest")]),
                    "sms_template_id": self.sms_template.id,
                    "sms_allow_unsubscribe": False,
                }
            )

            remaining_res_ids = mailing._get_remaining_recipients()
            self.assertEqual(set(remaining_res_ids), set(self.records.ids))

            mailing.sms_force_send = True
            with self.mockSMSGateway(moderated=True):
                mailing.action_send_sms()

        self.assertEqual(mailing.state, "sending")
        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "content": "Dear %s this is a mass SMS." % record.display_name,
                    "trace_status": "process",
                }
                for i, record in enumerate(self.records)
            ],
            mailing,
            self.records,
        )

    @users("user_marketing")
    def test_mass_sms_error_with_force_send(self):
        with self.with_user("user_marketing"):
            mailing = self.env["mailing.mailing"].create(
                {
                    "name": "Xmas Spam",
                    "subject": "Xmas Spam",
                    "mailing_model_id": self.env["ir.model"]._get("mail.test.sms").id,
                    "mailing_type": "sms",
                    "mailing_domain": "%s" % repr([("name", "ilike", "MassSMSTest")]),
                    "sms_template_id": self.sms_template.id,
                    "sms_allow_unsubscribe": False,
                }
            )

            remaining_res_ids = mailing._get_remaining_recipients()
            self.assertEqual(set(remaining_res_ids), set(self.records.ids))

            mailing.sms_force_send = True
            with self.mockSMSGateway(sim_error="server_error"):
                mailing.action_send_sms()

        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "content": "Dear %s this is a mass SMS." % record.display_name,
                    "trace_status": "error",
                    "failure_type": "sms_server",
                }
                for i, record in enumerate(self.records)
            ],
            mailing,
            self.records,
        )


@tagged("mass_mailing", "mass_mailing_sms", "mailing_test")
class TestMassSMSTest(TestMassSMSCommon):
    @mute_logger("odoo.addons.mail.models.mixin_mail_render")
    def test_mass_sms_test_button(self):
        mailing = self.env["mailing.mailing"].create(
            {
                "name": "TestButton",
                "subject": "Subject {{ object.name }}",
                "preview": "Preview {{ object.name }}",
                "state": "draft",
                "mailing_type": "sms",
                "body_plaintext": "Hello {{ object.name }}",
                "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                "sms_allow_unsubscribe": True,
            }
        )
        mailing_test = (
            self.env["wizard.mailing.mailing.send.sms.test"]
            .with_user(self.user_marketing)
            .create(
                {
                    "numbers": "+32456001122\n+32455334455\nwrong\n\n",
                    "mailing_id": mailing.id,
                }
            )
        )

        with self.with_user("user_marketing"):
            with self.mockSMSGateway():
                mailing_test.action_send_sms()
        new_traces = self.env["mailing.trace"].search(
            [("mass_mailing_id", "=", mailing.id)]
        )
        self.assertEqual(
            len(new_traces), 2, "Should have create 1 trace / valid number"
        )
        self.assertEqual(
            new_traces.mapped("is_test_trace"),
            [True, True],
            "Traces should be flagged as test",
        )
        self.assertEqual(
            sorted(new_traces.mapped("sms_number")), ["+32455334455", "+32456001122"]
        )

        mailing.write(
            {
                "body_plaintext": "Hello {{ object.name_id.id }}",
            }
        )

        with self.with_user("user_marketing"):
            with self.mock_mail_gateway(), self.assertRaises(UserError):
                mailing_test.action_send_sms()


@tagged("mass_mailing", "mass_mailing_sms")
class TestMassSMS(TestMassSMSCommon):
    @users("user_marketing")
    def test_mass_sms_links(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)
        mailing.write(
            {
                "body_plaintext": "Dear {{ object.display_name }} this is a mass SMS with two links http://www.odoo.com/smstest and http://www.odoo.com/smstest/{{ object.name }}",
                "sms_template_id": False,
                "sms_force_send": True,
                "sms_allow_unsubscribe": True,
            }
        )

        with self.mockSMSGateway():
            mailing.action_send_sms()

        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "trace_status": "pending",
                    "content": "Dear %s this is a mass SMS with two links"
                    % record.display_name,
                }
                for i, record in enumerate(self.records)
            ],
            mailing,
            self.records,
            sms_links_info=[
                [
                    ("http://www.odoo.com/smstest", True, {}),
                    ("http://www.odoo.com/smstest/%s" % record.name, True, {}),
                    ("unsubscribe", False, {}),
                ]
                for record in self.records
            ],
        )

    @users("user_marketing")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mass_sms_partner_only(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)
        mailing.write(
            {
                "mailing_model_id": self.env["ir.model"]
                ._get("mail.test.sms.partner")
                .id,
            }
        )

        records = self.env["mail.test.sms.partner"].create(
            [
                {
                    "name": "MassSMSTest on %s" % partner.name,
                    "customer_id": partner.id,
                }
                for partner in self.partners
            ]
        )

        with self.mockSMSGateway():
            mailing.action_send_sms()

        self.assertEqual(len(mailing.mailing_trace_ids), 10)
        self.assertSMSTraces(
            [
                {
                    "partner": record.customer_id,
                    "number": record.customer_id.phone_sanitized,
                    "trace_status": "pending",
                    "content": "Dear %s this is a mass SMS with two links"
                    % record.display_name,
                }
                for record in records
            ],
            mailing,
            records,
            sms_links_info=[
                [
                    ("http://www.odoo.com/smstest", True, {}),
                    ("http://www.odoo.com/smstest/%s" % record.id, True, {}),
                    ("unsubscribe", False, {}),
                ]
                for record in records
            ],
        )

        new_record = self.env["mail.test.sms.partner"].create(
            [
                {
                    "name": "Duplicate SMS on %s" % self.partners[0].name,
                    "customer_id": self.partners[0].id,
                }
            ]
        )
        with self.mockSMSGateway():
            mailing.action_send_sms()

        self.assertEqual(len(mailing.mailing_trace_ids), 11)
        self.assertSMSTraces(
            [
                {
                    "partner": new_record.customer_id,
                    "number": new_record.customer_id.phone_sanitized,
                    "trace_status": "pending",
                    "content": "Dear %s this is a mass SMS with two links"
                    % new_record.display_name,
                }
            ],
            mailing,
            new_record,
            sms_links_info=[
                [
                    ("http://www.odoo.com/smstest", True, {}),
                    ("http://www.odoo.com/smstest/%s" % new_record.id, True, {}),
                    ("unsubscribe", False, {}),
                ]
            ],
        )

    @users("user_marketing")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mass_sms_partner_only_m2m(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)
        mailing.write(
            {
                "mailing_model_id": self.env["ir.model"]
                ._get("mail.test.sms.partner.2many")
                .id,
            }
        )

        self.env["mail.test.sms.partner.2many"].create(
            [
                {
                    "name": "MassSMSTest on %s" % partner.name,
                    "customer_ids": [(4, partner.id)],
                }
                for partner in self.partners
            ]
        )

        with self.assertRaises(exceptions.UserError), self.mockSMSGateway():
            mailing.action_send_sms()

    @users("user_marketing")
    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_mass_sms_w_opt_out(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)
        recipients = self._create_mailing_sms_test_records(
            model="mail.test.sms.bl.optout", count=5
        )

        (recipients[0] | recipients[1]).write({"opt_out": True})
        self.env["phone.blacklist"].sudo().create(
            {"number": recipients[4].phone_nbr_ids.number}
        )

        mailing.write(
            {
                "mailing_model_id": self.env["ir.model"]._get(
                    "mail.test.sms.bl.optout"
                ),
                "mailing_domain": [("id", "in", recipients.ids)],
                "keep_archives": True,
            }
        )

        with self.mockSMSGateway():
            mailing.action_send_sms()

        self.assertSMSTraces(
            [
                {
                    "number": "+32456000000",
                    "trace_status": "cancel",
                    "failure_type": "sms_optout",
                },
                {
                    "number": "+32456000101",
                    "trace_status": "cancel",
                    "failure_type": "sms_optout",
                },
                {"number": "+32456000202", "trace_status": "pending"},
                {"number": "+32456000303", "trace_status": "pending"},
                {
                    "number": "+32456000404",
                    "trace_status": "cancel",
                    "failure_type": "sms_blacklist",
                },
            ],
            mailing,
            recipients,
        )
        self.assertEqual(mailing.canceled, 3)


@tagged("mass_mailing", "mass_mailing_sms", "twilio")
class TestMassSMSTwilio(TestMassSMSCommon, MockSmsTwilioApi):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.user_admin.company_id)

        cls.mailing_sms.write(
            {
                "body_plaintext": "This is a mass SMS",
                "sms_template_id": False,
                "sms_force_send": True,
                "sms_allow_unsubscribe": False,
            }
        )
        cls.records_fail = cls.env["mail.test.sms"].create(
            [
                {
                    "name": "MassSMSTest- No Number",
                    "phone_nbr_ids": False,
                },
                {
                    "name": "MassSMSTest- Invalid Number",
                    "phone_nbr_ids": [Command.create({"number": "1234"})],
                },
            ]
        )
        cls.records += cls.records_fail
        cls.records_numbers += [False, "1234"]

    @users("user_marketing")
    def test_mass_sms(self):
        mailing = self.env["mailing.mailing"].browse(self.mailing_sms.ids)

        with self.mock_sms_twilio_gateway():
            mailing.action_send_sms()

        exp_failure_types = [False] * 10 + ["sms_number_missing", "sms_number_format"]
        self.assertSMSTraces(
            [
                {
                    "failure_type": exp_failure_types[i],
                    "partner": record.customer_id,
                    "number": self.records_numbers[i],
                    "trace_status": "pending"
                    if record not in self.records_fail
                    else "cancel",
                    "content": "This is a mass SMS",
                }
                for i, record in enumerate(self.records)
            ],
            mailing,
            self.records,
        )

    @users("user_marketing")
    def test_mass_sms_twilio_issue(self):
        for error_type, exp_failure_type in [
            ("twilio_acc_unverified", "sms_acc"),
            ("twilio_callback", "twilio_callback"),
        ]:
            with self.subTest(error_type=error_type):
                mailing = (
                    self.env["mailing.mailing"].browse(self.mailing_sms.ids).copy()
                )

                with self.mock_sms_twilio_gateway(error_type=error_type):
                    mailing.action_send_sms()

                exp_failure_types = [exp_failure_type] * 10 + [
                    "sms_number_missing",
                    "sms_number_format",
                ]
                self.assertSMSTraces(
                    [
                        {
                            "failure_type": exp_failure_types[i],
                            "partner": record.customer_id,
                            "number": self.records_numbers[i],
                            "trace_status": "error"
                            if record not in self.records_fail
                            else "cancel",
                            "content": "This is a mass SMS",
                        }
                        for i, record in enumerate(self.records)
                    ],
                    mailing,
                    self.records,
                )
