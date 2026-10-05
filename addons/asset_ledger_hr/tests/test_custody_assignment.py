from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.asset_ledger.tests.common import create_test_template


@tagged("post_install", "-at_install")
class TestCustodyAssignment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.driver = cls.env["hr.employee"].create({"name": "Ana"})
        cls.other = cls.env["hr.employee"].create({"name": "Bo"})
        cls.manager = cls.env["hr.employee"].create({"name": "Cy"})
        template = create_test_template(
            cls.env, name="Van", asset_kind="vehicle", tracking="serial"
        )
        cls.lot = cls.env["product.trace"].create(
            {
                "name": "VAN-1",
                "product_id": template.product_variant_id.id,
                "company_id": cls.env.company.id,
                "operator_id": cls.driver.id,
                "asset_manager_id": cls.manager.id,
            }
        )
        cls.asset = cls.lot.asset_id

    def _open(self, role):
        return self.env["resource.assignment"].search(
            [
                ("resource_id", "=", self.asset.id),
                ("custody_role", "=", role),
                ("date_end", "=", False),
                ("date_start", "<=", fields.Datetime.now()),
            ]
        )

    def _planned(self):
        return self.env["resource.assignment"].search(
            [
                ("resource_id", "=", self.asset.id),
                ("custody_role", "=", "operator"),
                ("date_end", "=", False),
                ("date_start", ">", fields.Datetime.now()),
            ]
        )

    def _rows(self, role, resource=None):
        """The full shape of every row for `role`, archived ones included.

        Asserting on the open row alone hides a leaked sibling: a search for
        `date_end = False` cannot tell one open row from two.
        """
        return [
            (row.assignee_id.name, row.custody_role, bool(row.date_end), row.active)
            for row in self.env["resource.assignment"]
            .with_context(active_test=False)
            .search(
                [
                    ("resource_id", "=", (resource or self.asset).id),
                    ("custody_role", "=", role),
                ]
            )
        ]

    def _live(self, role, resource=None):
        return [row for row in self._rows(role, resource) if not row[2]]

    def _new_lot(self, name, asset_kind="vehicle", **vals):
        template = create_test_template(
            self.env, name=f"{name} T", asset_kind=asset_kind, tracking="serial"
        )
        return self.env["product.trace"].create(
            {
                "name": name,
                "product_id": template.product_variant_id.id,
                "company_id": self.env.company.id,
                **vals,
            }
        )

    def test_operator_and_manager_are_open_assignments(self):
        self.assertEqual(self._open("operator").assignee_id, self.driver.resource_id)
        self.assertEqual(self._open("manager").assignee_id, self.manager.resource_id)
        self.assertEqual(
            self.asset._get_holder(custody_role="operator"), self.driver.resource_id
        )
        self.assertEqual(
            self.asset._get_holder(custody_role="manager"), self.manager.resource_id
        )

    def test_changing_the_operator_ends_one_and_opens_the_next(self):
        first = self._open("operator")
        self.lot.operator_id = self.other
        self.assertTrue(first.date_end)
        self.assertEqual(first.state, "ended")
        self.assertEqual(self._open("operator").assignee_id, self.other.resource_id)
        self.assertEqual(
            self.env["resource.assignment"].search_count(
                [
                    ("resource_id", "=", self.asset.id),
                    ("custody_role", "=", "operator"),
                ]
            ),
            2,
        )

    def test_clearing_the_operator_ends_custody(self):
        self.lot.operator_id = False
        self.assertFalse(self._open("operator"))
        self.assertFalse(self.asset._get_holder(custody_role="operator"))
        self.assertEqual(self._open("manager").assignee_id, self.manager.resource_id)

    def test_accepting_the_future_operator_moves_custody(self):
        self.lot.future_operator_id = self.other
        self.assertEqual(self._open("operator").assignee_id, self.driver.resource_id)
        self.assertEqual(self._planned().assignee_id, self.other.resource_id)
        self.assertEqual(self.asset.future_operator_employee_id, self.other)
        self.lot.action_accept_operator_change()
        self.assertEqual(self.lot.operator_id, self.other)
        self.assertEqual(self._open("operator").assignee_id, self.other.resource_id)
        self.assertFalse(self._planned())
        self.assertFalse(self.lot.future_operator_id)

    def test_a_scheduled_hand_over_takes_effect_on_its_date(self):
        self.lot.future_operator_id = self.other
        planned = self._planned()
        self.assertEqual(
            planned.date_start.date(),
            (fields.Datetime.now() + timedelta(days=7)).date(),
            "a hand-over scheduled without a date takes effect in a week",
        )
        self.lot.date_future_operator = fields.Datetime.now() + timedelta(days=30)
        self.assertEqual(
            self._planned().date_start.date(),
            (fields.Datetime.now() + timedelta(days=30)).date(),
        )
        self.assertEqual(self.lot.future_operator_id, self.other)
        with patch.object(
            fields.Datetime,
            "now",
            return_value=fields.Datetime.now() + timedelta(days=31),
        ):
            # Custody is read off the resource; a clock that moved needs
            # both records forgotten.
            self.asset.invalidate_recordset()
            self.asset.invalidate_recordset()
            self.assertEqual(self.asset.operator_employee_id, self.other)
            self.assertFalse(self.asset.future_operator_employee_id)

    def test_a_hand_over_cannot_be_scheduled_in_the_past(self):
        with self.assertRaises(UserError):
            self.lot.write(
                {
                    "future_operator_id": self.other.id,
                    "date_future_operator": fields.Datetime.now() - timedelta(days=1),
                }
            )

    def test_rewriting_the_same_operator_opens_nothing(self):
        before = self._open("operator")
        self.lot.operator_id = self.driver
        self.assertEqual(self._open("operator"), before)

    def test_losing_the_asset_ends_custody(self):
        """The mirror has to record the way out, not only the way in.

        `write` re-syncs `self.filtered("asset_id")` after the write, so a lot
        that just lost its asset filters itself out and its row stayed open
        forever -- `_get_holder` kept naming the ex-operator.
        """
        self.lot.asset_id = False

        self.assertFalse(self._live("operator"))
        self.assertFalse(self._live("manager"))
        self.assertFalse(self.asset._get_holder(custody_role="operator"))
        self.assertEqual(self._rows("operator"), [("Ana", "operator", True, True)])

    def test_unlinking_the_lot_ends_custody(self):
        """An open row also blocks deleting the resource for good.

        `resource.assignment.resource_id` is `ondelete="restrict"`, so a row
        left open by a deleted lot pins its `resource.resource` permanently.
        """
        resource = self.asset

        self.lot.unlink()

        self.assertFalse(self._live("operator", resource))
        self.assertFalse(self._live("manager", resource))
        self.assertFalse(
            self.env["resource.assignment"]._get_holder(
                resource, custody_role="operator"
            )
        )

    def test_a_second_live_row_supersedes_the_first(self):
        """Nothing in the model forbids two live rows per role. A rival opened
        by hand used to survive beside the first; now the lot follows the
        newest row and its write ends the other, from whichever side the row
        came."""
        first = self._open("operator")
        rival = self.env["resource.assignment"].create(
            {
                "resource_id": self.asset.id,
                "assignee_id": self.other.resource_id.id,
                "custody_role": "operator",
                "date_start": fields.Datetime.now(),
            }
        )
        self.assertTrue(first.date_end)
        self.assertEqual(self._live("operator"), [("Bo", "operator", False, True)])
        self.assertEqual(self.lot.operator_id, self.other)

        self.lot.operator_id = self.manager

        self.assertTrue(rival.date_end)
        self.assertEqual(self._live("operator"), [("Cy", "operator", False, True)])

    def test_a_future_dated_end_is_superseded_too(self):
        """A row ending in the future is still `state = "active"`.

        The old search matched `date_end = False` only, so this row was never
        closed and `_get_holder` had two candidates to pick from -- both with
        the same `date_start`, which made the winner a tie.
        """
        current = self._open("operator")
        current.date_end = fields.Datetime.now() + timedelta(days=30)
        self.assertEqual(current.state, "active")

        self.lot.operator_id = self.other

        active = self.env["resource.assignment"].search(
            [
                ("resource_id", "=", self.asset.id),
                ("custody_role", "=", "operator"),
                ("state", "=", "active"),
            ]
        )
        self.assertEqual(active.assignee_id, self.other.resource_id)
        self.assertEqual(
            self.asset._get_holder(custody_role="operator"), self.other.resource_id
        )

    def test_an_archived_row_is_superseded_too(self):
        """An archived row is invisible to a default search and still open.

        Unarchiving it would bring back a second current operator.
        """
        self._open("operator").active = False

        self.lot.operator_id = self.other

        self.assertEqual(
            sorted(self._rows("operator")),
            sorted(
                [
                    ("Ana", "operator", True, False),
                    ("Bo", "operator", False, True),
                ]
            ),
        )

    def test_a_batched_write_syncs_in_one_search_and_one_create(self):
        """One search and one create for the whole recordset.

        The 1.4.0 migration hands `_sync_custody` every asset in the database in
        one call, and a list multi-edit hands it the selection.
        """
        lots = self.env["product.trace"].browse()
        for index in range(5):
            lots |= self._new_lot(f"BATCH-{index}")
        self.env.flush_all()

        assignment_class = type(self.env["resource.assignment"])
        real_search = assignment_class.search
        real_create = assignment_class.create
        searches, creates = [], []

        def counting_search(records, *args, **kwargs):
            searches.append(args)
            return real_search(records, *args, **kwargs)

        def counting_create(records, vals_list):
            creates.append(vals_list)
            return real_create(records, vals_list)

        with (
            patch.object(assignment_class, "search", counting_search),
            patch.object(assignment_class, "create", counting_create),
        ):
            lots.write({"asset_manager_id": self.manager.id})
            self.env.flush_all()

        self.assertEqual(len(searches), 1, "One search for the whole batch.")
        self.assertEqual(len(creates), 1, "One create for the whole batch.")
        self.assertEqual(len(creates[0]), 5)


