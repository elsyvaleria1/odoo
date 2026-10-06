from unittest.mock import patch

from odoo import Command
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestDeviceCallIngest(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="Mobile Call Config")
        cls.device = cls._create_device_device(
            config=cls.config, name="Phone", identifier="PHONE-CALLS"
        )
        cls.calls = cls.env["phone.call"]

    def _calls(self, count=5):
        return [
            {
                "number": f"55512300{i:02d}",
                "direction": "incoming",
                "duration": 30,
                "timestamp": 1754740800000 + i * 60000,
            }
            for i in range(count)
        ]

    def test_resending_a_call_batch_stores_nothing_new(self):
        calls = self._calls(20)
        self.assertEqual(
            len(self.calls.ingest_from_device(self.device, calls).created), 20
        )
        self.assertFalse(self.calls.ingest_from_device(self.device, calls).created)
        self.assertEqual(
            self.calls.search_count([("device_id", "=", self.device.id)]), 20
        )

    def test_a_resend_reads_the_stored_calls_at_its_stamps_not_the_span(self):
        # A backlog flushed after days offline spans days in one batch, and the
        # dedup read every stored call between its first and last stamp to
        # compare against a hundred.
        stored = self._calls(300)
        self.calls.ingest_from_device(self.device, stored)
        self.env.flush_all()
        read = []
        original = type(self.calls).search_read

        def counting(records, *args, **kwargs):
            rows = original(records, *args, **kwargs)
            read.append(len(rows))
            return rows

        with patch.object(type(self.calls), "search_read", counting):
            ingest = self.calls.ingest_from_device(self.device, [stored[0], stored[-1]])

        self.assertEqual(ingest.duplicates, 2)
        self.assertLessEqual(sum(read), 2, f"read {sum(read)} stored calls to dedup 2")

    def test_a_batch_is_created_in_one_pass(self):
        calls = self._calls(30)
        self.env.flush_all()
        before = self.env.cr.sql_statement_count
        self.calls.ingest_from_device(self.device, calls)
        self.env.flush_all()
        queries = self.env.cr.sql_statement_count - before
        self.assertLess(
            queries,
            len(calls),
            f"storing {len(calls)} calls took {queries} queries — "
            f"the per-record create loop or the per-record partner search is back",
        )

    def test_partner_is_matched_on_the_last_ten_digits(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Matched Contact",
                "phone_ids": [
                    Command.create({"number": "+52 (555) 123-0003", "type": "landline"})
                ],
            }
        )
        created = self.calls.ingest_from_device(self.device, self._calls(5)).created
        matched = created.filtered(lambda call: call.phone_number == "5551230003")
        self.assertEqual(matched.partner_id, partner)

    def test_unknown_directions_are_skipped(self):
        created = self.calls.ingest_from_device(
            self.device,
            [
                {"number": "5551230000", "direction": "incoming"},
                {"number": "5551230001", "direction": "teleported"},
                {"number": "", "direction": "incoming"},
            ],
        ).created
        self.assertEqual(len(created), 1)

    def test_an_out_of_range_timestamp_does_not_poison_the_batch(self):
        created = self.calls.ingest_from_device(
            self.device,
            [
                {
                    "number": "5551230000",
                    "direction": "incoming",
                    "timestamp": 1754740800000,
                },
                {
                    "number": "5551230001",
                    "direction": "incoming",
                    "timestamp": "99999999999999999999",
                },
            ],
        ).created
        self.assertEqual(len(created), 2)

    def test_a_device_without_company_files_its_calls_in_its_user_company(self):
        company = self.env["res.company"].create({"name": "Xiuman"})
        user = self.env["res.users"].create(
            {
                "name": "Rep",
                "login": "device_call_ingest_rep",
                "company_id": company.id,
                "company_ids": [Command.set(company.ids)],
            }
        )
        self.device.write({"company_id": False, "user_id": user.id})
        created = self.calls.ingest_from_device(self.device, self._calls(1)).created
        self.assertEqual(created.company_id, company)

    def test_another_company_does_not_see_the_calls(self):
        company = self.env["res.company"].create({"name": "Otra"})
        outsider = self.env["res.users"].create(
            {
                "name": "Outsider",
                "login": "device_call_outsider",
                "company_id": company.id,
                "company_ids": [Command.set(company.ids)],
                "group_ids": [
                    Command.link(self.env.ref("device.group_device_user").id)
                ],
            }
        )
        created = self.calls.ingest_from_device(self.device, self._calls(1)).created
        self.assertFalse(
            self.calls.with_user(outsider).search([("id", "in", created.ids)])
        )

    def test_a_phone_system_call_belongs_to_the_company_whose_line_it_reached(self):
        lmmr = self.env["res.company"].create(
            {
                "name": "LMMR",
                "phone_ids": [Command.create({"number": "+52 (722) 555-0101"})],
            }
        )
        xiuman = self.env["res.company"].create(
            {
                "name": "Xiuman",
                "phone_ids": [Command.create({"number": "+52 722 555 0202"})],
            }
        )
        pbx = self._create_device_device(
            config=self.config,
            name="Phone system",
            identifier="PBX-01",
            device_category_id=self.env.ref("device_phone_call.device_category_pbx").id,
        )
        created = self.calls.ingest_from_device(
            pbx,
            [
                {"number": "5551230001", "direction": "incoming", "line": "7225550202"},
                {
                    "number": "5551230002",
                    "direction": "incoming",
                    "line": "+527225550101",
                },
                {"number": "5551230003", "direction": "incoming"},
            ],
        ).created.sorted("phone_number")
        self.assertEqual(created.mapped("company_id")[:2], xiuman | lmmr)
        self.assertEqual(created[2].company_id, pbx._phone_call_company())
        self.assertEqual(set(created.mapped("channel")), {"pbx"})
