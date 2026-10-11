from datetime import UTC, date, datetime
from unittest.mock import patch
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from lxml import html

from odoo import SUPERUSER_ID, fields, http
from odoo.exceptions import AccessError
from odoo.fields import Command, Domain
from odoo.libs.web import urls
from odoo.tests import counting_statements, tagged
from odoo.tests.common import users
from odoo.tools import mute_logger

from odoo.addons.base.tests.common import HttpCaseWithUserDemo
from odoo.addons.digest.models.digest import KPI_AGGREGATE_MEMO, PERIODICITIES
from odoo.addons.digest.tests.common import TestDigestCommon
from odoo.addons.mail.tests.common import MailCommon


class TestDigest(TestDigestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reference_datetime = datetime(2024, 2, 13, 13, 30, 0)

        cls.env["mail.message"].search(
            [
                ("subtype_id", "=", cls.env.ref("mail.mt_comment").id),
                ("message_type", "in", ("comment", "email", "email_outgoing")),
            ]
        ).unlink()
        cls._setup_messages()

        cls.env["res.users"].search(
            [("login", "in", ["demo", "portal"])]
        ).action_archive()
        cls.env["res.users.log"].search(
            [("create_uid", "in", (cls.user_admin + cls.user_employee).ids)]
        ).unlink()
        cls._setup_logs_for_users(
            cls.user_admin, cls.reference_datetime - relativedelta(days=5)
        )

        with cls.mock_datetime_and_now(cls, cls.reference_datetime):
            cls.test_digest, cls.test_digest_2 = cls.env["digest.digest"].create(
                [
                    {
                        "kpi_mail_message_total": True,
                        "kpi_res_users_connected": True,
                        "name": "My Digest",
                        "periodicity": "daily",
                    },
                    {
                        "kpi_mail_message_total": True,
                        "kpi_res_users_connected": True,
                        "name": "My Digest",
                        "periodicity": "weekly",
                        "user_ids": [(4, cls.user_admin.id), (4, cls.user_employee.id)],
                    },
                ]
            )

    @users("admin")
    def test_assert_initial_values(self):
        test_digest = self.test_digest.with_user(self.env.user)
        test_digest_2 = self.test_digest_2.with_user(self.env.user)
        self.assertEqual(test_digest.create_date, self.reference_datetime)
        self.assertEqual(
            test_digest.next_run_date,
            self.reference_datetime.date() + relativedelta(days=1),
        )
        self.assertEqual(test_digest.periodicity, "daily")
        self.assertFalse(test_digest.user_ids)

        self.assertEqual(test_digest_2.create_date, self.reference_datetime)
        self.assertEqual(
            test_digest_2.next_run_date,
            self.reference_datetime.date() + relativedelta(weeks=1),
        )
        self.assertEqual(test_digest_2.periodicity, "weekly")
        self.assertEqual(test_digest_2.user_ids, self.user_admin + self.user_employee)

    @users("admin")
    def test_digest_kpi_res_users_connected_value(self):
        self.env["res.users.log"].with_user(SUPERUSER_ID).search([]).unlink()
        initial_values = self.all_digests.mapped("kpi_res_users_connected_value")
        self.assertEqual(initial_values, [0, 0, 0])

        self.env["res.users"].with_user(self.user_employee)._update_last_login()
        self.env["res.users"].with_user(self.user_admin)._update_last_login()

        self.all_digests.invalidate_recordset()

        self.assertEqual(self.digest_1.kpi_res_users_connected_value, 2)
        self.assertEqual(
            self.digest_2.kpi_res_users_connected_value,
            0,
            msg="This KPI is in an other company",
        )
        self.assertEqual(
            self.digest_3.kpi_res_users_connected_value,
            2,
            msg="This KPI has no company, should take the current one",
        )

    @users("admin")
    def test_digest_numbers(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        digest._action_subscribe_users(self.user_employee)

        digest.flush_recordset()
        with self.mock_mail_gateway():
            digest.action_send()

        self.assertEqual(
            len(self._new_mails), 1, "A new mail.mail should have been created"
        )
        mail = self._new_mails[0]
        self.assertEqual(mail.author_id, self.partner_admin)
        self.assertEqual(mail.email_from, self.company_admin.email_formatted)
        self.assertEqual(mail.state, "outgoing", "Mail should use the queue")

        kpi_message_values = html.fromstring(mail.body_html).xpath(
            '//table[@data-field="kpi_mail_message_total"]//*[hasclass("kpi_value")]/text()'
        )
        self.assertEqual([t.strip() for t in kpi_message_values], ["3", "8", "15"])

    @users("admin")
    def test_digest_subscribe(self):
        digest_user = self.digest_1.with_user(self.user_employee)
        self.assertFalse(digest_user.is_subscribed)

        digest_user.action_subscribe()
        self.assertTrue(
            digest_user.is_subscribed,
            "check the user was subscribed as action_subscribe will silently "
            "ignore subs of non-employees",
        )
        digest_user.action_unsubscribe()
        self.assertFalse(digest_user.is_subscribed)

    @users("admin")
    def test_digest_tip_description(self):
        self.env["digest.tip"].create(
            {
                "name": "Test digest tips",
                "tip_description": """
                <t t-set="record_exists" t-value="True" />
                <t t-if="record_exists">
                    <p class="rendered">Record exists.</p>
                </t>
                <t t-else="">
                    <p class="not-rendered">Record doesn't exist.</p>
                </t>
            """,
            }
        )
        with self.mock_mail_gateway():
            self.digest_1._action_send_to_user(self.user_employee)
        self.assertEqual(
            len(self._new_mails), 1, "A new Email should have been created"
        )
        sent_mail_body = html.fromstring(self._new_mails.body_html)
        values_to_check = [
            sent_mail_body.xpath('//t[@t-set="record_exists"]'),
            sent_mail_body.xpath('//p[@class="rendered"]/text()'),
            sent_mail_body.xpath('//p[@class="not-rendered"]/text()'),
        ]
        self.assertEqual(
            values_to_check,
            [[], ["Record exists."], []],
            "Sent mail should contain properly rendered tip content",
        )

    @users("admin")
    def test_digest_tone_down(self):
        test_digest = self.env["digest.digest"].browse(self.test_digest.ids)
        test_digest_2 = self.env["digest.digest"].browse(self.test_digest_2.ids)
        test_digest._action_subscribe_users(self.user_employee)
        digests = test_digest + test_digest_2

        digests.flush_recordset()
        current_dt = self.reference_datetime + relativedelta(days=1)
        with self.mock_datetime_and_now(current_dt), self.mock_mail_gateway():
            digests.action_send()

        self.assertEqual(
            test_digest.next_run_date, current_dt.date() + relativedelta(weeks=1)
        )
        self.assertEqual(test_digest.periodicity, "weekly")
        self.assertEqual(
            test_digest_2.next_run_date, current_dt.date() + relativedelta(weeks=1)
        )
        self.assertEqual(
            test_digest_2.periodicity,
            "weekly",
            "Should not have tone down because admin has logs",
        )

        with self.mock_datetime_and_now(current_dt), self.mock_mail_gateway():
            digests.action_send()

        self.assertEqual(
            test_digest.next_run_date, current_dt.date() + relativedelta(months=1)
        )
        self.assertEqual(test_digest.periodicity, "monthly")
        self.assertEqual(
            test_digest_2.next_run_date, current_dt.date() + relativedelta(weeks=1)
        )
        self.assertEqual(test_digest_2.periodicity, "weekly")

        with self.mock_datetime_and_now(current_dt), self.mock_mail_gateway():
            digests.action_send()

        self.assertEqual(
            test_digest.next_run_date, current_dt.date() + relativedelta(months=3)
        )
        self.assertEqual(test_digest.periodicity, "quarterly")
        self.assertEqual(
            test_digest_2.next_run_date, current_dt.date() + relativedelta(weeks=1)
        )
        self.assertEqual(test_digest_2.periodicity, "weekly")

    @users("admin")
    def test_digest_tone_down_wlogs(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        digest._action_subscribe_users(self.user_employee)

        for logs, (periodicity, run_date), (exp_periodicity, exp_run_date, msg) in zip(
            [
                [(self.user_employee, self.reference_datetime)],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(days=1, hours=23),
                    )
                ],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(days=2, hours=1),
                    )
                ],
                [],
                [(self.user_employee, self.reference_datetime - relativedelta(days=6))],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(days=8),
                    )
                ],
                [],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(days=25),
                    )
                ],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(days=32),
                    )
                ],
                [],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(months=2),
                    )
                ],
                [
                    (
                        self.user_employee,
                        self.reference_datetime - relativedelta(months=4),
                    )
                ],
                [],
            ],
            [
                ("daily", self.reference_datetime.date()),
                ("daily", self.reference_datetime.date()),
                ("daily", self.reference_datetime.date()),
                ("daily", self.reference_datetime.date()),
                ("weekly", self.reference_datetime.date()),
                ("weekly", self.reference_datetime.date()),
                ("weekly", self.reference_datetime.date()),
                ("monthly", self.reference_datetime.date()),
                ("monthly", self.reference_datetime.date()),
                ("monthly", self.reference_datetime.date()),
                ("quarterly", self.reference_datetime.date()),
                ("quarterly", self.reference_datetime.date()),
                ("quarterly", self.reference_datetime.date()),
            ],
            [
                (
                    "daily",
                    self.reference_datetime.date() + relativedelta(days=1),
                    "Daily ok",
                ),
                (
                    "daily",
                    self.reference_datetime.date() + relativedelta(days=1),
                    "Daily ok, 2 days - 1 hour",
                ),
                (
                    "weekly",
                    self.reference_datetime.date() + relativedelta(weeks=1),
                    "Daily old logs (2 days + 1 hour)",
                ),
                (
                    "weekly",
                    self.reference_datetime.date() + relativedelta(weeks=1),
                    "Daily no logs",
                ),
                (
                    "weekly",
                    self.reference_datetime.date() + relativedelta(weeks=1),
                    "Weekly ok",
                ),
                (
                    "monthly",
                    self.reference_datetime.date() + relativedelta(months=1),
                    "Weekly old logs",
                ),
                (
                    "monthly",
                    self.reference_datetime.date() + relativedelta(months=1),
                    "Weekly no logs",
                ),
                (
                    "monthly",
                    self.reference_datetime.date() + relativedelta(months=1),
                    "Monthly ok",
                ),
                (
                    "quarterly",
                    self.reference_datetime.date() + relativedelta(months=3),
                    "Monthly old logs",
                ),
                (
                    "quarterly",
                    self.reference_datetime.date() + relativedelta(months=3),
                    "Monthly no logs",
                ),
                (
                    "quarterly",
                    self.reference_datetime.date() + relativedelta(months=3),
                    "Quaterly ok",
                ),
                (
                    "quarterly",
                    self.reference_datetime.date() + relativedelta(months=3),
                    "Quaterly ok",
                ),
                (
                    "quarterly",
                    self.reference_datetime.date() + relativedelta(months=3),
                    "Quaterly ok",
                ),
            ],
            strict=True,
        ):
            with self.subTest(
                logs=logs, msg=msg, periodicity=periodicity, run_date=run_date
            ):
                digest.write(
                    {
                        "next_run_date": run_date,
                        "periodicity": periodicity,
                    }
                )
                for log_user, log_dt in logs:
                    self._setup_logs_for_users(log_user, log_dt)

                with (
                    self.mock_datetime_and_now(self.reference_datetime),
                    self.mock_mail_gateway(),
                ):
                    digest.action_send()

                self.assertEqual(digest.next_run_date, exp_run_date)
                self.assertEqual(digest.periodicity, exp_periodicity)
                self.env["res.users.log"].with_user(SUPERUSER_ID).search([]).unlink()