@tagged("post_install", "-at_install")
class TestCustodyReadsFromTheLedger(TestCustodyAssignment):
    """The assignment ledger is the source: the asset reads it, the lot's
    columns follow it, and a row opened or ended on the asset side reaches
    the lot without anyone writing the lot."""

    def test_the_asset_reads_its_operator_and_manager_off_the_ledger(self):
        self.assertEqual(self.asset.operator_employee_id, self.driver)
        self.assertEqual(self.asset.manager_employee_id, self.manager)
        assets = self.env["resource.resource"].search(
            [("operator_employee_id", "=", self.driver.id)]
        )
        self.assertIn(self.asset, assets)
        self.assertNotIn(
            self.asset,
            self.env["resource.resource"].search([("operator_employee_id", "=", False)]),
        )

    def test_writing_the_asset_moves_the_lot(self):
        self.asset.operator_employee_id = self.other
        self.assertEqual(self._open("operator").assignee_id, self.other.resource_id)
        self.assertEqual(self.lot.operator_id, self.other)
        log = self.env["resource.log"].search(
            [("asset_id", "=", self.asset.id), ("source", "=", "assignment")],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.operator_id, self.other)

    def test_ending_the_assignment_clears_the_lot(self):
        self._open("operator").date_end = fields.Datetime.now()
        self.assertFalse(self.asset.operator_employee_id)
        self.assertFalse(self.lot.operator_id)
        self.assertEqual(self.lot.asset_manager_id, self.manager)

    def test_a_row_opened_by_hand_reaches_the_lot(self):
        self._open("manager").unlink()
        self.assertFalse(self.lot.asset_manager_id)
        self.env["resource.assignment"].create(
            {
                "resource_id": self.asset.id,
                "assignee_id": self.other.resource_id.id,
                "custody_role": "manager",
            }
        )
        self.assertEqual(self.asset.manager_employee_id, self.other)
        self.assertEqual(self.lot.asset_manager_id, self.other)
