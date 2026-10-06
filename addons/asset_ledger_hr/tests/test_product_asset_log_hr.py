from datetime import date

from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import (
    create_test_product,
    create_test_template,
    ensure_publish_date_field,
)


class TestProductAssetLogHR(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.ProductAssetLog = cls.env["resource.asset.log"]
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.HrEmployee = cls.env["hr.employee"]
        cls.ProductProduct = cls.env["product.product"]

        cls.operator = cls.HrEmployee.create(
            {
                "name": "Test Operator",
                "company_id": cls.env.company.id,
            }
        )
        cls.manager = cls.HrEmployee.create(
            {
                "name": "Test Manager",
                "company_id": cls.env.company.id,
            }
        )

        cls.vehicle_template = create_test_template(
            cls.env,
            name="Service Van",
            asset_kind="vehicle",
            type="consu",
            tracking="serial",
        )
        cls.vehicle_product = cls.vehicle_template.product_variant_id

        cls.asset = cls.ProductTrace.create(
            {
                "name": "SERVICE-VAN-001",
                "product_id": cls.vehicle_product.id,
                "operator_id": cls.operator.id,
                "asset_manager_id": cls.manager.id,
                "company_id": cls.env.company.id,
            }
        )

        cls.service_product = create_test_product(
            cls.env,
            name="Fuel Service",
            type="service",
        )

    def test_operator_id_snapshot_from_asset(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log.operator_id, self.operator)

    def test_asset_manager_id_snapshot_from_asset(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log.asset_manager_id, self.manager)

    def test_operator_id_stored(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        field_info = self.ProductAssetLog._fields["operator_id"]
        self.assertTrue(field_info.store)

        self.env.cr.execute(
            "SELECT operator_id FROM resource_asset_log WHERE id = %s", (log.id,)
        )
        result = self.env.cr.fetchone()
        self.assertEqual(result[0], self.operator.id)

    def test_asset_manager_id_stored(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        field_info = self.ProductAssetLog._fields["asset_manager_id"]
        self.assertTrue(field_info.store)

        self.env.cr.execute(
            "SELECT asset_manager_id FROM resource_asset_log WHERE id = %s",
            (log.id,),
        )
        result = self.env.cr.fetchone()
        self.assertEqual(result[0], self.manager.id)

    def test_operator_id_not_related(self):
        field_info = self.ProductAssetLog._fields["operator_id"]
        self.assertFalse(
            field_info.related,
            "operator_id must not be a related field (history would be lost on recompute)",
        )

    def test_asset_manager_id_not_related(self):
        field_info = self.ProductAssetLog._fields["asset_manager_id"]
        self.assertFalse(
            field_info.related,
            "asset_manager_id must not be a related field (history would be lost on recompute)",
        )

    def test_operator_changes_reflected_in_logs(self):
        log1 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log1.operator_id, self.operator)

        new_operator = self.HrEmployee.create(
            {
                "name": "New Operator",
                "company_id": self.env.company.id,
            }
        )

        self.asset.write({"operator_id": new_operator.id})

        log2 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log1.operator_id, self.operator)

        self.assertEqual(log2.operator_id, new_operator)

    def test_manager_changes_reflected_in_logs(self):
        log1 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log1.asset_manager_id, self.manager)

        new_manager = self.HrEmployee.create(
            {
                "name": "New Manager",
                "company_id": self.env.company.id,
            }
        )

        self.asset.write({"asset_manager_id": new_manager.id})

        log2 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log1.asset_manager_id, self.manager)

        self.assertEqual(log2.asset_manager_id, new_manager)

    def test_log_without_operator(self):
        asset_no_operator = self.ProductTrace.create(
            {
                "name": "NO-OPERATOR-VAN",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        log = self.ProductAssetLog.create(
            {
                "asset_id": asset_no_operator.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertFalse(log.operator_id)

    def test_log_without_manager(self):
        asset_no_manager = self.ProductTrace.create(
            {
                "name": "NO-MANAGER-VAN",
                "product_id": self.vehicle_product.id,
                "company_id": self.env.company.id,
            }
        )

        log = self.ProductAssetLog.create(
            {
                "asset_id": asset_no_manager.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertFalse(log.asset_manager_id)

    def test_historical_tracking(self):
        log1 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
                "notes": "Service performed by initial operator",
            }
        )

        initial_operator = log1.operator_id
        initial_manager = log1.asset_manager_id

        new_operator = self.HrEmployee.create(
            {
                "name": "Changed Operator",
                "company_id": self.env.company.id,
            }
        )
        new_manager = self.HrEmployee.create(
            {
                "name": "Changed Manager",
                "company_id": self.env.company.id,
            }
        )

        self.asset.write(
            {
                "operator_id": new_operator.id,
                "asset_manager_id": new_manager.id,
            }
        )

        self.assertEqual(log1.operator_id, initial_operator)
        self.assertEqual(log1.asset_manager_id, initial_manager)

        log2 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
                "notes": "Service performed by changed operator",
            }
        )

        self.assertEqual(log2.operator_id, new_operator)
        self.assertEqual(log2.asset_manager_id, new_manager)

    def test_multiple_assets_different_operators(self):
        operator2 = self.HrEmployee.create(
            {
                "name": "Second Operator",
                "company_id": self.env.company.id,
            }
        )

        asset2 = self.ProductTrace.create(
            {
                "name": "SECOND-VAN",
                "product_id": self.vehicle_product.id,
                "operator_id": operator2.id,
                "company_id": self.env.company.id,
            }
        )

        log1 = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        log2 = self.ProductAssetLog.create(
            {
                "asset_id": asset2.asset_id.id,
                "product_id": self.service_product.id,
            }
        )

        self.assertEqual(log1.operator_id, self.operator)
        self.assertEqual(log2.operator_id, operator2)

    def test_field_help_text(self):
        operator_field = self.ProductAssetLog._fields["operator_id"]
        manager_field = self.ProductAssetLog._fields["asset_manager_id"]

        self.assertIn("operating", operator_field.help.lower())
        self.assertIn("snapshot", operator_field.help.lower())

        self.assertIn("managing", manager_field.help.lower())
        self.assertIn("snapshot", manager_field.help.lower())

    def test_comodel_name(self):
        operator_field = self.ProductAssetLog._fields["operator_id"]
        manager_field = self.ProductAssetLog._fields["asset_manager_id"]

        self.assertEqual(operator_field.comodel_name, "hr.employee")
        self.assertEqual(manager_field.comodel_name, "hr.employee")

    def test_field_string_labels(self):
        operator_field = self.ProductAssetLog._fields["operator_id"]
        manager_field = self.ProductAssetLog._fields["asset_manager_id"]

        self.assertIn("Operator", operator_field.string)
        self.assertIn("Manager", manager_field.string)


class TestOperatorTimeline(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.Log = cls.env["resource.asset.log"]
        cls.category = cls.env.ref(
            "asset_ledger.product_category_operator_assignment",
        )
        cls.driver_2024 = cls.env["hr.employee"].create(
            {"name": "Driver 2024", "company_id": cls.env.company.id},
        )
        cls.driver_2025 = cls.env["hr.employee"].create(
            {"name": "Driver 2025", "company_id": cls.env.company.id},
        )
        cls.driver_2026 = cls.env["hr.employee"].create(
            {"name": "Driver 2026", "company_id": cls.env.company.id},
        )
        template = create_test_template(
            cls.env,
            name="Timeline Van",
            asset_kind="vehicle",
            type="consu",
            tracking="serial",
        )
        cls.product = template.product_variant_id
        cls.assignment_product = cls.env["product.product"].create(
            {
                "name": "Timeline Operator Assignment",
                "categ_id": cls.category.id,
                "type": "service",
            },
        )

    def _rows(self, asset):
        return self.env["resource.assignment"].search(
            [
                ("resource_id", "=", asset.asset_id.resource_id.id),
                ("custody_role", "=", "operator"),
            ],
            order="date_start asc, id asc",
        )

    def _asset(self, operator):
        asset = self.env["product.trace"].create(
            {
                "name": f"TIMELINE-{self.id().rsplit('.', 1)[-1][:20]}",
                "product_id": self.product.id,
                "operator_id": operator.id,
                "company_id": self.env.company.id,
            },
        )
        self._rows(asset).write({"date_start": "2024-01-01 00:00:00"})
        return asset

    def _change_operator(self, asset, operator, when):
        asset.write({"operator_id": operator.id})
        rows = self._rows(asset)
        rows[-2].write({"date_end": when})
        rows[-1].write({"date_start": when})
        self.env.flush_all()

    def test_the_timeline_is_built_from_the_ledger(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")
        self._change_operator(asset, self.driver_2026, "2026-03-01 10:00:00")

        timeline = self.Log._get_employee_timeline(asset.asset_id.id, "operator_id")

        self.assertEqual(
            [(row["old"], row["new"]) for row in timeline],
            [
                (0, self.driver_2024.id),
                (self.driver_2024.id, self.driver_2025.id),
                (self.driver_2025.id, self.driver_2026.id),
            ],
            "Each hand-over must appear once, oldest first, with both ends.",
        )

    def test_create_leaves_the_callers_vals_untouched(self):
        asset = self._asset(self.driver_2024)
        vals = {"asset_id": asset.asset_id.id, "product_id": self.assignment_product.id}
        untouched = dict(vals)

        log = self.Log.create([vals])

        self.assertEqual(log.operator_id, self.driver_2024)
        self.assertEqual(
            vals,
            untouched,
            "create() must not hand the caller back keys it never wrote.",
        )

    def test_the_timeline_sees_a_change_made_in_the_same_transaction(self):
        asset = self._asset(self.driver_2024)
        asset.write({"operator_id": self.driver_2025.id})

        timeline = self.Log._get_employee_timeline(asset.asset_id.id, "operator_id")

        self.assertEqual(
            [(row["old"], row["new"]) for row in timeline],
            [(0, self.driver_2024.id), (self.driver_2024.id, self.driver_2025.id)],
        )

    def test_a_date_before_the_first_change_resolves_to_the_old_value(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")

        resolved = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", date(2024, 6, 1), {}
        )

        self.assertEqual(resolved, self.driver_2024.id)

    def test_a_date_between_changes_resolves_to_the_one_in_force(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")
        self._change_operator(asset, self.driver_2026, "2026-03-01 10:00:00")

        resolved = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", date(2025, 8, 1), {}
        )

        self.assertEqual(resolved, self.driver_2025.id)

    def test_a_change_earlier_the_same_day_counts_as_in_force(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")

        resolved = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", date(2025, 6, 1), {}
        )

        self.assertEqual(resolved, self.driver_2025.id)

    def test_a_change_late_in_the_local_day_counts_as_in_force(self):
        asset = self._asset(self.driver_2024)
        # 02:00 UTC on the 2nd is 20:00 on the 1st in America/Mexico_City.
        self._change_operator(asset, self.driver_2025, "2025-06-02 02:00:00")
        self.env.user.tz = "America/Mexico_City"

        resolved = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", date(2025, 6, 1), {}
        )

        self.assertEqual(
            resolved,
            self.driver_2025.id,
            "The change was made on the 1st in the user's timezone.",
        )

    def test_the_business_date_resolves_the_same_from_a_date_and_a_string(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")

        from_date = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", date(2025, 6, 1), {}
        )
        from_string = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", "2025-06-01", {}
        )

        self.assertEqual(from_date, self.driver_2025.id)
        self.assertEqual(from_string, from_date)

    def test_a_log_is_stamped_the_same_from_a_date_and_a_string(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")

        from_date = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "date": date(2025, 6, 1),
                "product_id": self.assignment_product.id,
            },
        )
        from_string = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "date": "2025-06-01",
                "product_id": self.assignment_product.id,
            },
        )

        self.assertEqual(from_date.operator_id, self.driver_2025)
        self.assertEqual(from_string.operator_id, from_date.operator_id)

    def test_without_history_the_current_value_is_used(self):
        asset = self._asset(self.driver_2024)

        resolved = self.Log._get_employee_at_date(
            asset.asset_id.id, "operator_id", date(2025, 8, 1), {}
        )

        self.assertEqual(resolved, self.driver_2024.id)

    def test_create_stamps_the_operator_of_the_logs_business_date(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")
        self._change_operator(asset, self.driver_2026, "2026-03-01 10:00:00")

        log = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "date": date(2025, 8, 1),
                "product_id": self.assignment_product.id,
            },
        )

        self.assertEqual(
            log.log_type,
            "operator",
            "The fixture has to be an assignment log for this test to mean anything.",
        )
        self.assertEqual(
            log.operator_id,
            self.driver_2025,
            "The log took today's driver instead of the one in force on its own date.",
        )

    def test_an_explicit_operator_is_never_overridden(self):
        asset = self._asset(self.driver_2024)
        self._change_operator(asset, self.driver_2025, "2025-06-01 10:00:00")

        log = self.Log.create(
            {
                "asset_id": asset.asset_id.id,
                "date": date(2025, 8, 1),
                "product_id": self.assignment_product.id,
                "operator_id": self.driver_2026.id,
            },
        )

        self.assertEqual(log.log_type, "operator")
        self.assertEqual(log.operator_id, self.driver_2026)
