from odoo import Command
from odoo.tests import tagged, users

from odoo.addons.sms.tests.common import SMSCommon
from odoo.addons.test_mail_sms.tests.common import TestSMSRecipients


@tagged("mail_thread")
class TestSMSActionsCommon(SMSCommon, TestSMSRecipients):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_phone_records, cls.test_phone_partners = cls._create_records_for_batch(
            "mail.test.sms.bl",
            5,
        )
        cls.test_phone_records += cls.env["mail.test.sms.bl"].create(
            [
                {
                    "phone_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "+32475110505"}),
                    ],
                    "mobile_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "+32475000505"}),
                    ],
                },
                {
                    "phone_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "0032475110606"}),
                    ],
                    "mobile_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "0032475000606"}),
                    ],
                },
                {
                    "phone_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "0032475110707"}),
                    ],
                    "mobile_nbr_ids": False,
                },
                {
                    "phone_nbr_ids": False,
                    "mobile_nbr_ids": False,
                },
                {
                    "phone_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "0475110606"}),
                    ],
                    "mobile_nbr_ids": False,
                },
                {
                    "phone_nbr_ids": False,
                    "mobile_nbr_ids": [
                        Command.clear(),
                        Command.create({"number": "0475110606"}),
                    ],
                },
            ]
        )
        cls.void_record = cls.test_phone_records[-3]
        cls.dupes = cls.test_phone_records[-2:]

    def test_initial_data(self):
        self.assertEqual(
            [record.mobile_nbr_ids.number for record in self.test_phone_records],
            [
                False,
                False,
                False,
                False,
                False,
                "+32475000505",
                "0032475000606",
                False,
                False,
                False,
                "0032475110606",
            ],
        )
        self.assertEqual(
            [record.phone_nbr_ids.number for record in self.test_phone_records],
            [
                "0475000000",
                "0475000101",
                "0475000202",
                "0475000303",
                "0475000404",
                "+32475110505",
                "0032475110606",
                "0032475110707",
                False,
                "0032475110606",
                False,
            ],
        )
        self.assertEqual(
            self.test_phone_records.mapped("phone_sanitized"),
            [
                "+32475000000",
                "+32475000101",
                "+32475000202",
                "+32475000303",
                "+32475000404",
                "+32475110505",
                "+32475110606",
                "+32475110707",
                False,
                "+32475110606",
                "+32475110606",
            ],
        )

    @users("employee")
    def test_search_phone_mobile_search_boolean(self):
        test_phone_records = self.test_phone_records.with_env(self.env)

        for test_values in [False, "", " "]:
            results = self.env["mail.test.sms.bl"].search(
                [("phone_mobile_search", "=", test_values)]
            )
            self.assertEqual(
                results,
                self.void_record,
                "Search on phone_mobile_search: = False: record with two void values",
            )
            results = self.env["mail.test.sms.bl"].search(
                [("phone_mobile_search", "!=", test_values)]
            )
            self.assertEqual(
                results,
                test_phone_records - self.void_record,
                "Search on phone_mobile_search: != False: record at least one value set",
            )

        results = self.env["mail.test.sms.bl"].search(
            [("phone_mobile_search", "=", True)]
        )
        self.assertEqual(
            results,
            test_phone_records - self.void_record,
            "Search on phone_mobile_search: = True: record at least one value set",
        )
        results = self.env["mail.test.sms.bl"].search(
            [("phone_mobile_search", "!=", True)]
        )
        self.assertEqual(
            results,
            self.void_record,
            "Search on phone_mobile_search: != True: record with two void values",
        )

    @users("employee")
    def test_search_phone_mobile_search_equal(self):
        test_phone_records = self.test_phone_records.with_env(self.env)

        for user_country in (self.env.ref("base.be"), self.env.ref("base.us")):
            self.env.user.sudo().country_id = user_country.id
            for source, expected in [
                (
                    "0475",
                    self.env["mail.test.sms.bl"],
                ),
                ("0475000000", test_phone_records[0]),
                ("0032475110606", test_phone_records[6] + self.dupes),
                ("+32475110606", test_phone_records[6] + self.dupes),
                ("+32 475 11 06 06", test_phone_records[6] + self.dupes),
            ]:
                with self.subTest(source=source):
                    results = self.env["mail.test.sms.bl"].search(
                        [("phone_mobile_search", "=", source)]
                    )
                    self.assertEqual(results, expected)

    @users("employee")
    def test_search_phone_mobile_search_ilike(self):
        test_phone_records = self.test_phone_records.with_env(self.env)

        for source, ilike_expected, notilike_expected in [
            (
                "0475",
                test_phone_records[:5],
                test_phone_records - test_phone_records[:5],
            ),
            ("101", test_phone_records[1], test_phone_records - test_phone_records[1]),
            (
                "+32475110",
                test_phone_records[5:8] + self.dupes,
                test_phone_records - test_phone_records[5:8] - self.dupes,
            ),
            (
                "0032475110",
                test_phone_records[5:8] + self.dupes,
                test_phone_records - test_phone_records[5:8] - self.dupes,
            ),
        ]:
            with self.subTest(source=source, operator="ilike"):
                results = self.env["mail.test.sms.bl"].search(
                    [("phone_mobile_search", "ilike", source)]
                )
                self.assertEqual(results, ilike_expected)

            with self.subTest(source=source, operator="not ilike"):
                results = self.env["mail.test.sms.bl"].search(
                    [("phone_mobile_search", "not ilike", source)]
                )
                self.assertEqual(results, notilike_expected)
