from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestApprovalRequestAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.other_company = cls.env["res.company"].create({"name": "Second Yard"})

        template = cls.env["product.template"].create(
            {
                "name": "Fleet Pickup",
                "is_storable": True,
                "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
                "tracking": "serial",
            },
        )
        cls.product = template.product_variant_id

        cls.driver = new_test_user(
            cls.env,
            login="approval_stock_driver",
            groups="base.group_user",
        )
        cls.other_driver = new_test_user(
            cls.env,
            login="approval_stock_other_driver",
            groups="base.group_user",
        )
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Driver One", "user_id": cls.driver.id},
        )
        cls.other_employee = cls.env["hr.employee"].create(
            {"name": "Driver Two", "user_id": cls.other_driver.id},
        )

        cls.first_truck, cls.second_truck = cls.env["product.trace"].create(
            [
                {
                    "name": "TRUCK-A",
                    "product_id": cls.product.id,
                    "operator_id": cls.employee.id,
                    "company_id": cls.company.id,
                },
                {
                    "name": "TRUCK-B",
                    "product_id": cls.product.id,
                    "operator_id": cls.employee.id,
                    "company_id": cls.company.id,
                },
            ],
        )
        cls.other_truck = cls.env["product.trace"].create(
            {
                "name": "TRUCK-C",
                "product_id": cls.product.id,
                "operator_id": cls.other_employee.id,
                "company_id": cls.company.id,
            },
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Fleet Log",
                "approval_type": "asset_log",
                "approval_minimum": 1,
                "has_asset": "required",
                "has_odometer": "required",
                "has_date": "required",
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            },
        )

    def _request(self):
        return self.env["approval.request"].create(
            {
                "name": "Fleet Request",
                "category_id": self.category.id,
                "request_owner_id": self.driver.id,
                "company_id": self.company.id,
            },
        )

    def test_the_default_is_deterministic(self):
        self.assertEqual(
            self._request().asset_id,
            self.first_truck.asset_id,
            "with several assets on one operator the default has to be stable, "
            "not whatever the database returns first",
        )

    def test_a_chosen_asset_survives_an_owner_change(self):
        request = self._request()
        request.asset_id = self.second_truck.asset_id

        request.request_owner_id = self.other_driver

        self.assertEqual(
            request.asset_id,
            self.second_truck.asset_id,
            "the compute only fills an empty value; it must never overwrite "
            "what the user picked",
        )

    def test_the_default_still_fills_an_empty_asset(self):
        request = self._request()
        request.asset_id = False

        request.request_owner_id = self.other_driver

        self.assertEqual(request.asset_id, self.other_truck.asset_id)

    def test_the_default_does_not_cross_companies(self):
        self.driver.company_ids = [
            Command.set([self.company.id, self.other_company.id]),
        ]
        self.env.ref("base.user_admin").company_ids = [
            Command.link(self.other_company.id),
        ]

        request = self.env["approval.request"].create(
            {
                "name": "Cross Company Request",
                "category_id": self.category.id,
                "request_owner_id": self.driver.id,
                "company_id": self.other_company.id,
            },
        )

        self.assertEqual(
            self.first_truck.operator_id,
            self.employee,
            "the premise: this operator does have assets, just not in this company",
        )
        self.assertFalse(
            request.asset_id,
            "sudo() drops the company guard that would have filtered these out, "
            "so the domain has to carry the company term itself",
        )


@tagged("post_install", "-at_install")
class TestApprovalAssetLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = "America/Mexico_City"
        template = cls.env["product.template"].create(
            {
                "name": "Log Pickup",
                "is_storable": True,
                "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
                "tracking": "serial",
            },
        )
        cls.truck = cls.env["product.trace"].create(
            {
                "name": "LOG-TRUCK",
                "product_id": template.product_variant_id.id,
                "company_id": cls.env.company.id,
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Odometer Log",
                "approval_type": "asset_log",
                "approval_minimum": 1,
                "has_asset": "required",
                "has_odometer": "required",
                "has_date": "required",
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            },
        )

    def _approved_request(self, odometer=1000.0, date="2026-08-28 03:00:00"):
        request = self.env["approval.request"].create(
            {
                "name": "Odometer Request",
                "category_id": self.category.id,
                "request_owner_id": self.env.user.id,
                "asset_id": self.truck.asset_id.id,
                "odometer": odometer,
                "date": date,
            },
        )
        request.action_confirm()
        request.approver_ids[0].with_context(skip_wizard=True).action_approve()
        return request

    def test_a_second_press_opens_the_log_it_already_made(self):
        request = self._approved_request()

        first = request.action_create_asset_log()
        second = request.action_create_asset_log()

        self.assertEqual(len(request.asset_log_ids), 1)
        self.assertEqual(first["res_id"], second["res_id"])

    def test_the_log_books_the_requester_s_day_not_the_utc_one(self):
        request = self._approved_request()

        request.action_create_asset_log()

        self.assertEqual(
            str(request.asset_log_ids.date),
            "2026-08-27",
            "2026-08-28 03:00 UTC is 2026-08-27 21:00 in America/Mexico_City; "
            "truncating the UTC value books an evening approval on the next day",
        )

    def test_a_brand_new_asset_at_zero_can_be_logged(self):
        request = self._approved_request(odometer=0.0)

        request.action_create_asset_log()

        self.assertEqual(request.asset_log_ids.odometer, 0.0)

    def test_the_reading_keeps_its_fraction(self):
        request = self._approved_request(odometer=1234.5)

        self.assertEqual(
            request.odometer,
            1234.5,
            "the log stores a Float; an Integer here silently truncated it",
        )
