from datetime import UTC, datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import Form, common


class TestMrpMaintenance(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Relative models
        cls.ResUsers = cls.env["res.users"]
        cls.asset = cls.env["resource.resource"]
        cls.workcenter = cls.env["mrp.workcenter"]

        # User references
        cls.main_company = cls.env.ref("base.main_company")
        calendar = cls.env["resource.calendar"].create(
            {
                "name": "Main Company Calendar",
                "company_id": cls.main_company.id,
                "tz": "UTC",
            }
        )
        cls.main_company.resource_calendar_id = calendar
        cls.technician_user_id = cls.env.ref("base.user_root")
        cls.maintenance_team_id = cls.env.ref("maintenance.equipment_team_maintenance")
        cls.kind_id = cls.env["resource.kind"].create(
            {
                "name": "Monitors - Test",
                "code": "monitor_test",
                "technician_user_id": cls.env.ref("base.user_admin").id,
            }
        )

        # Create user
        cls.user = cls.ResUsers.create(
            {
                "name": "employee",
                "company_id": cls.main_company.id,
                "login": "employee",
                "email": "employee@yourcompany.example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

        # Create user with extra rights
        cls.manager = cls.ResUsers.create(
            {
                "name": "Equipment Manager",
                "company_id": cls.main_company.id,
                "login": "manager",
                "email": "eqmanager@yourcompany.example.com",
                "group_ids": [
                    (6, 0, [cls.env.ref("maintenance.group_equipment_manager").id])
                ],
            }
        )

        # Create workcenter
        cls.workcenter_id = cls.env["mrp.workcenter"].create(
            {
                "name": "Workcenter 01",
            }
        )

    # Create method for create a maintenance order
    def _create_order(self, name, date_confirmed, asset, maintenance_type):
        values = {
            "name": name,
            "date_confirmed": date_confirmed,
            "user_id": self.user.id,
            "resource_ids": asset.ids,
            "maintenance_type": maintenance_type,
            "state": "confirmed",
            "maintenance_team_id": self.maintenance_team_id.id,
        }
        return self.env["maintenance.order"].create(values)

    def _create_workcenter_plan(self, **values):
        return self.env["maintenance.plan"].create(
            {
                "user_id": self.technician_user_id.id,
                "resource_ids": [(6, 0, self.workcenter_id.resource_id.ids)],
                "maintenance_team_id": self.maintenance_team_id.id,
                "block_resource": True,
                "repeat_anchor": "fixed",
                **values,
            }
        )

    def _plan_work_order(self, date_start):
        product = self.env["product.product"].create({"name": "Held Product"})
        bom = self.env["mrp.bom"].create(
            {"product_tmpl_id": product.product_tmpl_id.id}
        )
        self.env["mrp.routing.workcenter"].create(
            {
                "name": "Held Operation",
                "workcenter_id": self.workcenter_id.id,
                "bom_id": bom.id,
                "time_cycle_manual": 60,
            }
        )
        production = self.env["mrp.production"].create(
            {"bom_id": bom.id, "date_start": date_start}
        )
        production.action_confirm()
        production.button_plan()
        return production.workorder_ids[:1]

    def _create_workcenter_order(
        self, name, date_confirmed, workcenter_id, maintenance_type, **kwargs
    ):
        """Create and return a workcenter maintenance order"""
        values = {
            "name": name,
            "date_confirmed": date_confirmed,
            "user_id": self.technician_user_id.id,
            "resource_ids": [(6, 0, workcenter_id.resource_id.ids)],
            "maintenance_type": maintenance_type,
            "maintenance_team_id": self.maintenance_team_id.id,
            "state": "confirmed",
            **kwargs,
        }
        return self.env["maintenance.order"].create(values)

    def test_00_mrp_maintenance(self):
        """In order to check Next preventive maintenance date"""
        """
        ex:  asset          =     Acer Laptop
             date_in_service = 25-04-2018
             period         = 5

            preventive maintenance date = effective date + period
                30-04-2018              = 25-04-2018     + 5 days

            create maintenance order
                date_confirmed  =  effective date + period
                30-04-2018    = 25-04-2018      + 5 days

            close maintenance order and calculate preventive maintenance date
            date_done = 05-05-2018

            preventive maintenance date = date_done + period
                10-05-2018              = 05-05-2018 + 5day
        """

        asset_form = Form(self.asset, view="base.resource_asset_view_form")
        asset_form.name = "Acer Laptop"
        asset_form.maintenance_team_id = self.maintenance_team_id
        asset_form.kind_id = self.kind_id
        asset_form.technician_user_id = self.technician_user_id
        asset_form.expected_mtbf = 2
        asset_form.date_in_service = (
            datetime.now().date() + timedelta(days=5)
        ).strftime("%Y-%m-%d")
        asset_01 = asset_form.save()

        # Create a maintenance order
        maintenance_order_01 = self._create_order(
            name="Display not working",
            date_confirmed=datetime.now().date() + timedelta(days=10),
            asset=asset_01,
            maintenance_type="preventive",
        )

        # check that maintenance_order is created or not
        self.assertTrue(maintenance_order_01, "Maintenance Order not created")

        # check maintenance order date.
        self.assertEqual(
            maintenance_order_01.date_confirmed.date(),
            datetime.now().date() + timedelta(days=10),
            "maintenance date_confirmed is wrong",
        )

        # Updating maintenance to done and its close date
        maintenance_order_01.write({"state": "done"})
        maintenance_order_01.date_done = datetime.now().date() + timedelta(days=15)

        # Create another order which would still be open
        maintenance_order_02 = self._create_order(
            name="Display not working",
            date_confirmed=datetime.now().date() + timedelta(days=25),
            asset=asset_01,
            maintenance_type="preventive",
        )

        # check that maintenance_order is created or not
        self.assertTrue(maintenance_order_02, "Maintenance Order not created")

    def test_01_mrp_maintenance(self):
        """In order to check MTBF,MTTR,estimated next failure and estimated
        latest failure of an asset's orders.
        """

        asset_form = Form(self.asset, view="base.resource_asset_view_form")
        asset_form.name = "Acer Laptop"
        asset_form.maintenance_team_id = self.maintenance_team_id
        asset_form.kind_id = self.kind_id
        asset_form.technician_user_id = self.technician_user_id
        asset_form.expected_mtbf = 2
        asset_form.date_in_service = "2017-04-13"
        asset_01 = asset_form.save()

        # Create maintenance orders

        # Maintenance Order          Order Date
        #  1)                          2017-05-03
        #  2)                          2017-05-23
        #  3)                          2017-06-11

        maintenance_order_01 = self._create_order(
            name="Some keys are not working",
            date_confirmed=datetime(2017, 5, 3).date(),
            asset=asset_01,
            maintenance_type="corrective",
        )
        maintenance_order_02 = self._create_order(
            name="Touchpad not working",
            date_confirmed=datetime(2017, 5, 23).date(),
            asset=asset_01,
            maintenance_type="corrective",
        )
        maintenance_order_03 = self._create_order(
            name="Battery drains fast",
            date_confirmed=datetime(2017, 6, 11).date(),
            asset=asset_01,
            maintenance_type="corrective",
        )

        # check that maintenance_order is created or not
        self.assertTrue(maintenance_order_01, "Maintenance Order not created")
        self.assertTrue(maintenance_order_02, "Maintenance Order not created")
        self.assertTrue(maintenance_order_03, "Maintenance Order not created")

        # Order  Order Date  Close Date  diff_days
        #  1)      2017-05-03    2017-05-13     10
        #  2)      2017-05-23    2017-05-28      5
        #  3)      2017-06-11    2017-06-11      0

        # MTTR = Day used to handle maintenance order / No of order
        #   5  =            (10+5+0)15                  /    3

        #  MTBF = Gap in days of between effective date and last order / No of order
        #   19  = (2017-06-11 - 2017-04-13) 59                          /       3

        # estimated next failure = latest failure date + MTBF
        # 2017-06-30 00:00:00    = 2017-06-11           + 19

        # maintenance_order_01 write state and date_done.
        maintenance_order_01.write({"state": "done"})
        maintenance_order_01.date_done = datetime(2017, 5, 3).date() + timedelta(
            days=10
        )
        self.assertEqual(
            maintenance_order_01.date_done,
            datetime(2017, 5, 13).date(),
            "Wrong close date on maintenance order.",
        )

        # maintenance_order_02 write state and date_done.
        maintenance_order_02.write({"state": "done"})
        maintenance_order_02.date_done = datetime(2017, 5, 23).date() + timedelta(
            days=5
        )
        self.assertEqual(
            maintenance_order_02.date_done,
            datetime(2017, 5, 28).date(),
            "Wrong close date on maintenance order.",
        )

        # maintenance_order_03 write state and date_done.
        maintenance_order_03.write({"state": "done"})
        maintenance_order_03.date_done = maintenance_order_03.date_confirmed.date()
        self.assertEqual(
            maintenance_order_03.date_done,
            datetime(2017, 6, 11).date(),
            "Wrong close date on maintenance order.",
        )

        # Check MTTR = Day used to handle maintenance order / No of order (15 / 3)
        self.assertEqual(
            asset_01.mttr,
            5,
            "Maintenance Equipment MTTR(Mean Time To Repair) should be 5 days",
        )

        # Check MTBF = Gap in days of between effective date and last order / No of order
        self.assertEqual(
            asset_01.mtbf,
            19,
            "Maintenance Equipment MTBF(Mean Time Between Failure) should be 19 days",
        )

        # Check calculation of latest failure date (should be 11-06-2017)
        date_last_failure = asset_01.date_last_failure
        self.assertEqual(
            maintenance_order_03.date_confirmed.date(),
            datetime(2017, 6, 11).date(),
            "Wrong date_confirmed on maintenance order.",
        )
        self.assertEqual(
            date_last_failure,
            maintenance_order_03.date_confirmed.date(),
            "Wrong date_last_failure on maintenance order.",
        )

        # Check calculation of estimated next failure (should be 30-06-2017)
        # Step-1: latest failure date + MTBF
        date_next_failure = asset_01.date_last_failure + timedelta(days=asset_01.mtbf)
        self.assertEqual(
            date_next_failure,
            datetime(2017, 6, 30).date(),
            "Wrong date_last_failure on maintenance order.",
        )

    def test_01_mrp_maintenance_workcenter(
        self,
    ):  # adapted from test_01_mrp_maintenance (working on an asset)
        with self.debug_mode():
            # Create a new workcenter
            workcenter_form = Form(
                self.workcenter,
                view="mrp_maintenance.mrp_workcenter_view_form_inherit_maintenance",
            )
            workcenter_form.name = "WorkCenter"
            workcenter_form.maintenance_team_id = self.maintenance_team_id
            workcenter_form.technician_user_id = self.technician_user_id
            workcenter_form.expected_mtbf = 2
            workcenter_form.date_in_service = "2017-04-13"
            workcenter = workcenter_form.save()

        # Check that workcenter is createdworkcenter
        self.assertTrue(workcenter, "Equipment not created")

        # Create maintenance orders

        # Maintenance Order          Order Date
        #  1)                          2017-05-03
        #  2)                          2017-05-23
        #  3)                          2017-06-11

        maintenance_order_1 = self._create_workcenter_order(
            name="Some keys are not working",
            date_confirmed=datetime(2017, 5, 3).date(),
            workcenter_id=workcenter,
            maintenance_type="corrective",
        )
        maintenance_order_2 = self._create_workcenter_order(
            name="Touchpad not working",
            date_confirmed=datetime(2017, 5, 23).date(),
            workcenter_id=workcenter,
            maintenance_type="corrective",
        )
        maintenance_order_3 = self._create_workcenter_order(
            name="Battery drains fast",
            date_confirmed=datetime(2017, 6, 11).date(),
            workcenter_id=workcenter,
            maintenance_type="corrective",
        )

        # check that maintenance_orders are created or not
        self.assertTrue(maintenance_order_1, "Maintenance Order not created")
        self.assertTrue(maintenance_order_2, "Maintenance Order not created")
        self.assertTrue(maintenance_order_3, "Maintenance Order not created")

        # Order  Order Date  Close Date  diff_days
        #  1)      2017-05-03    2017-05-13     10
        #  2)      2017-05-23    2017-05-28      5
        #  3)      2017-06-11    2017-06-11      0

        # MTTR = Day used to handle maintenance order / No of order
        #   5  =            (10+5+0)15                  /    3

        #  MTBF = Gap in days of between effective date and last order / No of order
        #   19  = (2017-06-11 - 2017-04-13) 59                          /       3

        # estimated next failure = latest failure date + MTBF
        # 2017-06-30 00:00:00    = 2017-06-11           + 19

        # maintenance_order_1 write state and date_done.
        maintenance_order_1.write({"state": "done"})
        maintenance_order_1.date_done = datetime(2017, 5, 3).date() + timedelta(days=10)
        self.assertEqual(
            maintenance_order_1.date_done,
            datetime(2017, 5, 13).date(),
            "Wrong close date on maintenance order.",
        )

        # maintenance_order_2 write state and date_done.
        maintenance_order_2.write({"state": "done"})
        maintenance_order_2.date_done = datetime(2017, 5, 23).date() + timedelta(days=5)
        self.assertEqual(
            maintenance_order_2.date_done,
            datetime(2017, 5, 28).date(),
            "Wrong close date on maintenance order.",
        )

        # maintenance_order_3 write state and date_done.
        maintenance_order_3.write({"state": "done"})
        maintenance_order_3.date_done = maintenance_order_3.date_confirmed.date()
        self.assertEqual(
            maintenance_order_3.date_done,
            datetime(2017, 6, 11).date(),
            "Wrong close date on maintenance order.",
        )

        # Check MTTR = Day used to handle maintenance order / No of order (15 / 3)
        self.assertEqual(
            workcenter.mttr,
            5,
            "Maintenance Equipment MTTR(Mean Time To Repair) should be 5 days",
        )

        # Check MTBF = Gap in days of between effective date and last order / No of order
        self.assertEqual(
            workcenter.mtbf,
            19,
            "Maintenance Equipment MTBF(Mean Time Between Failure) should be 19 days",
        )

        # Check calculation of latest failure date (should be 11-06-2017)
        date_last_failure = workcenter.date_last_failure
        self.assertEqual(
            maintenance_order_3.date_confirmed.date(),
            datetime(2017, 6, 11).date(),
            "Wrong date_confirmed on maintenance order.",
        )
        self.assertEqual(
            date_last_failure,
            maintenance_order_3.date_confirmed.date(),
            "Wrong date_last_failure on maintenance order.",
        )

        # Check calculation of estimated next failure (should be 30-06-2017)
        # Step-1: latest failure date + MTBF
        date_next_failure = workcenter.date_last_failure + timedelta(
            days=workcenter.mtbf
        )
        self.assertEqual(
            date_next_failure,
            datetime(2017, 6, 30).date(),
            "Wrong date_last_failure on maintenance order.",
        )

    def test_workcenter_unavailability(self):
        self.env.user.group_ids += self.env.ref("mrp.group_mrp_routings")
        asset_form = Form(self.asset, view="base.resource_asset_view_form")
        asset_form.name = "Screwdriver"
        asset_form.maintenance_team_id = self.maintenance_team_id
        asset_form.kind_id = self.kind_id
        asset_form.technician_user_id = self.technician_user_id
        asset_form.expected_mtbf = 2
        asset_form.date_in_service = datetime.now().date() + timedelta(days=5)
        screwdriver = asset_form.save()

        maintenance_order_01 = self._create_order(
            name="Does not turn",
            date_confirmed=datetime(2017, 5, 3).date(),
            asset=screwdriver,
            maintenance_type="corrective",
        )
        maintenance_order_01.write(
            {
                "date_scheduled_start": datetime(2017, 5, 3, 8, microsecond=500),
                "date_scheduled_end": datetime(2017, 5, 3, 10, microsecond=500),
                "resource_ids": [(6, 0, self.workcenter_id.resource_id.ids)],
                "block_resource": True,
            }
        )
        start_datetime = datetime(2017, 5, 3, 7)
        intervals_by_workcenter = self.workcenter_id._get_unavailability_intervals(
            start_datetime, start_datetime + timedelta(hours=4)
        )
        intervals = [
            (
                start.astimezone(UTC).replace(tzinfo=None),
                stop.astimezone(UTC).replace(tzinfo=None),
            )
            for start, stop in intervals_by_workcenter[self.workcenter_id.id]
        ]
        self.assertIn((datetime(2017, 5, 3, 7), datetime(2017, 5, 3, 8)), intervals)
        self.assertTrue(
            any(
                start <= maintenance_order_01.date_scheduled_start
                and stop >= maintenance_order_01.date_scheduled_end
                for start, stop in intervals
            ),
            intervals,
        )

    def test_maintenance_team_id_compute(self):
        """Ensure that the maintenance order does not update its maintenance_team_id
        when changing to a workcenter that does not have a maintenance_team_id.
        """

        workcenter_without_team = self.env["mrp.workcenter"].create(
            {
                "name": "Workcenter No Team",
            }
        )

        order = self._create_workcenter_order(
            name="Unexpected shutdowns",
            date_confirmed=datetime(2018, 4, 5).date(),
            workcenter_id=workcenter_without_team,
            maintenance_type="corrective",
        )
        order.write({"resource_ids": [(6, 0, self.workcenter_id.resource_id.ids)]})

        self.assertEqual(
            order.maintenance_team_id.id,
            self.maintenance_team_id.id,
            "Maintenance team should remain unchanged when workcenter has no maintenance_team_id.",
        )

    @freeze_time("2025-05-21 11:00:00")
    def test_maintenance_block_workcenter(self):
        """
        Validate that maintenance orders can create resource leaves as long as they do not
        conflict with existing workorder intervals, regardless of working hours (unlike workorder scheduling).
        Also verifies that recurring maintenance orders are properly rescheduled after any overlapping
        manufacturing orders have been completed.
        """
        product = self.env["product.product"].create({"name": "Test Product"})
        bom = self.env["mrp.bom"].create(
            {"product_tmpl_id": product.product_tmpl_id.id}
        )
        self.env["mrp.routing.workcenter"].create(
            {
                "name": "Test Operation",
                "workcenter_id": self.workcenter_id.id,
                "bom_id": bom.id,
            }
        )
        mo = self.env["mrp.production"].create(
            {"bom_id": bom.id, "date_start": datetime.now()}
        )  # 11:00 AM - 12:00 PM
        mo.action_confirm()
        mo.button_plan()
        wo_finished_date = mo.workorder_ids[0].date_end

        # A daily plan whose first occurrence is one day before today (past), from 07:00 to 18:00.
        date_scheduled_start = datetime(2025, 5, 20, 7, 0, 0)
        mr = self._create_workcenter_plan(
            name="Preventive Maintenance (Block Workcenter)",
            date_first_occurrence=date_scheduled_start,
            duration=11,
            repeat_unit="day",
            repeat_interval=1,
            repeat_type="until",
            repeat_until=date_scheduled_start + timedelta(weeks=1),
            book_ahead_count=2,
        ).order_ids
        # Ensure the MR is allowed to span non-working hours (e.g., 07:00-08:00, 13:00-14:00)
        # and that booking in the past is permitted without blocking the user.
        reservations = mr.reservation_ids.sorted("date_start")
        self.assertEqual(len(reservations), 3)  # 1 for today + 2 recurring slots
        self.assertRecordValues(
            reservations,
            [
                {
                    "date_start": datetime(2025, 5, 20, 7, 0, 0),
                    "date_end": datetime(2025, 5, 20, 18, 0, 0),
                    "enforcement_mode": "hard",
                },
                {
                    "date_start": wo_finished_date,
                    "date_end": wo_finished_date + timedelta(hours=11),
                    "enforcement_mode": "hard",
                },
                {
                    "date_start": datetime(2025, 5, 22, 7, 0, 0),
                    "date_end": datetime(2025, 5, 22, 18, 0, 0),
                    "enforcement_mode": "hard",
                },
            ],
        )
        self.assertEqual(reservations.resource_id, self.workcenter_id.resource_id)
        self.assertFalse(
            self.env["resource.schedule.exception"].search(
                [("resource_id", "=", self.workcenter_id.resource_id.id)]
            )
        )

        with freeze_time("2025-05-20 20:00:00"):
            mr.write({"state": "done"})
        next_mr = mr.plan_id.order_ids - mr

        # Confirm that the next MR is scheduled after the MO has finished
        self.assertEqual(
            next_mr.date_scheduled_start,
            wo_finished_date,
            "Next preventive maintenance should be scheduled after the MO's end.",
        )

    @freeze_time("2027-01-01 08:00:00")
    def test_the_booked_recurrences_follow_the_series_dates(self):
        self.env = self.env(context=dict(self.env.context, tz="UTC"))
        date_scheduled_start = datetime(2027, 1, 31, 7, 0, 0)
        mr = self._create_workcenter_plan(
            name="Month-end maintenance",
            tz="UTC",
            date_first_occurrence=date_scheduled_start,
            duration=1,
            repeat_unit="month",
            repeat_interval=1,
            book_ahead_count=2,
        ).order_ids
        self.assertEqual(
            mr.reservation_ids.sorted("date_start").mapped("date_start"),
            [
                datetime(2027, 1, 31, 7, 0, 0),
                datetime(2027, 2, 28, 7, 0, 0),
                datetime(2027, 3, 31, 7, 0, 0),
            ],
        )

    @freeze_time("2025-05-21 11:00:00")
    def test_maintenance_reservation_is_unavailable_time_for_the_planner(self):
        """A blocking order is unavailable time: a work order planned into its
        window lands after it, and the work centre reports the window as
        unavailable to the Gantt."""
        date_scheduled_start = datetime(2025, 5, 22, 9, 0, 0)
        mr = self._create_workcenter_order(
            name="Blocking maintenance",
            date_confirmed=date_scheduled_start,
            workcenter_id=self.workcenter_id,
            maintenance_type="corrective",
            date_scheduled_start=date_scheduled_start,
            date_scheduled_end=datetime(2025, 5, 22, 12, 0, 0),
            block_resource=True,
        )
        self.assertEqual(len(mr.reservation_ids), 1)

        product = self.env["product.product"].create({"name": "Planned Product"})
        bom = self.env["mrp.bom"].create(
            {"product_tmpl_id": product.product_tmpl_id.id}
        )
        self.env["mrp.routing.workcenter"].create(
            {
                "name": "Planned Operation",
                "workcenter_id": self.workcenter_id.id,
                "bom_id": bom.id,
                "time_cycle_manual": 60,
            }
        )
        mo = self.env["mrp.production"].create(
            {"bom_id": bom.id, "date_start": date_scheduled_start}
        )
        mo.action_confirm()
        mo.button_plan()
        self.assertGreaterEqual(
            mo.workorder_ids[0].date_start, datetime(2025, 5, 22, 12, 0, 0)
        )

        unavailable = self.workcenter_id._get_unavailability_intervals(
            datetime(2025, 5, 22, 0, 0, 0),
            datetime(2025, 5, 23, 0, 0, 0),
        )[self.workcenter_id.id]
        self.assertTrue(
            any(
                start.astimezone(UTC).replace(tzinfo=None) <= date_scheduled_start
                and stop.astimezone(UTC).replace(tzinfo=None)
                >= datetime(2025, 5, 22, 12, 0, 0)
                for start, stop in unavailable
            ),
            unavailable,
        )

        # Repairing keeps the booking as the record of when the machine was
        # down, exactly as a finished work order keeps its own.
        mr.write({"state": "done"})
        self.assertEqual(len(mr.reservation_ids), 1)

    def test_cancelling_and_unlinking_an_order_releases_the_work_centre(self):
        date_scheduled_start = datetime(2025, 6, 2, 9, 0, 0)
        mr = self._create_workcenter_order(
            name="Short-lived",
            date_confirmed=date_scheduled_start,
            workcenter_id=self.workcenter_id,
            maintenance_type="corrective",
            date_scheduled_start=date_scheduled_start,
            block_resource=True,
        )
        resource = self.workcenter_id.resource_id
        self.assertTrue(
            self.env["resource.reservation"].search([("resource_id", "=", resource.id)])
        )
        mr.action_cancel()
        mr.unlink()
        self.assertFalse(
            self.env["resource.reservation"].search([("resource_id", "=", resource.id)])
        )

    def test_a_code_path_create_takes_the_work_centre_team(self):
        team = self.env["team.team"].create(
            {"use_maintenance": True, "name": "Work Centre Team"}
        )
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Press Line", "maintenance_team_id": team.id}
        )
        order = self.env["maintenance.order"].create(
            {
                "name": "Jam",
                "resource_ids": [(6, 0, workcenter.resource_id.ids)],
            }
        )
        self.assertEqual(order.maintenance_team_id, team)

    def test_the_machine_of_a_work_centre_shares_its_maintenance(self):
        workcenter_team = self.env["team.team"].create(
            {"use_maintenance": True, "name": "Work Centre Team"}
        )
        press = self.asset.create(
            {"name": "Hydraulic Press", "kind_id": self.kind_id.id}
        )
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Press Line", "asset_id": press.id}
        )
        workcenter.maintenance_team_id = workcenter_team
        self.assertEqual(press.maintenance_team_id, workcenter_team)
        order = self.env["maintenance.order"].create(
            {"name": "Leak", "resource_ids": press.ids}
        )
        self.assertEqual(order.maintenance_team_id, workcenter_team)
        self.assertEqual(workcenter.maintenance_count, 1)

    def test_a_tool_of_a_work_centre_is_a_component_of_its_machine(self):
        press = self.asset.create({"name": "Press", "kind_id": self.kind_id.id})
        workcenter = self.env["mrp.workcenter"].create(
            {"name": "Press Line", "asset_id": press.id}
        )
        die = self.asset.create(
            {"name": "Die", "kind_id": self.kind_id.id, "parent_id": press.id}
        )
        self.assertEqual(workcenter.asset_component_ids, die)

    @freeze_time("2025-05-21 11:00:00")
    def test_an_order_typed_into_a_held_slot_is_refused_even_under_a_plan(self):
        work_order = self._plan_work_order(datetime(2025, 5, 22, 9, 0, 0))
        plan = self._create_workcenter_plan(
            name="Weekly check",
            date_first_occurrence=datetime(2025, 6, 2, 7, 0, 0),
            repeat_unit="week",
            repeat_interval=1,
        )
        with self.assertRaises(UserError):
            self._create_workcenter_order(
                name="Typed in",
                date_confirmed=work_order.date_start,
                workcenter_id=self.workcenter_id,
                maintenance_type="preventive",
                date_scheduled_start=work_order.date_start,
                block_resource=True,
                plan_id=plan.id,
            )

    @freeze_time("2025-05-21 11:00:00")
    def test_only_the_pushed_order_is_told_its_schedule_moved(self):
        work_order = self._plan_work_order(datetime(2025, 5, 22, 9, 0, 0))
        held, free = self.env["maintenance.order"].concat(
            *(
                self._create_workcenter_order(
                    name=name,
                    date_confirmed=date,
                    workcenter_id=self.workcenter_id,
                    maintenance_type="corrective",
                    date_scheduled_start=date,
                    block_resource=False,
                )
                for name, date in (
                    ("Held", work_order.date_start),
                    ("Free", datetime(2025, 5, 26, 7, 0, 0)),
                )
            )
        )
        (held | free).with_context(skip_maintenance_reservations=True).write(
            {"block_resource": True}
        )
        (held | free)._recreate_reservations(refuse_taken_window=False)
        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "maintenance.order"),
                ("res_id", "in", (held | free).ids),
                (
                    "activity_type_id",
                    "=",
                    self.env.ref("mail.mail_activity_data_warning").id,
                ),
            ]
        )
        self.assertEqual(activities.mapped("res_id"), held.ids)

    @freeze_time("2027-01-01 08:00:00")
    def test_a_plan_change_reaches_its_open_order(self):
        plan = self._create_workcenter_plan(
            name="Weekly check",
            date_first_occurrence=datetime(2027, 1, 4, 7, 0, 0),
            repeat_unit="week",
            repeat_interval=1,
        )
        order = plan.order_ids
        press = self.env["mrp.workcenter"].create({"name": "Press Line"})
        plan.resource_ids = press.resource_id
        self.assertEqual(order.workcenter_ids, press)
        self.assertEqual(order.reservation_ids.resource_id, press.resource_id)
        plan.block_resource = False
        self.assertFalse(order.block_resource)
        self.assertFalse(order.reservation_ids)

    @freeze_time("2027-01-01 08:00:00")
    def test_an_archived_plan_books_no_windows_ahead(self):
        plan = self._create_workcenter_plan(
            name="Daily check",
            date_first_occurrence=datetime(2027, 1, 4, 7, 0, 0),
            repeat_unit="day",
            repeat_interval=1,
            book_ahead_count=2,
        )
        order = plan.order_ids
        self.assertEqual(len(order.reservation_ids), 3)
        plan.action_archive()
        self.assertEqual(
            order.reservation_ids.mapped("date_start"),
            [datetime(2027, 1, 4, 7, 0, 0)],
        )

    @freeze_time("2027-01-01 08:00:00")
    def test_cancelling_an_order_hands_its_windows_to_the_next_one(self):
        plan = self._create_workcenter_plan(
            name="Daily check",
            date_first_occurrence=datetime(2027, 1, 4, 7, 0, 0),
            repeat_unit="day",
            repeat_interval=1,
            book_ahead_count=2,
        )
        cancelled = plan.order_ids
        cancelled.action_cancel()
        successor = plan.order_ids - cancelled
        self.assertFalse(cancelled.reservation_ids)
        self.assertEqual(successor.date_scheduled_start, datetime(2027, 1, 5, 7, 0, 0))
        self.assertEqual(
            successor.reservation_ids.sorted("date_start").mapped("date_start"),
            [
                datetime(2027, 1, 5, 7, 0, 0),
                datetime(2027, 1, 6, 7, 0, 0),
                datetime(2027, 1, 7, 7, 0, 0),
            ],
        )
