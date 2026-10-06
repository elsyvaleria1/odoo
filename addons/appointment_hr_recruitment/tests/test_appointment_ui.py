from datetime import datetime, timedelta

from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged, users

from odoo.addons.calendar.tests.booking.common import AppointmentCommon


@tagged("appointment_ui", "post_install", "-at_install")
class AppointmentCrmUITest(AppointmentCommon, common.HttpCase):
    @users("apt_manager")
    def test_route_create_custom_with_context(self):
        self.authenticate(self.env.user.login, self.env.user.login)
        now = datetime.now()
        unique_slots = [
            {
                "start": (now + timedelta(hours=1))
                .replace(microsecond=0)
                .isoformat(" "),
                "end": (now + timedelta(hours=2)).replace(microsecond=0).isoformat(" "),
                "allday": False,
            },
            {
                "start": (now + timedelta(days=2))
                .replace(microsecond=0)
                .isoformat(" "),
                "end": (now + timedelta(days=3)).replace(microsecond=0).isoformat(" "),
                "allday": True,
            },
        ]
        dep_rd = (
            self.env["hr.department"]
            .sudo()
            .create(
                {
                    "name": "Research & Development",
                }
            )
        )
        job_developer = (
            self.env["hr.job"]
            .sudo()
            .create(
                {
                    "name": "Test Job",
                    "department_id": dep_rd.id,
                    "no_of_recruitment": 5,
                }
            )
        )
        applicant = (
            self.env["hr.applicant"]
            .sudo()
            .create(
                {
                    "partner_name": "Test Applicant",
                    "job_id": job_developer.id,
                }
            )
        )
        request = self.url_open(
            "/appointment/appointment_type/create_custom",
            data=json_dumps(
                {
                    "params": {
                        "slots": unique_slots,
                        "context": {
                            "default_is_auto_assign": True,
                            "default_applicant_id": applicant.id,
                        },
                    }
                }
            ),
            headers={"Content-Type": "application/json"},
        ).json()
        result = request.get("result", {})
        self.assertTrue(
            result.get("appointment_type_id"),
            "The request returns the id of the custom appointment type",
        )

        appointment_type = self.env["appointment.type"].browse(
            result["appointment_type_id"]
        )
        # The default_is_auto_assign should be ignored as the field is not whitelisted
        self.assertFalse(appointment_type.is_auto_assign)
        # applicant_id is not whitelisted in this module, unlike appointment_crm's opportunity_id
        self.env["appointment.invite"].search(
            [("appointment_type_ids", "in", appointment_type.ids)]
        )
