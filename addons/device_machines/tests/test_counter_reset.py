from datetime import UTC, datetime, timedelta

from odoo.tests import tagged

from .common import DeviceMachinesCommon


@tagged("post_install", "-at_install")
class TestCounterReset(DeviceMachinesCommon):
    def _ingest(self, device, payload_time, count):
        return device._ingest_counter_payload(
            {
                "m": {
                    "Maquina": device.identifier,
                    "Time Stamp": payload_time,
                    "Conteo": count,
                }
            }
        )

    def test_pieces_made_after_a_mid_hour_reset_are_still_counted(self):
        device = self.device
        self._ingest(device, "2026-08-16-10:00:00", 100)
        self._ingest(device, "2026-08-16-10:10:00", 150)
        self._ingest(device, "2026-08-16-10:20:00", 200)

        buckets = self.env["device.machine.bucket"].search(
            [("device_id", "=", device.id)]
        )
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets.delta, 100, "100 pieces before the reset")

        self._ingest(device, "2026-08-16-10:30:00", 0)
        self._ingest(device, "2026-08-16-10:40:00", 40)
        self._ingest(device, "2026-08-16-10:50:00", 90)

        buckets = self.env["device.machine.bucket"].search(
            [("device_id", "=", device.id)]
        )
        self.assertEqual(len(buckets), 1, "the bucket is keyed on the hour")
        self.assertTrue(buckets.reset_detected)
        self.assertEqual(
            buckets.delta,
            190,
            "100 before the reset plus 90 after it; pinning count_end to the "
            "pre-reset high recorded 100 and lost the rest",
        )
        self.assertEqual(
            buckets.count_end - buckets.count_start + buckets.count_carried,
            buckets.delta,
            "delta must stay reconstructible from the stored counters",
        )

    def test_the_hour_after_a_reset_opens_from_the_new_baseline(self):
        device = self.device
        self._ingest(device, "2026-08-16-10:00:00", 100)
        self._ingest(device, "2026-08-16-10:10:00", 150)
        self._ingest(device, "2026-08-16-10:20:00", 0)
        self._ingest(device, "2026-08-16-10:30:00", 20)
        self._ingest(device, "2026-08-16-11:10:00", 60)

        buckets = self.env["device.machine.bucket"].search(
            [("device_id", "=", device.id)], order="bucket_start"
        )
        self.assertEqual(len(buckets), 2)
        self.assertEqual(buckets[0].delta, 70, "50 before the reset, 20 after")
        self.assertEqual(buckets[1].delta, 40, "20 -> 60 in the next hour")

    def test_a_work_order_spanning_a_reset_keeps_its_count(self):
        workcenter = self.env["mrp.workcenter"].create({"name": "Reset WC"})
        device = self.device
        device.workcenter_id = workcenter.id
        run = self.env["device.machine.workorder"]
        moment = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)

        workorder = self.env["device.machine.workorder"].create(
            {
                "device_id": device.id,
                "workorder_id": self._any_workorder().id,
                "count_start": 100,
                "count_end": 100,
                "date_start": moment.replace(tzinfo=None),
            }
        )
        run._accumulate(
            device, workorder.workorder_id, 180, moment + timedelta(minutes=10)
        )
        self.assertEqual(workorder.bottles, 80)

        run._accumulate(
            device, workorder.workorder_id, 0, moment + timedelta(minutes=20)
        )
        run._accumulate(
            device, workorder.workorder_id, 35, moment + timedelta(minutes=30)
        )
        self.assertEqual(
            workorder.bottles,
            115,
            "80 before the reset plus 35 after; taking count_end verbatim made "
            "the whole run report zero",
        )

    def _any_workorder(self):
        workorder = self.env["mrp.workorder"].search([], limit=1)
        if workorder:
            return workorder
        production = self.env["mrp.production"].create(
            {"product_id": self.env["product.product"].create({"name": "PLC Item"}).id}
        )
        return self.env["mrp.workorder"].create(
            {
                "name": "Reset WO",
                "production_id": production.id,
                "workcenter_id": self.env["mrp.workcenter"].search([], limit=1).id,
                "product_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
