from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestDeviceResource(TransactionCase):
    def _resource(self, name="Physical device", **vals):
        return self.env["resource.resource"].create(
            {
                "name": name,
                "type": "material",
                "tz": "UTC",
                **vals,
            }
        )

    def _device(self, name="Endpoint", **vals):
        return self.env["device.device"].create(
            {
                "name": name,
                "identifier": name,
                "credential_id": False,
                **vals,
            }
        )

    def test_virtual_endpoint_has_no_implicit_resource(self):
        count = (
            self.env["resource.resource"]
            .with_context(active_test=False)
            .search_count([])
        )
        device = self._device()
        self.assertFalse(device.resource_id)
        self.assertEqual(
            self.env["resource.resource"]
            .with_context(active_test=False)
            .search_count([]),
            count,
        )

    def test_multiple_endpoints_share_identity_without_owning_it(self):
        resource = self._resource(capacity=3, tz="Asia/Tokyo")
        first = self._device("First", resource_id=resource.id)
        second = self._device("Second", resource_id=resource.id, parent_id=first.id)
        self.assertEqual(first.resource_id, second.resource_id)
        self.assertEqual(resource.device_ids, first | second)
        self.assertFalse(resource.membership_ids)
        copied = first.copy(
            {"identifier": "Copied", "name": "Copied", "credential_id": False}
        )
        self.assertFalse(copied.resource_id)
        first.unlink()
        self.assertFalse((first | second).exists())
        self.assertTrue(resource.exists())
        self.assertEqual(resource.capacity, 3)
        self.assertEqual(resource.tz, "Asia/Tokyo")

    def test_endpoint_parent_does_not_reparent_resource(self):
        whole = self._resource("Whole")
        member = self._resource("Member")
        parent = self._device("Parent", resource_id=whole.id)
        device = self._device("Child", resource_id=member.id, parent_id=parent.id)
        self.assertFalse(member.membership_ids)
        device.parent_id = False
        self.assertEqual(device.resource_id, member)
        self.assertFalse(whole.relation_ids)

    def test_endpoint_manager_references_without_resource_write_authority(self):
        user = new_test_user(
            self.env,
            login="resource_endpoint_manager",
            groups="device.group_device_manager",
        )
        resource = self._resource()
        device = (
            self.env["device.device"]
            .with_user(user)
            .create(
                {
                    "name": "Managed endpoint",
                    "identifier": "MANAGED-ENDPOINT",
                    "resource_id": resource.id,
                }
            )
        )
        self.assertEqual(device.resource_id, resource)
        with self.assertRaises(AccessError), self.cr.savepoint():
            device.resource_id.capacity = 2
        device.resource_id = False
        self.assertTrue(resource.exists())

    def test_foreign_identity_is_not_available_to_endpoint_manager(self):
        user = new_test_user(
            self.env,
            login="restricted_endpoint_manager",
            groups="device.group_device_manager",
        )
        company = self.env["res.company"].create({"name": "Foreign endpoint company"})
        resource = self._resource(company_id=company.id)
        Device = self.env["device.device"].with_user(user)
        with self.assertRaises(AccessError), self.cr.savepoint():
            Device.with_context(default_resource_id=resource.id).create(
                {"name": "Hidden", "identifier": "HIDDEN"}
            )
        device = Device.create({"name": "Visible", "identifier": "VISIBLE"})
        with self.assertRaises(AccessError), self.cr.savepoint():
            device.resource_id = resource
        self.assertFalse(device.resource_id)

    def test_represented_identity_cannot_change_type_or_conflict_with_company(self):
        resource = self._resource()
        device = self._device(resource_id=resource.id, active=False)
        company = self.env["res.company"].create({"name": "Other endpoint company"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            resource.type = "human"
        with self.assertRaises(ValidationError), self.cr.savepoint():
            resource.company_id = company
        with self.assertRaises(UserError), self.cr.savepoint():
            device.company_id = company
        with self.assertRaises(ValidationError), self.cr.savepoint():
            device.resource_id = self._resource(type="human")

    def test_shared_resource_can_have_endpoints_in_several_companies(self):
        resource = self._resource(company_id=False)
        company = self.env["res.company"].create({"name": "Other endpoints"})
        first = self._device("First shared", resource_id=resource.id)
        second = self._device(
            "Second shared", resource_id=resource.id, company_id=company.id
        )
        self.assertEqual(resource.device_ids, first | second)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            resource.company_id = self.env.company

    def test_integrity_probe_accepts_multiple_endpoints_and_shared_companies(self):
        resource = self._resource(company_id=False)
        company = self.env["res.company"].create({"name": "Shared probe endpoints"})
        first = self._device("Probe first", resource_id=resource.id)
        second = self._device(
            "Probe second", resource_id=resource.id, company_id=company.id
        )
        report = self.env["device.device"]._probe_integrity()
        self.assertNotIn("duplicate_asset_facets", report)
        for reason in ("resource_company_mismatch", "non_material_resource"):
            self.assertFalse(set((first | second).ids) & set(report[reason]["ids"]))

    def test_integrity_probe_reports_invalid_resource_reference_without_repairing_it(
        self,
    ):
        resource = self._resource()
        device = self._device(resource_id=resource.id)
        company = self.env["res.company"].create({"name": "Conflicting probe company"})
        self.env.flush_all()
        self.cr.execute(
            "UPDATE device_device SET company_id=%s WHERE id=%s",
            [company.id, device.id],
        )
        device.invalidate_recordset(["company_id"])
        report = device._probe_integrity()
        self.assertIn(device.id, report["resource_company_mismatch"]["ids"])
        self.assertEqual(device.company_id, company)

    def test_retirement_preserves_an_archived_endpoint_identity(self):
        resource = self._resource()
        self._device(resource_id=resource.id, active=False)
        resource._archive_if_unused()
        self.assertTrue(resource.active)
