from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import (
    create_test_template,
    ensure_publish_date_field,
    flush_tracking,
)


class TestSecurityHR(TransactionCase):
    """The HR access rows must not widen what `asset_ledger` narrows.

    `ir.access` ORs the permissions of every group a user holds and only guards
    narrow them, so an HR group whose permission on these models carries no
    domain is left with the multi-company guard alone and reads the whole table.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductAssetLog = cls.env["resource.log"]

        cls.vehicle = cls.ProductTrace.create(
            {
                "name": "SEC-VEHICLE",
                "product_id": create_test_template(
                    cls.env,
                    name="Security Van",
                    asset_kind="vehicle",
                    type="consu",
                    tracking="serial",
                ).product_variant_id.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.machinery = cls.ProductTrace.create(
            {
                "name": "SEC-MACHINERY",
                "product_id": create_test_template(
                    cls.env,
                    name="Security Tractor",
                    asset_kind="machinery",
                    type="consu",
                    tracking="serial",
                ).product_variant_id.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.plain_lot = cls.ProductTrace.create(
            {
                "name": "SEC-WAREHOUSE",
                "product_id": create_test_template(
                    cls.env,
                    name="Security Widget",
                    type="consu",
                    tracking="serial",
                ).product_variant_id.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.hr_user = cls._create_user("sec_hr_user", ["hr.group_hr_user"])
        cls.hr_manager = cls._create_user("sec_hr_manager", ["hr.group_hr_manager"])
        cls.hr_fleet_user = cls._create_user(
            "sec_hr_fleet",
            [
                "hr.group_hr_user",
                "asset_ledger.group_asset_user",
                "asset_ledger.group_enable_fleet_assets",
            ],
        )

    @classmethod
    def _create_user(cls, login, group_xml_ids):
        groups = [cls.env.ref("base.group_user").id]
        groups += [cls.env.ref(xml_id).id for xml_id in group_xml_ids]
        return (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": login, "login": login, "group_ids": [(6, 0, groups)]})
        )

    def test_hr_user_reads_no_lot_outside_the_enabled_asset_kinds(self):
        self.assertTrue(self.hr_user, "the probe user must exist")
        gated = self.hr_user._get_asset_kinds_gated().ids
        self.assertFalse(set(self.hr_user._get_enabled_asset_kinds()) & set(gated))
        self.assertFalse(self.ProductTrace.with_user(self.hr_user).search([]))

    def test_hr_user_reads_only_the_asset_kinds_it_is_enabled_for(self):
        visible = self.ProductTrace.with_user(self.hr_fleet_user).search([])
        self.assertIn(self.vehicle, visible)
        self.assertNotIn(self.machinery, visible)
        self.assertNotIn(self.plain_lot, visible)

    def test_hr_user_cannot_write_a_lot(self):
        with self.assertRaises(AccessError):
            self.vehicle.with_user(self.hr_user).write({"name": "SEC-RENAMED"})

    def test_hr_manager_cannot_write_a_lot(self):
        self.assertTrue(self.hr_manager, "the probe user must exist")
        with self.assertRaises(AccessError):
            self.vehicle.with_user(self.hr_manager).write({"name": "SEC-RENAMED"})

    def test_hr_manager_cannot_create_a_lot(self):
        with self.assertRaises(AccessError):
            self.ProductTrace.with_user(self.hr_manager).create(
                {
                    "name": "SEC-NEW",
                    "product_id": self.vehicle.product_id.id,
                    "company_id": self.env.company.id,
                }
            )

    def test_hr_manager_cannot_create_an_asset_log(self):
        with self.assertRaises(AccessError):
            self.ProductAssetLog.with_user(self.hr_manager).create(
                {"asset_id": self.vehicle.asset_id.id}
            )

    def test_hr_user_reads_no_log_that_has_no_asset(self):
        orphan = self.ProductAssetLog.create(
            {
                "amount": 123456.78,
                "inv_ref": "SEC-CONFIDENTIAL",
                "notes": "board-level repair quote",
            }
        )

        self.assertFalse(orphan.asset_id)
        self.assertNotIn(
            orphan, self.ProductAssetLog.with_user(self.hr_user).search([])
        )

    def test_an_hr_user_that_is_also_an_asset_user_still_reads_orphan_logs(self):
        orphan = self.ProductAssetLog.create({"amount": 5.0})
        asset_user = self._create_user(
            "sec_hr_asset", ["hr.group_hr_user", "asset_ledger.group_asset_user"]
        )

        self.assertIn(orphan, self.ProductAssetLog.with_user(asset_user).search([]))

    def test_hr_user_reads_the_logs_of_the_asset_kinds_it_is_enabled_for(self):
        visible = self.ProductAssetLog.create(
            {"asset_id": self.vehicle.asset_id.id, "amount": 7.0}
        )
        hidden = self.ProductAssetLog.create(
            {"asset_id": self.machinery.asset_id.id, "amount": 7.0}
        )

        readable = self.ProductAssetLog.with_user(self.hr_fleet_user).search([])

        self.assertIn(visible, readable)
        self.assertNotIn(hidden, readable)


class TestOperatorSubtypeVisibility(TransactionCase):
    """Who operates an asset is internal HR and fleet information.

    mail.message.subtype.internal gates a subtype to employees. Both operator
    subtypes are default=True, so without it every follower of a product.trace --
    including a contact with no user account -- is subscribed to them and
    notified of the assignment.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Subtype Driver", "company_id": cls.env.company.id}
        )
        cls.successor = cls.env["hr.employee"].create(
            {"name": "Subtype Successor", "company_id": cls.env.company.id}
        )
        cls.lot = cls.env["product.trace"].create(
            {
                "name": "SUBTYPE-001",
                "product_id": create_test_template(
                    cls.env,
                    name="Subtype Van",
                    asset_kind="vehicle",
                    type="consu",
                    tracking="serial",
                ).product_variant_id.id,
                "operator_id": cls.driver.id,
                "company_id": cls.env.company.id,
            }
        )
        flush_tracking(cls.env)
        cls.outsider = cls.env["res.partner"].create(
            {"name": "Outside Contact", "email": "outside@example.org"}
        )
        cls.lot.asset_id.message_subscribe(partner_ids=cls.outsider.ids)

    def test_both_operator_subtypes_are_internal(self):
        for xml_id in (
            "resource_mail.mt_asset_operator_updated",
            "resource_mail.mt_asset_future_operator_scheduled",
        ):
            self.assertTrue(self.env.ref(xml_id).internal, xml_id)

    def test_the_subtypes_are_named_after_the_role_they_record(self):
        self.assertEqual(
            self.env.ref("resource_mail.mt_asset_operator_updated").name,
            "Operator Updated",
        )
        self.assertEqual(
            self.env.ref("resource_mail.mt_asset_future_operator_scheduled").name,
            "Future Operator Scheduled",
        )

    def test_a_contact_without_a_user_is_not_subscribed_to_them(self):
        self.assertFalse(self.outsider.user_ids)
        follower = self.env["mail.followers"].search(
            [
                ("res_model", "=", "resource.resource"),
                ("res_id", "=", self.lot.asset_id.id),
                ("partner_id", "=", self.outsider.id),
            ]
        )

        self.assertNotIn(
            self.env.ref("resource_mail.mt_asset_operator_updated"),
            follower.subtype_ids,
        )

    def test_a_contact_without_a_user_is_not_told_who_operates(self):
        self.lot.write({"operator_id": self.successor.id})
        flush_tracking(self.env)

        message = self.lot.asset_id.message_ids.sorted("id")[-1]

        self.assertEqual(
            message.subtype_id,
            self.env.ref("resource_mail.mt_asset_operator_updated"),
        )
        self.assertIn(self.successor.name, message.body)
        self.assertNotIn(self.outsider, message.notified_partner_ids)
