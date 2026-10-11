from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import TestCommonPlanning
from odoo.addons.base.models.access_link import hash_token
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install", "access_link")
class TestPlanningPageLinks(HttpCase, TestCommonPlanning):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpEmployees()
        start = datetime.combine(
            fields.Date.today() + timedelta(days=7), datetime.min.time()
        )
        cls.planning = cls.env["planning.planning"].create(
            {
                "start_datetime": start,
                "end_datetime": start + timedelta(days=7),
                "include_unassigned": True,
            }
        )

    def _page_url(self, resource, token=None):
        return "/planning/%s/%s" % (
            token or self.planning._page_token(resource),
            resource.sudo().planning_token,
        )

    def _links(self):
        return (
            self.env["access.link"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "planning.planning"),
                    ("res_id", "=", self.planning.id),
                ]
            )
        )

    def test_a_schedule_page_is_a_link_in_the_persons_name(self):
        token = self.planning._page_token(self.resource_bert)
        link = self._links()
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.cause_res_id),
            (1, self.resource_bert.partner_id, "comment", self.resource_bert.id),
        )
        self.assertEqual(link.date_to, self.planning.end_datetime + timedelta(days=30))
        self.assertEqual(link.token_hash, hash_token(token))
        self.assertEqual(self.planning._page_token(self.resource_bert), token)
        self.assertNotEqual(self.planning._page_token(self.resource_joseph), token)

    @mute_logger("odoo.http")
    def test_a_page_link_opens_its_own_persons_page_only(self):
        self.authenticate(None, None)
        self.assertEqual(
            self.url_open(self._page_url(self.resource_bert)).status_code, 200
        )
        bert_token = self.planning._page_token(self.resource_bert)
        joseph_with_bert = self._page_url(self.resource_joseph, bert_token)
        self.assertEqual(self.url_open(joseph_with_bert).status_code, 404)
        self.assertEqual(
            self.url_open(
                self._page_url(self.resource_bert, self.planning.access_token)
            ).status_code,
            404,
            "the feed's token is not a page link",
        )

    @mute_logger("odoo.http")
    def test_the_calendar_feed_stays_until_its_person_resets_it(self):
        feed = "/planning/%s/%s.ics" % (
            self.planning.access_token,
            self.resource_bert.sudo().planning_token,
        )
        self.authenticate(None, None)
        self.assertEqual(self.url_open(feed).status_code, 200)
        self.resource_bert.action_reset_planning_token()
        self.assertEqual(self.url_open(feed).status_code, 404)

    @mute_logger("odoo.http")
    def test_a_user_s_unavailable_link_unassigns_their_own_shift_only(self):
        self.env.company.planning_employee_unavailabilities = "unassign"
        self.employee_bert.user_id = mail_new_test_user(
            self.env, login="bert_user", groups="base.group_user"
        )
        start = self.planning.start_datetime + timedelta(hours=8)
        bert_shift, joseph_shift = self.env["planning.slot"].create(
            [
                {
                    "resource_id": resource.id,
                    "start_datetime": start,
                    "end_datetime": start + timedelta(hours=4),
                }
                for resource in (self.resource_bert, self.resource_joseph)
            ]
        )
        self.authenticate("bert_user", "bert_user")

        own = self.url_open(
            "/planning/unassign/%s/%s"
            % (self.resource_bert.sudo().planning_token, bert_shift.id),
            allow_redirects=False,
        )
        other = self.url_open(
            "/planning/unassign/%s/%s"
            % (self.resource_joseph.sudo().planning_token, joseph_shift.id),
            allow_redirects=False,
        )

        self.assertEqual(own.status_code, 303)
        self.assertFalse(bert_shift.resource_id)
        self.assertEqual(other.status_code, 404)
        self.assertEqual(joseph_shift.resource_id, self.resource_joseph)

    def _shift(self, start):
        return self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "start_datetime": start,
                "end_datetime": start + timedelta(hours=4),
            }
        )

    def _slot_links(self, slot):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", "planning.slot"), ("res_id", "=", slot.id)])
        )

    @mute_logger("odoo.http")
    def test_a_shift_calendar_file_is_a_link_in_its_persons_name(self):
        shift = self._shift(self.planning.start_datetime + timedelta(hours=8))
        bert_url = shift._get_ics_url(self.resource_bert.partner_id)
        joseph_url = shift._get_ics_url(self.resource_joseph.partner_id)
        bert_link = self._slot_links(shift).filtered(
            lambda link: link.partner_id == self.resource_bert.partner_id
        )

        self.assertNotEqual(bert_url, joseph_url)
        self.assertEqual(
            (bert_link.role, bert_link.date_to),
            ("view", shift.end_datetime + timedelta(days=30)),
        )
        self.authenticate(None, None)
        self.assertEqual(self.url_open(bert_url).status_code, 200)
        bert_link.action_revoke("a test")
        self.assertEqual(self.url_open(bert_url).status_code, 404)
        self.assertEqual(self.url_open(joseph_url).status_code, 200)
        self.assertEqual(self.url_open("/slot/%s.ics" % ("x" * 32)).status_code, 404)

    def test_a_shift_far_ahead_keeps_its_link_until_a_month_after_it(self):
        far = datetime.combine(
            fields.Date.today() + timedelta(days=730), datetime.min.time()
        )
        shift = self._shift(far)
        shift._get_ics_url(self.resource_bert.partner_id)
        self.assertEqual(
            self._slot_links(shift).date_to, shift.end_datetime + timedelta(days=30)
        )
        shift.write(
            {
                "start_datetime": far - timedelta(days=700),
                "end_datetime": far - timedelta(days=700) + timedelta(hours=4),
            }
        )
        self.assertEqual(
            self._slot_links(shift).date_to, shift.end_datetime + timedelta(days=30)
        )

    def test_a_shift_reshaped_by_a_template_moves_its_link(self):
        start = datetime.combine(
            fields.Date.today() + timedelta(days=400), datetime.min.time()
        )
        shift = self._shift(start)
        shift.end_datetime = start + timedelta(days=100)
        shift._get_ics_url(self.resource_bert.partner_id)
        template = self.env["planning.slot.template"].create(
            {"start_time": 8.0, "end_time": 12.0, "duration_days": 1}
        )
        shift.write({"template_id": template.id})
        self.assertLess(shift.end_datetime, start + timedelta(days=2))
        self.assertEqual(
            self._slot_links(shift).date_to, shift.end_datetime + timedelta(days=30)
        )

    def test_a_past_shift_s_link_lives_a_month_from_issue(self):
        shift = self._shift(datetime(2023, 6, 2, 8, 0))
        shift._get_ics_url(self.resource_bert.partner_id)

        self.assertGreater(
            self._slot_links(shift).date_to,
            fields.Datetime.now() + timedelta(days=29),
        )
