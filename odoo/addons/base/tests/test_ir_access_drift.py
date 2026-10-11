from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccessDrift(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Drift = cls.env["ir.access.drift"]
        cls.shipped = cls.env.ref("base.access_phone_number_group_user")

    def drifts(self, state):
        return self.Drift.search([("state", "=", state)])

    def set_operation(self, access, operation):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_access SET operation = %s WHERE id = %s", [operation, access.id]
        )
        self.env.invalidate_all()

    def test_a_fresh_installation_parts_from_no_file(self):
        self.Drift._scan()
        self.assertFalse(self.drifts("differs").mapped("xmlid"))
        self.assertFalse(self.drifts("unreadable").mapped("detail"))

    def test_a_row_edited_against_its_file_is_named_and_kept(self):
        original = self.shipped.operation
        self.set_operation(self.shipped, "crud")

        self.Drift._scan()

        [drift] = self.drifts("differs")
        self.assertEqual(drift.xmlid, "base.access_phone_number_group_user")
        self.assertEqual(drift.changed, "operation")
        self.assertIn(f"'crud' -> {original!r}", drift.detail)
        self.assertEqual(self.shipped.operation, "crud")
        self.assertIn(
            self.env.ref("base.group_user"),
            self.env["ir.access"]._get_groups_with_access("phone.number", "unlink"),
        )

    def test_a_drift_is_logged_the_night_it_appears_and_leaves_when_gone(self):
        self.set_operation(self.shipped, "crud")
        self.Drift._scan()
        self.Drift._scan()
        logged = self.env["ir.access.log"].search(
            [("event", "=", "access_drift"), ("res_ids", "=", str(self.shipped.id))]
        )
        self.assertEqual(len(logged), 1)
        first_seen = self.drifts("differs").first_seen

        self.Drift._scan()
        self.assertEqual(self.drifts("differs").first_seen, first_seen)

        self.set_operation(self.shipped, "cr")
        self.Drift._scan()
        self.assertFalse(self.drifts("differs"))

    def test_rows_no_module_ships_are_named_with_who_wrote_them(self):
        Access = self.env["ir.access"]
        values = {
            "model_id": self.env["ir.model"]._get_id("phone.number"),
            "group_id": self.env.ref("base.group_user").id,
            "kind": "permission",
            "operation": "r",
        }
        custom = Access.create({**values, "name": "probe: written by a person"})
        orphan = Access.create({**values, "name": "probe: shipped no more"})
        self.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "probe_row_nobody_ships",
                "model": "ir.access",
                "res_id": orphan.id,
            }
        )

        self.Drift._scan()

        self.assertIn(custom, self.drifts("custom").access_id)
        self.assertEqual(
            self.drifts("custom").filtered(lambda d: d.access_id == custom).writer_id,
            self.env.user,
        )
        self.assertEqual(
            self.drifts("orphan").filtered(lambda d: d.access_id == orphan).xmlid,
            "base.probe_row_nobody_ships",
        )

    def test_a_shipped_row_someone_deleted_is_missing(self):
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM ir_access WHERE id = %s", [self.shipped.id])
        self.env.invalidate_all()

        self.Drift._scan()

        self.assertIn(
            "base.access_phone_number_group_user",
            self.drifts("missing").mapped("xmlid"),
        )
        self.assertFalse(
            self.env["ir.access"].browse(self.shipped.id).exists(),
            "the scan restores nothing",
        )

    def test_a_row_shipped_in_a_noupdate_block_may_be_deleted(self):
        editable = self.env.ref("base.access_res_partner_erp_manager_users")
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM ir_access WHERE id = %s", [editable.id])
        self.env.invalidate_all()

        self.Drift._scan()

        self.assertNotIn(
            "base.access_res_partner_erp_manager_users",
            self.Drift.search([]).mapped("xmlid"),
        )