@tagged("digest", "mail_mail", "-at_install", "post_install")
class TestUnsubscribe(MailCommon, HttpCaseWithUserDemo):
    def setUp(self):
        super().setUp()

        self.test_digest = self.env["digest.digest"].create(
            {
                "kpi_mail_message_total": True,
                "kpi_res_users_connected": True,
                "name": "My Digest",
                "periodicity": "daily",
                "user_ids": self.user_demo.ids,
            }
        )
        self.test_digest._action_subscribe_users(self.user_demo)
        self.base_url = self.test_digest.get_base_url()
        self.user_demo_unsubscribe_token = self.test_digest._get_unsubscribe_token(
            self.user_demo.id
        )

    def test_mail_mail_headers(self):
        digest = self.env["digest.digest"].browse(self.test_digest.ids)
        digest._action_subscribe_users(self.user_employee)

        with self.mock_mail_gateway():
            digest.action_send()

        for user in self.user_employee + self.user_demo:
            mail = self._find_mail_mail_wemail(user.email_formatted, "outgoing")
            headers = mail.headers
            unsubscribe_url = headers.get("List-Unsubscribe", "").strip("<>")
            self.assertTrue(unsubscribe_url)
            self.url_open(unsubscribe_url, method="POST")

        self.assertFalse(
            digest.user_ids, "Users should have been unsubscribed from digest"
        )

    def test_unsubscribe(self):
        digest = self.test_digest
        demo_token = digest._get_unsubscribe_token(self.user_demo.id)
        for test_user, is_member, is_logged, token, exp_code in [
            (self.user_demo, True, True, False, 200),
            (
                self.user_demo,
                False,
                True,
                False,
                200,
            ),
            (
                self.user_demo,
                False,
                False,
                demo_token,
                200,
            ),
            (
                self.user_demo,
                False,
                False,
                "probably-not-a-token",
                404,
            ),
            (
                self.user_demo,
                False,
                False,
                False,
                404,
            ),
        ]:
            with self.subTest(
                user_name=test_user.name,
                is_member=is_member,
                is_logged=is_logged,
                token=token,
            ):
                if is_member:
                    digest._action_subscribe_users(test_user)
                    self.assertIn(test_user, digest.user_ids)
                else:
                    digest._action_unsubscribe_users(test_user)
                    self.assertNotIn(test_user, digest.user_ids)

                self.authenticate(
                    test_user.login if is_logged else None,
                    test_user.login if is_logged else None,
                )
                if token:
                    response = self._url_unsubscribe(
                        token=token, user_id=test_user.id, method="POST"
                    )
                else:
                    response = self._url_unsubscribe(method="POST")
                self.assertEqual(response.status_code, exp_code)
                self.assertNotIn(test_user, digest.user_ids)

    def test_unsubscribe_token_one_click(self):
        self.assertIn(self.user_demo, self.test_digest.user_ids)
        self.authenticate(None, None)

        with mute_logger("odoo.addons.http_routing.models.ir_http"):
            response = self._url_unsubscribe(
                token=self.user_demo_unsubscribe_token,
                user_id=self.user_demo.id,
                one_click="1",
                method="GET",
            )
        self.assertEqual(response.status_code, 405, "GET method is not allowed")
        self.assertIn(self.user_demo, self.test_digest.user_ids)

        response = self._url_unsubscribe(
            token=self.user_demo_unsubscribe_token,
            user_id=self.user_demo.id,
            one_click="1",
            method="POST",
        )
        self.assertEqual(
            response.status_code,
            200,
            "Valid one-click unsubscribe just returns an OK 200",
        )
        self.assertNotIn(self.user_demo, self.test_digest.user_ids)

    def test_an_unsubscribe_link_asks_before_it_acts(self):
        self.authenticate(None, None)
        response = self._url_unsubscribe(
            token=self.user_demo_unsubscribe_token, user_id=self.user_demo.id
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self.user_demo, self.test_digest.user_ids, "a GET changes nothing"
        )
        with mute_logger("odoo.http"):
            forged = self._url_unsubscribe(token="forged", user_id=self.user_demo.id)
        self.assertEqual(forged.status_code, 404, "the page is for the token's holder")

        response = self._url_unsubscribe(
            token=self.user_demo_unsubscribe_token,
            user_id=self.user_demo.id,
            method="POST",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.user_demo, self.test_digest.user_ids)

    def _url_unsubscribe(self, token=None, user_id=None, one_click=None, method="GET"):
        url_params = {}
        if token is not None:
            url_params["token"] = token
        if user_id is not None:
            url_params["user_id"] = user_id
        if one_click is not None:
            unsubscribe_route = "unsubscribe_oneclick"
        else:
            unsubscribe_route = "unsubscribe"

        url = urls.urljoin(
            self.base_url,
            f"digest/{self.test_digest.id}/{unsubscribe_route}?{urlencode(url_params)}",
        )
        if method == "POST" and one_click is None:
            return self.url_open(
                url,
                data={"csrf_token": http.Request.csrf_token(self)},
                timeout=10,
                allow_redirects=True,
            )
        return self.url_open(url, timeout=10, allow_redirects=True, method=method)


