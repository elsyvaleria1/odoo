from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestAssetLedgerCompany(TransactionCase):
    """Where a log's company comes from, and what happens when it disagrees.

    The ledger invariant is one asset, one company. It used to be guarded only
    at the end, by a constraint, while the company itself was seeded from
    ``env.company`` -- the acting user's, which has nothing to do with the
    asset's. Anything running outside the fleet's own company therefore built
    rows the constraint then refused: an import booked 32 of them, repaired by
    the 19.0.1.20.0 migration, and the nightly GPS cron never once succeeded.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["resource.log"]
        cls.owner = cls.env["res.company"].create({"name": "Ledger owner"})
        cls.other = cls.env["res.company"].create({"name": "Somebody else"})
        cls.env.user.company_ids = [
            Command.link(cls.owner.id),
            Command.link(cls.other.id),
        ]
        cls.template = cls.env["product.template"].create(
            {
                "name": "Ledger company probe truck",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
            }
        )
        cls.product = cls.template.product_variant_ids[0]
        cls.asset = cls.env["product.trace"].create(
            {
                "name": "LEDGER-CO-1",
                "product_id": cls.product.id,
                "company_id": cls.owner.id,
            }
        )
        cls.shared_asset = cls.env["product.trace"].create(
            {
                "name": "LEDGER-CO-SHARED",
                "product_id": cls.product.id,
            }
        )

    def _acting_as(self, company):
        """Act *in* `company`, while still allowed to see the other one.

        Both stay allowed on purpose. What is under test is which company a log
        takes, and narrowing the allowed set would mean a cross-company create
        failed on a company guard instead -- refused either way, but for a reason
        that proves nothing about where the company came from.
        """
        others = [other.id for other in (self.owner | self.other) if other != company]
        return self.Log.with_company(company).with_context(
            allowed_company_ids=[company.id, *others]
        )

    def test_a_log_takes_the_company_of_its_asset(self):
        log = self._acting_as(self.other).create({"asset_id": self.asset.asset_id.id})

        self.assertEqual(
            log.company_id,
            self.owner,
            "The ledger's company decides, not the session's.",
        )

    def test_a_company_less_asset_falls_back_to_the_acting_company(self):
        """A shared asset imposes nothing, which is the case the constraint
        already exempts by ignoring empty companies."""
        log = self._acting_as(self.other).create(
            {"asset_id": self.shared_asset.asset_id.id}
        )

        self.assertEqual(log.company_id, self.other)

    def test_an_explicit_company_still_wins(self):
        """The field is computed to seed a value, not to overrule a caller."""
        log = self._acting_as(self.other).create(
            {"asset_id": self.shared_asset.asset_id.id, "company_id": self.owner.id}
        )

        self.assertEqual(log.company_id, self.owner)

    def test_moving_a_log_to_another_asset_moves_its_company(self):
        second_owner_asset = self.env["product.trace"].create(
            {
                "name": "LEDGER-CO-2",
                "product_id": self.product.id,
                "company_id": self.other.id,
            }
        )
        log = self._acting_as(self.other).create({"asset_id": self.asset.asset_id.id})

        log.asset_id = second_owner_asset.asset_id

        self.assertEqual(
            log.company_id,
            self.other,
            "A log re-pointed at another ledger joins that ledger.",
        )

    def test_recompanying_the_asset_leaves_booked_logs_alone(self):
        """The dependency is the coarse `asset_id` on purpose.

        A log is an accounting row whose currency follows its company. Tracking
        `asset_id.company_id` would silently restate every stored figure the
        day somebody edited the asset.
        """
        log = self._acting_as(self.owner).create(
            {"asset_id": self.asset.asset_id.id, "amount": 500.0}
        )

        self.asset.company_id = self.other

        self.assertEqual(log.company_id, self.owner)

    @mute_logger("odoo.addons.resource_asset_product.models.resource_asset_log")
    def test_a_ledger_split_before_this_edit_says_so(self):
        self.Log.create({"asset_id": self.shared_asset.asset_id.id})
        stale = self.Log.create({"asset_id": self.shared_asset.asset_id.id})
        # Planted the way production got its own: a write that bypassed the
        # field, leaving a split the constraint can only report, never prevent.
        self.env.cr.execute(
            "UPDATE resource_log SET company_id = %s WHERE id = %s",
            (self.other.id, stale.id),
        )
        self.env.invalidate_all()

        # The next person to book anything against this asset is the one who
        # meets it, which is the whole reason the message exists.
        with self.assertRaises(ValidationError) as caught:
            self.Log.create({"asset_id": self.shared_asset.asset_id.id})

        self.assertIn("from before this edit", str(caught.exception))

    @mute_logger("odoo.addons.resource_asset_product.models.resource_asset_log")
    def test_a_split_this_edit_causes_does_not_blame_old_data(self):
        """The other branch, and the reason they are told apart.

        Sending a reader after stale rows that are perfectly fine costs them
        the one thing the message was supposed to give them.
        """
        self.Log.create(
            {"asset_id": self.shared_asset.asset_id.id, "company_id": self.owner.id}
        )

        with self.assertRaises(ValidationError) as caught:
            self.Log.create(
                {"asset_id": self.shared_asset.asset_id.id, "company_id": self.other.id}
            )

        message = str(caught.exception)
        self.assertIn("keeps its ledger in one company", message)
        self.assertNotIn("from before this edit", message)
