import random
import time
from datetime import timedelta
from logging import getLogger

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tests.common import warmup

from odoo.addons.calendar.tests.booking.common import AppointmentCommon

_logger = getLogger(__name__)


class AppointmentPerformanceCase(AppointmentCommon):
    def setUp(self):
        super().setUp()
        self.patch(self.env.registry, "ready", True)
        self._mock_smtplib_connection()


class AppointmentUIPerformanceCase(AppointmentPerformanceCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        shipped_type_ids = (
            cls.env["ir.model.data"]
            .search([("model", "=", "appointment.type")])
            .mapped("res_id")
        )
        cls.env["appointment.type"].browse(shipped_type_ids).exists().active = False
        cls._website_renders_the_page = "website" in cls.env
        cls._page_reads_the_type_seo = (
            "website_meta_title" in cls.env["appointment.type"]._fields
        )
        cls._layout_reads_the_team_menus = bool(
            "team.team" in cls.env
            and "website_menu_id" in cls.env["team.team"]._fields
            and cls.env["team.team"]
            .sudo()
            .search_count([("website_menu_id", "!=", False)])
        )

        if "website" in cls.env and "channel_id" in cls.env["website"]:
            cls.env["website"].search([]).channel_id = False

            cls.env["website.menu"].search(
                [
                    ("url", "=like", "/%/%-%"),
                ]
            ).unlink()


@tagged("appointment_performance", "post_install", "-at_install")
class OnlineAppointmentPerformance(AppointmentUIPerformanceCase):
    def setUp(self):
        super().setUp()
        self._create_meetings(
            self.staff_user_bxls,
            [
                (
                    self.reference_monday + timedelta(days=1),
                    self.reference_monday + timedelta(days=1, hours=3),
                    False,
                ),
                (
                    self.reference_monday
                    + timedelta(days=7),
                    self.reference_monday + timedelta(days=7, hours=1),
                    True,
                ),
            ],
        )

        if "product.pricelist" in self.env:
            self.env["product.pricelist"].search([]).write({"active": False})

        self.flush_tracking()

    @warmup
    def test_appointment_invitation_page_anonymous(self):
        random.seed(1871)
        invitation = self.env["appointment.invite"].create(
            {
                "short_code": "spock",
                "appointment_type_ids": self.apt_type_bxls_2days.ids,
            }
        )

        self.authenticate(None, None)
        t0 = time.time()
        with freeze_time(self.reference_now):
            with self.assertQueryCount(
                default=(29 + self._layout_reads_the_team_menus)
                if self._website_renders_the_page
                else 26
            ):
                response = self._test_url_open(invitation.redirect_url)
        self.assertEqual(response.status_code, 200)
        t1 = time.time()

        _logger.info("Browsed %s, time %.3f", invitation.redirect_url, t1 - t0)

    @warmup
    def test_appointment_type_page_website_authenticated(self):
        random.seed(1871)
        self.apt_type_bxls_2days.is_published = True

        self.authenticate("staff_user_aust", "staff_user_aust")
        t0 = time.time()
        with freeze_time(self.reference_now):
            with self.assertQueryCount(
                (34 + self._page_reads_the_type_seo)
                if self._website_renders_the_page
                else 30
            ):
                response = self._test_url_open(
                    "/appointment/%i" % self.apt_type_bxls_2days.id
                )
        self.assertEqual(response.status_code, 200)
        t1 = time.time()

        _logger.info(
            "Browsed /appointment/%i, time %.3f", self.apt_type_bxls_2days.id, t1 - t0
        )