@tagged("digest")
class TestDigestDefects(TestDigestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_tz = "America/Mexico_City"
        cls.company_1.partner_id.tz = cls.company_tz
        cls.env["mail.message"].search(
            [
                ("subtype_id", "=", cls.env.ref("mail.mt_comment").id),
                ("message_type", "in", ("comment", "email", "email_outgoing")),
            ]
        ).unlink()
        cls._setup_messages()


    @users("admin")
    def test_timeframes_are_naive_utc(self):
        digest = self.digest_1.with_user(self.env.user)
        now = datetime.now(UTC).replace(tzinfo=None)
        timeframes = digest._get_timeframes(self.company_1)

        self.assertEqual(len(timeframes), 3)
        for label, (current, previous) in timeframes:
            for bound in (*current, *previous):
                self.assertIsNone(
                    bound.tzinfo,
                    f"{label}: bounds reach Datetime.to_string(), which never converts",
                )
            self.assertLess(
                abs((current[1] - now).total_seconds()),
                60,
                f"{label}: the current window must end now, not {self.company_tz} now",
            )
            self.assertEqual(
                current[0],
                previous[1],
                f"{label}: the previous window must end where the current one starts",
            )

    @users("admin")
    def test_timeframe_bounds_reach_the_domain_unshifted(self):
        digest = self.digest_1.with_user(self.env.user)
        self.env["mail.message"].search(
            [
                ("subtype_id", "=", self.env.ref("mail.mt_comment").id),
                ("message_type", "in", ("comment", "email", "email_outgoing")),
            ]
        ).unlink()
        now = fields.Datetime.now()
        for hours_ago in (2, 5, 20, 26):
            self.partner_admin.message_post(
                author_id=self.partner_admin.id,
                body=f"{hours_ago}h ago",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                create_date=now - relativedelta(hours=hours_ago),
            )
        self.env.flush_all()

        _label, (current, __) = digest._get_timeframes(self.company_1)[0]
        start, end, __ = digest.with_context(
            start_datetime=current[0],
            end_datetime=current[1],
        )._get_kpi_compute_parameters()

        self.assertEqual(
            digest._get_kpi_value(
                "kpi_mail_message_total_value",
                current,
                self.company_1,
                self.env.user,
            ),
            3,
            f"window {start} .. {end} must be the real last 24 hours",
        )


    @users("admin")
    def test_margin_reports_a_fall_to_zero(self):
        digest = self.digest_1.with_user(self.env.user)
        for value, previous, expected in [
            (0, 0, 0.0),
            (10, 10, 0.0),
            (0, 10, -100.0),
            (10, 0, 0.0),
            (-5, 0, 0.0),
            (10, 5, 100.0),
            (5, 10, -50.0),
            (1, 3, -66.67),
            (-10, -5, 100.0),
        ]:
            with self.subTest(value=value, previous=previous):
                self.assertEqual(digest._get_margin_value(value, previous), expected)


    @users("admin")
    def test_tips_are_consumed_one_by_one(self):
        Tip = self.env["digest.tip"].sudo()
        Tip.search([]).unlink()
        tip_a, tip_b = Tip.create(
            [
                {
                    "name": "Tip A",
                    "sequence": 1,
                    "tip_description": "<p>A</p>",
                    "user_ids": [Command.link(self.user_admin.id)],
                },
                {
                    "name": "Tip B",
                    "sequence": 2,
                    "tip_description": "<p>B</p>",
                    "user_ids": [Command.link(self.user_employee.id)],
                },
            ]
        )
        reader = self.env["res.users"].create(
            {
                "name": "Tip Reader",
                "login": "digest_tip_reader",
                "group_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )

        preview = self.digest_1.with_user(self.env.user)._acquire_tips(
            self.company_1, reader, tips_count=2, consumed=False
        )
        self.assertEqual(len(preview), 2)
        self.assertTrue(all(isinstance(tip, str) for tip in preview))
        self.assertEqual(tip_a.user_ids, self.user_admin)
        self.assertEqual(tip_b.user_ids, self.user_employee)
        consumed = self.digest_1.with_user(self.env.user)._acquire_tips(
            self.company_1,
            reader,
            tips_count=2,
            consumed=True,
        )
        self.assertEqual(consumed, preview)

        self.assertEqual(
            tip_a.user_ids,
            self.user_admin + reader,
            "Tip A must gain the reader and nothing else",
        )
        self.assertEqual(
            tip_b.user_ids,
            self.user_employee + reader,
            "Tip B must gain the reader and nothing else",
        )


    def test_is_subscribed_is_the_reader_s_own(self):
        digest = self.digest_1
        digest._action_subscribe_users(self.user_admin)
        digest._action_unsubscribe_users(self.user_employee)

        self.assertTrue(digest.with_user(self.user_admin).is_subscribed)
        self.assertFalse(
            digest.with_user(self.user_employee).is_subscribed,
            "the employee is not a recipient, whoever read the field first",
        )
        self.assertTrue(digest.with_user(self.user_admin).is_subscribed)

    @users("admin")
    def test_reading_one_digest_s_kpi_keeps_the_others_warm(self):
        digest = self.digest_1.with_user(self.env.user)
        others = self.env["digest.digest"].create(
            [
                {"name": f"Bystander {i}", "kpi_mail_message_total": True}
                for i in range(5)
            ]
        )
        window = digest._get_timeframes(self.company_1)[0][1][0]
        warm = others.with_context(start_datetime=window[0], end_datetime=window[1])
        warm.mapped("kpi_mail_message_total_value")

        with self.assertQueryCount(0):
            warm.mapped("kpi_mail_message_total_value")

        digest._get_kpi_value(
            "kpi_mail_message_total_value",
            window,
            self.company_1,
            self.env.user,
        )

        with self.assertQueryCount(0):
            warm.mapped("kpi_mail_message_total_value")

    @users("admin")
    def test_a_denied_kpi_is_resolved_once_not_once_per_column(self):
        digest = self.digest_1.with_user(self.env.user)
        calls = []
        denied = AccessError("nope")

        def _refuse(records):
            calls.append(records)
            raise denied

        with patch.object(
            type(digest),
            "_compute_kpi_mail_message_total_value",
            _refuse,
        ):
            kpi_data = digest._get_kpi_data(self.company_1, self.user_admin)

        self.assertEqual(len(calls), 2, "one column asks, the ORM retries once")
        self.assertNotIn(
            "kpi_mail_message_total",
            [kpi["kpi_name"] for kpi in kpi_data],
            "a KPI the reader cannot see stays out of their mail",
        )


    @users("admin")
    def test_one_scan_answers_every_window_with_the_same_numbers(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        digest.write(dict.fromkeys(digest._get_kpi_boolean_names(), True))
        self.env.flush_all()

        batched = digest._get_kpi_data(self.company_1, self.user_admin)

        original = type(digest)._read_kpi_over_windows
        try:
            type(digest)._read_kpi_over_windows = lambda *a, **kw: None
            per_window = digest._get_kpi_data(self.company_1, self.user_admin)
        finally:
            type(digest)._read_kpi_over_windows = original

        self.assertTrue(batched, "the digest must render at least one KPI")
        self.assertEqual(
            [kpi["kpi_name"] for kpi in batched],
            [kpi["kpi_name"] for kpi in per_window],
        )
        for one, six in zip(batched, per_window, strict=True):
            for col in ("kpi_col1", "kpi_col2", "kpi_col3"):
                with self.subTest(kpi=one["kpi_name"], col=col):
                    self.assertEqual(one[col], six[col])

    @users("admin")
    def test_one_scan_is_one_query_and_six_answers(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        windows = tuple(
            (fields.Datetime.to_string(s), fields.Datetime.to_string(e))
            for __, pair in digest._get_timeframes(self.company_1)
            for s, e in pair
        )
        scoped = digest.with_context(digest_windows=windows)
        memo = {}
        self.cr.cache[KPI_AGGREGATE_MEMO] = memo
        try:
            self.env.invalidate_all()
            scoped._read_kpi_over_windows(
                "kpi_warm",
                "res.users",
                "create_date",
                Domain.TRUE,
                None,
                self.company_1,
            )
            with counting_statements(self.cr) as statements:
                one_scan = scoped._read_kpi_over_windows(
                    "kpi_probe",
                    "res.users",
                    "create_date",
                    Domain.TRUE,
                    None,
                    self.company_1,
                )
                spent = statements.count
        finally:
            self.cr.cache.pop(KPI_AGGREGATE_MEMO, None)

        self.assertEqual(spent, 1, "six windows, one query")
        per_company = one_scan[self.company_1.id]
        self.assertEqual(len(per_company), 6, "and six answers out of it")

        expected = []
        for start, end in windows:
            rows = self.env["res.users"]._read_group(
                domain=Domain(
                    [
                        ("company_id", "in", self.company_1.ids),
                        ("create_date", ">=", start),
                        ("create_date", "<", end),
                    ]
                ),
                groupby=["company_id"],
                aggregates=["__count"],
            )
            expected.append({c.id: n for c, n in rows}.get(self.company_1.id, 0))
        self.assertEqual([per_company[w] for w in windows], expected)

    @users("admin")
    def test_one_scan_sees_a_sum_the_ORM_has_not_written_yet(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        rate = self.env["res.currency.rate"].create(
            {
                "name": "2001-01-01",
                "rate": 2.0,
                "currency_id": self.env.ref("base.EUR").id,
                "company_id": self.company_1.id,
            }
        )
        self.assertTrue(self.env["res.currency.rate"]._fields["rate"].store)
        window = ("2000-01-01 00:00:00", "2100-01-01 00:00:00")

        def summed():
            self.cr.cache[KPI_AGGREGATE_MEMO] = {}
            try:
                out = digest.with_context(
                    digest_windows=(window,)
                )._read_kpi_over_windows(
                    "kpi_flush_probe",
                    "res.currency.rate",
                    "create_date",
                    Domain([("id", "=", rate.id)]),
                    "rate",
                    self.company_1,
                )
            finally:
                self.cr.cache.pop(KPI_AGGREGATE_MEMO, None)
            return out.get(self.company_1.id, {}).get(window, 0)

        self.env.flush_all()
        self.assertEqual(summed(), rate.rate)

        rate.rate = 99.0
        self.cr.execute("SELECT rate FROM res_currency_rate WHERE id = %s", (rate.id,))
        self.assertNotEqual(self.cr.fetchone()[0], 99.0, "the row is still stale")
        self.assertEqual(summed(), 99.0, "the scan must flush before it reads")

    @users("admin")
    def test_a_non_stored_date_field_takes_the_slow_path(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        self.assertFalse(self.env["res.users"]._fields["login_date"].store)
        windows = tuple(
            (fields.Datetime.to_string(s), fields.Datetime.to_string(e))
            for __, pair in digest._get_timeframes(self.company_1)
            for s, e in pair
        )
        self.cr.cache[KPI_AGGREGATE_MEMO] = {}
        try:
            declined = digest.with_context(
                digest_windows=windows
            )._read_kpi_over_windows(
                "kpi_res_users_connected_value",
                "res.users",
                "login_date",
                Domain.TRUE,
                None,
                self.company_1,
            )
        finally:
            self.cr.cache.pop(KPI_AGGREGATE_MEMO, None)
        self.assertIsNone(declined, "declined, not raised")

        self.env["res.users"].with_user(self.user_employee)._update_last_login()
        self.all_digests.invalidate_recordset()
        self.assertEqual(self.digest_1.kpi_res_users_connected_value, 1)

    @users("admin")
    def test_the_memo_cannot_serve_one_kpi_s_answer_to_another(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        windows = tuple(
            (fields.Datetime.to_string(s), fields.Datetime.to_string(e))
            for __, pair in digest._get_timeframes(self.company_1)
            for s, e in pair
        )
        memo = {}
        self.cr.cache[KPI_AGGREGATE_MEMO] = memo
        try:
            scoped = digest.with_context(digest_windows=windows)
            everything = scoped._read_kpi_over_windows(
                "kpi_a", "res.users", "create_date", Domain.TRUE, None, self.company_1
            )
            nothing = scoped._read_kpi_over_windows(
                "kpi_b",
                "res.users",
                "create_date",
                Domain([("login", "=", "__nobody__")]),
                None,
                self.company_1,
            )
        finally:
            self.cr.cache.pop(KPI_AGGREGATE_MEMO, None)

        self.assertEqual(len(memo), 2, "two KPIs, two memo entries")
        self.assertNotEqual(
            everything,
            nothing,
            "the impossible domain must not read the other KPI back",
        )
        self.assertFalse(any(nothing.values()), "nothing matches that domain")

    @users("admin")
    def test_the_memo_does_not_outlive_the_render(self):
        digest = self.env["digest.digest"].browse(self.digest_1.ids)
        digest._get_kpi_data(self.company_1, self.user_admin)
        self.assertNotIn(
            KPI_AGGREGATE_MEMO,
            self.cr.cache,
            "a memo left on the cursor would answer the next recipient",
        )

    @users("admin")
    def test_slowdown_costs_one_read_group_whatever_the_batch(self):
        Digest = self.env["digest.digest"]

        def measure(count):
            digests = Digest.create(
                [
                    {
                        "name": f"Slowdown {count}-{i}",
                        "periodicity": "daily",
                        "user_ids": [Command.link(self.user_employee.id)],
                    }
                    for i in range(count)
                ]
            )
            self.env.flush_all()
            self.env.invalidate_all()
            with counting_statements(self.cr) as statements:
                digests._get_digests_to_slowdown()
                return statements.count

        small, large = measure(2), measure(20)
        self.assertLessEqual(
            large - small,
            2,
            f"18 further digests cost {large - small} extra queries; the log "
            f"lookup is one _read_group for the whole recordset",
        )

    @users("admin")
    def test_slowdown_still_reads_the_recipients_logs(self):
        Digest = self.env["digest.digest"]
        Log = self.env["res.users.log"].with_user(SUPERUSER_ID)
        Log.search([]).unlink()

        awake, asleep, empty = Digest.create(
            [
                {
                    "name": "Awake",
                    "periodicity": "daily",
                    "user_ids": [Command.link(self.user_employee.id)],
                },
                {
                    "name": "Asleep",
                    "periodicity": "daily",
                    "user_ids": [Command.link(self.user_admin.id)],
                },
                {"name": "No recipients", "periodicity": "daily"},
            ]
        )
        Log.create({"create_uid": self.user_employee.id})
        self.env.flush_all()

        to_slowdown = (awake + asleep + empty)._get_digests_to_slowdown()
        self.assertEqual(to_slowdown, asleep + empty)


    def test_periodicity_table_is_the_selection(self):
        selection = self.env["digest.digest"]._fields["periodicity"].selection
        self.assertEqual(
            [value for value, __ in selection],
            list(PERIODICITIES),
            "the selection is PERIODICITY_SELECTION; an override would be a copy",
        )
        for name, periodicity in PERIODICITIES.items():
            with self.subTest(periodicity=name):
                self.assertIn(periodicity.slower, PERIODICITIES)
                self.assertTrue(periodicity.label)
        self.assertEqual(
            PERIODICITIES["quarterly"].slower,
            "quarterly",
            "quarterly is the floor: there is nothing slower to fall back to",
        )

    def test_get_next_periodicity_covers_every_slower_target(self):
        digest = self.env["digest.digest"].create(
            {"name": "Test", "periodicity": "daily"}
        )
        for name, periodicity in PERIODICITIES.items():
            if name == periodicity.slower:
                continue
            with self.subTest(periodicity=name):
                digest.periodicity = name
                slower, label = digest._get_next_periodicity()
                self.assertEqual(slower, periodicity.slower)
                self.assertTrue(label)

    def test_auto_subscription_honours_the_unticked_setting(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("digest.default_digest_emails", "False")
        icp.set_param("digest.default_digest_id", str(self.digest_1.id))

        user = self.env["res.users"].create(
            {
                "name": "Unsubscribed By Default",
                "login": "digest_setting_off",
                "group_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )
        self.assertNotIn(user, self.digest_1.user_ids)

        icp.set_param("digest.default_digest_emails", "True")
        subscribed = self.env["res.users"].create(
            {
                "name": "Subscribed By Default",
                "login": "digest_setting_on",
                "group_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )
        self.assertIn(subscribed, self.digest_1.user_ids)

    def test_auto_subscription_survives_a_broken_parameter(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("digest.default_digest_emails", "True")
        icp.set_param("digest.default_digest_id", "not-an-id")

        user = self.env["res.users"].create(
            {
                "name": "Created Anyway",
                "login": "digest_bad_param",
                "group_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )
        self.assertTrue(user.id)

    @users("admin")
    def test_create_rejects_a_bad_periodicity_the_ORM_s_way(self):
        with self.assertRaises(ValueError) as caught:
            self.env["digest.digest"].create({"name": "Bad", "periodicity": "hourly"})
        self.assertNotIsInstance(caught.exception, KeyError)
        self.assertIn("hourly", str(caught.exception))

    @users("admin")
    def test_log_attribution_sticks_whatever_the_test_phase(self):
        logs = self._setup_logs_for_users(
            self.user_employee + self.user_admin,
            datetime(2024, 2, 13, 13, 30, 0),
        )
        self.assertEqual(logs.create_uid, self.user_employee + self.user_admin)

    def test_cron_sends_every_due_digest_and_leaves_the_rest(self):
        Digest = self.env["digest.digest"]
        Digest.search([]).write({"state": "deactivated"})
        today = fields.Date.today()
        due, not_yet, deactivated = Digest.create(
            [
                {
                    "name": "Due",
                    "next_run_date": today,
                    "user_ids": [Command.link(self.user_employee.id)],
                },
                {
                    "name": "Not yet",
                    "next_run_date": today + relativedelta(days=3),
                    "user_ids": [Command.link(self.user_employee.id)],
                },
                {
                    "name": "Deactivated",
                    "next_run_date": today,
                    "user_ids": [Command.link(self.user_employee.id)],
                },
            ]
        )
        deactivated.action_deactivate()
        self._setup_logs_for_users(self.user_employee, fields.Datetime.now())
        self.env.flush_all()

        budget = []

        def _commit_progress(cron, processed=0, *, remaining=None, deactivate=False):
            budget.append((processed, remaining))
            return float("inf")

        with (
            patch.object(
                type(self.env["ir.cron"]), "_commit_progress", _commit_progress
            ),
            self.mock_mail_gateway(),
        ):
            Digest._cron_send_digest_email()

        self.assertEqual(
            len(self._new_mails), 1, "only the due, activated digest sends"
        )
        self.assertEqual(self._new_mails.email_to, self.user_employee.email_formatted)
        self.assertEqual(budget[0], (0, 1), "the total is announced once, and it is 1")
        self.assertEqual(due.next_run_date, today + relativedelta(days=1))
        self.assertEqual(
            not_yet.next_run_date,
            today + relativedelta(days=3),
            "a digest that is not due is not touched",
        )
        self.assertEqual(deactivated.next_run_date, today)

    def test_cron_stops_when_the_budget_runs_out(self):
        Digest = self.env["digest.digest"]
        Digest.search([]).write({"state": "deactivated"})
        today = fields.Date.today()
        digests = Digest.create(
            [{"name": f"Batch {i}", "next_run_date": today} for i in range(25)]
        )
        self.env.flush_all()
        calls = []

        def _commit_progress(cron, processed=0, *, remaining=None, deactivate=False):
            calls.append(processed)
            return 0.0 if len(calls) >= 3 else float("inf")

        with (
            patch.object(
                type(self.env["ir.cron"]), "_commit_progress", _commit_progress
            ),
            self.mock_mail_gateway(),
        ):
            Digest._cron_send_digest_email()

        moved = digests.filtered(lambda d: d.next_run_date != today)
        self.assertEqual(len(moved), 20, "two batches of ten ran, then it gave up")
        self.assertEqual(
            len(digests) - len(moved),
            5,
            "the five left over are still due on the next pass, not skipped",
        )

    def test_a_broken_kpi_does_not_abort_the_whole_batch(self):
        Digest = self.env["digest.digest"]
        Digest.search([]).write({"state": "deactivated"})
        today = fields.Date.today()
        bad, good = Digest.create(
            [
                {
                    "name": "Bad Digest (broken KPI)",
                    "next_run_date": today,
                    "periodicity": "daily",
                    "kpi_res_users_connected": True,
                    "user_ids": [Command.link(self.user_employee.id)],
                },
                {
                    "name": "Good Digest",
                    "next_run_date": today,
                    "periodicity": "daily",
                    "user_ids": [Command.link(self.user_employee.id)],
                },
            ]
        )
        self._setup_logs_for_users(self.user_employee, fields.Datetime.now())
        self.env.flush_all()

        def _raise(records):
            raise ZeroDivisionError("broken KPI formula")

        with (
            patch.object(type(bad), "_compute_kpi_res_users_connected_value", _raise),
            self.mock_mail_gateway(),
        ):
            (bad + good).action_send()

        self.assertEqual(len(self._new_mails), 1, "the good digest still gets its mail")
        self.assertEqual(self._new_mails.email_to, self.user_employee.email_formatted)
        self.assertEqual(
            bad.next_run_date,
            today + relativedelta(days=1),
            "the broken digest is still rescheduled, not stuck retrying forever",
        )
        self.assertEqual(good.next_run_date, today + relativedelta(days=1))

    @users("admin")
    def test_create_seeds_the_run_date_without_a_second_write(self):
        digests = self.env["digest.digest"].create(
            [
                {"name": "Seeded daily", "periodicity": "daily"},
                {"name": "Seeded quarterly", "periodicity": "quarterly"},
                {"name": "Seeded default"},
                {"name": "Explicit", "next_run_date": date(2030, 1, 1)},
            ]
        )
        today = fields.Date.today()
        self.assertEqual(digests[0].next_run_date, today + relativedelta(days=1))
        self.assertEqual(
            digests[1].next_run_date,
            today + relativedelta(months=3),
            "quarterly had no branch of its own, only a bare else",
        )
        self.assertEqual(digests[2].next_run_date, today + relativedelta(days=1))
        self.assertEqual(
            digests[3].next_run_date,
            date(2030, 1, 1),
            "an explicit date is never overwritten",
        )


@tagged("digest", "-at_install", "post_install")
class TestUnsubscribeRoutes(MailCommon, HttpCaseWithUserDemo):
    def test_both_spellings_of_the_one_click_route_answer(self):
        for route, user in [
            ("unsubscribe_oneclik", self.user_demo),
            ("unsubscribe_oneclick", self.user_employee),
        ]:
            with self.subTest(route=route):
                digest = self.env["digest.digest"].create(
                    {
                        "name": "Route Digest",
                        "user_ids": user.ids,
                    }
                )
                token = digest._get_unsubscribe_token(user.id)
                url = urls.urljoin(
                    digest.get_base_url(),
                    f"digest/{digest.id}/{route}?{urlencode({'token': token, 'user_id': user.id})}",
                )
                response = self.url_open(url, method="POST", timeout=10)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(user, digest.user_ids)

    def test_set_periodicity_refuses_what_the_field_refuses(self):
        digest = self.env["digest.digest"].create({"name": "Periodicity Digest"})
        self.authenticate("admin", "admin")
        base = digest.get_base_url()

        with mute_logger("odoo.addons.http_routing.models.ir_http"):
            response = self.url_open(
                urls.urljoin(
                    base, f"digest/{digest.id}/set_periodicity?periodicity=hourly"
                ),
                timeout=10,
            )
        self.assertEqual(
            response.status_code, 404, "not a 500 out of a bare ValueError"
        )
        self.assertEqual(digest.periodicity, "daily")

        response = self.url_open(
            urls.urljoin(
                base, f"digest/{digest.id}/set_periodicity?periodicity=weekly"
            ),
            timeout=10,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(digest.periodicity, "weekly")

    def test_set_periodicity_on_a_deleted_digest_is_a_404(self):
        digest = self.env["digest.digest"].create({"name": "Doomed"})
        digest_id, base_url = digest.id, digest.get_base_url()
        digest.unlink()
        self.authenticate("admin", "admin")

        with mute_logger("odoo.addons.http_routing.models.ir_http"):
            response = self.url_open(
                urls.urljoin(
                    base_url, f"digest/{digest_id}/set_periodicity?periodicity=weekly"
                ),
                timeout=10,
            )
        self.assertEqual(
            response.status_code,
            404,
            "it used to redirect to /odoo/digest.digest/False",
        )
