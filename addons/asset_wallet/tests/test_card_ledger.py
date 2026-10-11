from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import create_test_template


@tagged("post_install", "-at_install")
class TestCardLedger(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["resource.log"]
        cls.fuel_product = cls.env.ref("asset_ledger.product_product_fuel_debit")
        cls.toll_product = cls.env.ref("asset_ledger.product_product_highway_debit")
        issuer = cls.env["res.partner"].create({"name": "Card issuer"})
        cls.fuel_account = cls.env["wallet.account"].create(
            {"name": "Fuel", "kind": "fuel", "issuer_id": issuer.id}
        )
        cls.toll_account = cls.env["wallet.account"].create(
            {"name": "Toll", "kind": "toll", "issuer_id": issuer.id}
        )
        template = create_test_template(
            cls.env, name="Ledger truck", asset_kind="vehicle", tracking="serial"
        )
        cls.product = template.product_variant_id

    def _asset(self, name):
        return (
            self.env["product.trace"]
            .create(
                {
                    "name": name,
                    "product_id": self.product.id,
                    "company_id": self.env.company.id,
                }
            )
            .asset_id
        )

    def _card(self, asset, account, number, opening=0.0):
        return self.env["wallet.card"].create(
            {
                "number": number,
                "account_id": account.id,
                "asset_id": asset.id,
                "opening_balance": opening,
            }
        )

    def _log(self, asset, product, amount, **vals):
        return self.Log.create(
            {
                "asset_id": asset.id,
                "product_id": product.id,
                "amount": amount,
                "state": "done",
                **vals,
            }
        )

    def test_the_opening_balance_is_the_balance_until_something_is_booked(self):
        asset = self._asset("SN-012")
        card = self._card(asset, self.fuel_account, "F-012", opening=1000.0)
        self.assertEqual(card.amount_balance, 1000.0)
        self.assertEqual(asset.fuel_card_balance, 1000.0)

    def test_a_done_fuel_log_debits_the_fuel_card(self):
        asset = self._asset("SN-013")
        card = self._card(asset, self.fuel_account, "F-013", opening=1000.0)
        self._log(asset, self.fuel_product, 500.0)
        self.assertEqual(card.amount_balance, 500.0)
        self.assertEqual(asset.fuel_card_balance, 500.0)

    def test_a_credit_log_reloads_the_card(self):
        asset = self._asset("SN-FC-CREDIT")
        card = self._card(asset, self.fuel_account, "F-CR", opening=1000.0)
        self._log(asset, self.fuel_product, -200.0)
        self.assertEqual(card.amount_balance, 1200.0)

    def test_the_toll_card_reads_the_highway_logs_only(self):
        asset = self._asset("SN-017")
        fuel = self._card(asset, self.fuel_account, "F-017", opening=800.0)
        toll = self._card(asset, self.toll_account, "T-017", opening=500.0)
        self._log(asset, self.toll_product, 150.0)
        self._log(asset, self.fuel_product, 200.0)
        self.assertEqual(toll.amount_balance, 350.0)
        self.assertEqual(fuel.amount_balance, 600.0)
        self.assertEqual(asset.highway_pass_balance, 350.0)
        self.assertEqual(asset.fuel_card_balance, 600.0)

    def test_a_new_or_cancelled_log_books_nothing(self):
        asset = self._asset("SN-HWY-NEW")
        toll = self._card(asset, self.toll_account, "T-NEW", opening=500.0)
        self._log(asset, self.toll_product, 150.0, state="new")
        self._log(asset, self.toll_product, 100.0, state="new").action_set_cancelled()
        self.assertEqual(toll.amount_balance, 500.0)

    def test_an_archived_log_leaves_the_balance(self):
        asset = self._asset("SN-ARCHIVE")
        fuel = self._card(asset, self.fuel_account, "F-AR", opening=800.0)
        log = self._log(asset, self.fuel_product, 200.0)
        self.assertEqual(fuel.amount_balance, 600.0)
        log.active = False
        self.assertEqual(fuel.amount_balance, 800.0)

    def test_every_fuel_category_hits_the_card(self):
        asset = self._asset("INV-D")
        fuel = self._card(asset, self.fuel_account, "F-D", opening=1000.0)
        category = self.env["product.category"].create(
            {"name": "Diesel", "log_type": "fuel"}
        )
        diesel = (
            self.env["product.template"]
            .create({"name": "Diesel product", "categ_id": category.id})
            .product_variant_ids[0]
        )
        self._log(asset, self.fuel_product, 100.0)
        self._log(asset, diesel, 250.0)
        self.assertEqual(fuel.amount_balance, 650.0)

    def test_the_balance_does_not_depend_on_the_readers_context(self):
        asset = self._asset("INV-B")
        fuel = self._card(asset, self.fuel_account, "F-B", opening=1000.0)
        self._log(asset, self.fuel_product, 100.0)
        self._log(asset, self.fuel_product, 50.0).action_archive()
        self.assertEqual(fuel.amount_balance, 900.0)
        self.assertEqual(fuel.with_context(active_test=False).amount_balance, 900.0)
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT amount_balance FROM wallet_card WHERE id = %s", (fuel.id,)
        )
        self.assertEqual(self.env.cr.fetchone()[0], 900.0)

    def test_a_reported_balance_supersedes_the_ledger(self):
        asset = self._asset("SN-REPORTED")
        fuel = self._card(asset, self.fuel_account, "F-REP", opening=1000.0)
        self._log(asset, self.fuel_product, 300.0)
        self.assertEqual(fuel.amount_balance, 700.0)
        self.env["wallet.balance"].create({"card_id": fuel.id, "amount_balance": 123.0})
        self.assertEqual(fuel.amount_balance, 123.0)
        self._log(asset, self.fuel_product, 50.0)
        self.assertEqual(fuel.amount_balance, 123.0, "the issuer's word stands")

    def test_the_budget_and_reload_come_from_the_rule(self):
        asset = self._asset("SN-014")
        fuel = self._card(asset, self.fuel_account, "F-014", opening=200.0)
        self.assertEqual(asset.fuel_card_balance_to_reload, 0.0, "no rule yet")
        self.env["wallet.reorder.rule"].create(
            {"card_id": fuel.id, "amount_min": 500.0, "amount_max": 1000.0}
        )
        self.assertEqual(asset.fuel_card_budget, 1000.0)
        self.assertEqual(asset.fuel_card_balance_to_reload, 800.0)
