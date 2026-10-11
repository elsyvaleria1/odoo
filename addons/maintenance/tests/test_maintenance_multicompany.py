from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestMaintenanceMulticompany(TransactionCase):
    def test_00_maintenance_multicompany_user(self):

        Asset = self.env["resource.resource"]
        MaintenanceOrder = self.env["maintenance.order"]
        Kind = self.env["resource.kind"]
        ResUsers = self.env["res.users"]
        ResCompany = self.env["res.company"]
        MaintenanceTeam = self.env["team.team"]

        group_user = self.env.ref("base.group_user")
        group_manager = self.env.ref("maintenance.group_equipment_manager")

        company_a = ResCompany.create(
            {
                "name": "Company A",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        company_b = ResCompany.create(
            {
                "name": "Company B",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        cids = [company_a.id, company_b.id]
        equipment_manager = ResUsers.create(
            {
                "name": "Equipment Manager",
                "company_id": company_a.id,
                "login": "e_equipment_manager",
                "email": "eqmanager@yourcompany.example.com",
                "group_ids": [(6, 0, [group_manager.id])],
                "company_ids": [(6, 0, [company_a.id, company_b.id])],
            }
        )

        user = ResUsers.create(
            {
                "name": "Normal User/Employee",
                "company_id": company_b.id,
                "login": "emp",
                "email": "empuser@yourcompany.example.com",
                "group_ids": [(6, 0, [group_user.id])],
                "company_ids": [(6, 0, [company_b.id])],
            }
        )

        MaintenanceTeam.with_user(equipment_manager).create(
            {
                "use_maintenance": True,
                "name": "Metrology",
                "company_id": company_a.id,
            }
        )
        (
            MaintenanceTeam.with_user(equipment_manager)
            .with_context(allowed_company_ids=cids)
            .create(
                {
                    "use_maintenance": True,
                    "name": "Subcontractor",
                    "company_id": company_b.id,
                }
            )
        )

        with self.assertRaises(AccessError):
            Kind.with_user(user).create({"name": "Software", "code": "software_test"})
        kind = Kind.with_user(equipment_manager).create(
            {
                "name": "Monitors - Test",
                "code": "monitor_test",
                "technician_user_id": equipment_manager.id,
            }
        )

        with self.assertRaises(AccessError):
            Asset.with_user(user).create(
                {
                    "name": "Samsung Monitor 15",
                    "kind_id": kind.id,
                    "company_id": company_b.id,
                }
            )
        ManagerAsset = Asset.with_user(equipment_manager).with_context(
            allowed_company_ids=cids
        )
        laptop = ManagerAsset.create(
            {"name": "Acer Laptop", "kind_id": kind.id, "company_id": company_b.id}
        )
        ManagerAsset.create(
            {"name": "HP Laptop", "kind_id": kind.id, "company_id": company_a.id}
        )
        self.assertEqual(laptop.technician_user_id, equipment_manager)
        self.assertEqual(ManagerAsset.search_count([("kind_id", "=", kind.id)]), 2)
        self.assertEqual(
            Asset.with_user(user).search([("kind_id", "=", kind.id)]), laptop
        )

        with self.assertRaises(AccessError):
            MaintenanceTeam.with_user(user).create(
                {
                    "use_maintenance": True,
                    "name": "Subcontractor",
                    "company_id": company_b.id,
                }
            )

        MaintenanceOrder.with_user(user).create(
            {
                "name": "Some keys are not working",
                "company_id": company_b.id,
                "user_id": user.id,
            }
        )

        MaintenanceOrder.with_user(equipment_manager).create(
            {
                "name": "Battery drains fast",
                "company_id": company_a.id,
                "user_id": equipment_manager.id,
            }
        )

        self.assertEqual(
            MaintenanceOrder.with_user(equipment_manager)
            .with_context(allowed_company_ids=cids)
            .search_count([]),
            2,
        )
        self.assertEqual(MaintenanceOrder.with_user(user).search_count([]), 1)
