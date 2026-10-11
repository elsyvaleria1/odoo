from datetime import datetime

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.integration_twilio.tests.common import MockSmsTwilio

DID = "+527221234567"


def _call(sid, direction, caller, called, start, end, status="completed", trunk="TK1"):
    return {
        "sid": sid,
        "trunk_sid": trunk,
        "direction": direction,
        "from": caller,
        "to": called,
        "status": status,
        "start_time": start,
        "end_time": end,
        "duration": "42",
        "price": "-0.0130",
        "price_unit": "USD",
    }


@tagged("post_install", "-at_install", "twilio")
class TestTwilioTrunkCalls(MockSmsTwilio):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_sms_twilio(cls.company_admin)
        cls.reported = cls.env["phone.call"].create(
            {
                "channel": "pbx",
                "direction": "incoming",
                "state": "terminated",
                "phone_number": "7225550101",
                "start_date": datetime(2026, 10, 6, 9, 0, 40),
                "end_date": datetime(2026, 10, 6, 9, 1, 22),
                "company_id": cls.company_admin.id,
            }
        )

    @freeze_time("2026-10-06 14:00:00")
    def test_trunk_calls_are_matched_to_the_phone_system_reports(self):
        calls = [
            _call(
                "CA1",
                "trunking-originating",
                "+527225550101",
                f"sip:{DID}@pbx.example.mx:5061",
                "Tue, 06 Oct 2026 09:00:00 +0000",
                "Tue, 06 Oct 2026 09:01:22 +0000",
            ),
            _call(
                "CA2",
                "trunking-terminating",
                DID,
                "+527225550202",
                "Tue, 06 Oct 2026 10:00:00 +0000",
                "Tue, 06 Oct 2026 10:03:00 +0000",
            ),
            _call(
                "CA3",
                "trunking-terminating",
                DID,
                "+527225550303",
                "Tue, 06 Oct 2026 10:30:00 +0000",
                "Tue, 06 Oct 2026 10:30:05 +0000",
                status="busy",
            ),
            _call(
                "CA4",
                "trunking-originating",
                "+527225550404",
                DID,
                "Tue, 06 Oct 2026 12:58:00 +0000",
                "Tue, 06 Oct 2026 13:00:00 +0000",
            ),
            _call(
                "CA5",
                "outbound-api",
                DID,
                "+527225550505",
                "Tue, 06 Oct 2026 11:00:00 +0000",
                "Tue, 06 Oct 2026 11:01:00 +0000",
                trunk=None,
            ),
            _call(
                "CA6",
                "trunking-originating",
                "+527225550606",
                DID,
                "Tue, 06 Oct 2026 13:59:00 +0000",
                None,
                status="ringing",
            ),
        ]
        self.patch(type(self), "calls_json", {"calls": calls, "next_page_uri": None})
        self.env["integration.twilio.call"]._cron_sync_trunk_calls()

        records = self.env["integration.twilio.call"].search(
            [("company_id", "=", self.company_admin.id)], order="twilio_sid"
        )
        self.assertEqual(
            [(r.twilio_sid, r.report_state, r.phone_call_id) for r in records],
            [
                ("CA1", "matched", self.reported),
                ("CA2", "unreported", self.env["phone.call"]),
                ("CA3", "not_expected", self.env["phone.call"]),
                ("CA4", "pending", self.env["phone.call"]),
            ],
        )
        self.assertRecordValues(
            records[:2],
            [
                {
                    "direction": "incoming",
                    "phone_number": "+527225550101",
                    "line_number": DID,
                },
                {
                    "direction": "outgoing",
                    "phone_number": "+527225550202",
                    "line_number": DID,
                },
            ],
        )
        self.assertEqual((records[0].amount_price, records[0].duration), (0.013, 42))
        self.assertEqual(records[0].start_date, datetime(2026, 10, 6, 9, 0, 0))

        late = self.env["phone.call"].create(
            {
                "channel": "pbx",
                "direction": "incoming",
                "state": "terminated",
                "phone_number": "+52 722 555 0404",
                "start_date": datetime(2026, 10, 6, 12, 58, 30),
                "company_id": self.company_admin.id,
            }
        )
        self.env["integration.twilio.call"]._cron_sync_trunk_calls()
        records = self.env["integration.twilio.call"].search(
            [("company_id", "=", self.company_admin.id)], order="twilio_sid"
        )
        self.assertEqual(len(records), 4)
        self.assertEqual(records[3].phone_call_id, late)

    @freeze_time("2026-10-06 14:00:00")
    def test_withheld_callers_and_calls_the_phone_system_never_took(self):
        withheld_report = self.env["phone.call"].create(
            {
                "channel": "pbx",
                "direction": "incoming",
                "state": "terminated",
                "phone_number": False,
                "start_date": datetime(2026, 10, 6, 8, 0, 20),
                "company_id": self.company_admin.id,
            }
        )
        calls = [
            _call(
                "CA7",
                "trunking-originating",
                "anonymous",
                DID,
                "Tue, 06 Oct 2026 08:00:00 +0000",
                "Tue, 06 Oct 2026 08:02:00 +0000",
            ),
            _call(
                "CA8",
                "trunking-originating",
                "+266696687",
                DID,
                "Tue, 06 Oct 2026 08:30:00 +0000",
                "Tue, 06 Oct 2026 08:31:00 +0000",
            ),
            _call(
                "CA9",
                "trunking-originating",
                "+527225550909",
                DID,
                "Tue, 06 Oct 2026 09:30:00 +0000",
                "Tue, 06 Oct 2026 09:30:30 +0000",
                status="no-answer",
            ),
        ]
        self.patch(type(self), "calls_json", {"calls": calls, "next_page_uri": None})
        self.env["integration.twilio.call"]._cron_sync_trunk_calls()

        records = self.env["integration.twilio.call"].search(
            [("twilio_sid", "in", ["CA7", "CA8", "CA9"])], order="twilio_sid"
        )
        self.assertEqual(
            [
                (r.twilio_sid, r.phone_number, r.report_state, r.phone_call_id)
                for r in records
            ],
            [
                ("CA7", False, "matched", withheld_report),
                ("CA8", False, "unreported", self.env["phone.call"]),
                ("CA9", "+527225550909", "unreported", self.env["phone.call"]),
            ],
        )
