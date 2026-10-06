from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.asset_ledger.tests.common import create_test_template


@tagged("post_install", "-at_install")
class TestCardAsset(TransactionCase):
    def test_a_transaction_follows_its_card_to_the_asset(self):
        template = create_test_template(
            self.env, name="Wallet Van", asset_kind="vehicle", tracking="serial"
        )
        lot = self.env["product.trace"].create(
            {
                "name": "WAL-VAN-1",
                "product_id": template.product_variant_id.id,
                "company_id": self.env.company.id,
                "license_plate": "WAL-001",
            }
        )
        issuer = self.env["res.partner"].create({"name": "Fuel issuer"})
        account = self.env["wallet.account"].create(
            {"name": "Fuel fleet", "kind": "fuel", "issuer_id": issuer.id}
        )
        card = self.env["wallet.card"].create(
            {"number": "77", "account_id": account.id, "asset_id": lot.asset_id.id}
        )
        transaction = self.env["wallet.transaction"].create(
            {"card_id": card.id, "amount": 12.0}
        )
        self.assertEqual(card.trace_id, lot)
        self.assertEqual(card.license_plate, "WAL-001")
        self.assertEqual(transaction.asset_id, lot.asset_id)
        self.assertEqual(transaction.trace_id, lot)

    def test_the_asset_reads_its_cards_balance_and_rule(self):
        template = create_test_template(
            self.env, name="Wallet Truck", asset_kind="vehicle", tracking="serial"
        )
        lot = self.env["product.trace"].create(
            {
                "name": "WAL-TRK-1",
                "product_id": template.product_variant_id.id,
                "company_id": self.env.company.id,
            }
        )
        asset = lot.asset_id
        self.assertEqual(asset.fuel_card_balance, 0.0, "no card yet")
        issuer = self.env["res.partner"].create({"name": "Issuers"})
        fuel = self.env["wallet.account"].create(
            {"name": "Fuel", "kind": "fuel", "issuer_id": issuer.id}
        )
        toll = self.env["wallet.account"].create(
            {"name": "Toll", "kind": "toll", "issuer_id": issuer.id}
        )
        fuel_card = self.env["wallet.card"].create(
            {"number": "F1", "account_id": fuel.id, "asset_id": asset.id}
        )
        toll_tag = self.env["wallet.card"].create(
            {"number": "T1", "account_id": toll.id, "asset_id": asset.id}
        )
        self.assertEqual(asset.fuel_wallet_card_id, fuel_card)
        self.assertEqual(asset.toll_wallet_card_id, toll_tag)
        self.assertEqual(asset.fuel_card_balance, 0.0, "no snapshot yet")
        self.env["wallet.balance"].create(
            [
                {
                    "card_id": fuel_card.id,
                    "amount_balance": 100.0,
                    "date": fields.Datetime.now(),
                },
                {
                    "card_id": toll_tag.id,
                    "amount_balance": 40.0,
                    "date": fields.Datetime.now(),
                },
            ]
        )
        self.assertEqual(asset.fuel_card_balance, 100.0)
        self.assertEqual(asset.highway_pass_balance, 40.0)
        self.assertEqual(lot.asset_id.fuel_card_balance, 100.0)
        self.assertEqual(asset.fuel_card_balance_to_reload, 0.0, "no rule yet")
        rule = self.env["wallet.reorder.rule"].create(
            {"card_id": fuel_card.id, "amount_min": 500.0, "amount_max": 1000.0}
        )
        self.assertEqual(asset.fuel_card_budget, 1000.0)
        self.assertEqual(asset.fuel_card_balance_to_reload, 900.0)
        fuel_card.amount_budget = 1200.0
        self.assertEqual(rule.amount_max, 1200.0)
        self.assertEqual(asset.fuel_card_balance_to_reload, 1100.0)
        self.assertEqual(asset.count_wallet_card, 2)
