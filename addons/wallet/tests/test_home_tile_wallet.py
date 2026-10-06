from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHomeTileWalletLow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        prepaid = cls.env["account.account"].create(
            {
                "name": "Tile fuel prepaid",
                "code": "WAL.TILE",
                "account_type": "asset_prepayments",
                "company_ids": [(6, 0, cls.env.company.ids)],
            }
        )
        cls.account = cls.env["wallet.account"].create(
            {
                "name": "Tile fleet",
                "kind": "fuel",
                "issuer_id": cls.env["res.partner"].create({"name": "Issuer"}).id,
                "account_id": prepaid.id,
                "amount_threshold_low": 500.0,
            }
        )
        cls.low, cls.fine = cls.env["wallet.card"].create(
            [
                {"number": "T-LOW", "account_id": cls.account.id},
                {"number": "T-FINE", "account_id": cls.account.id},
            ]
        )
        for card, amount in ((cls.low, 120.0), (cls.fine, 900.0)):
            cls.env["wallet.balance"].create(
                {
                    "card_id": card.id,
                    "amount_balance": amount,
                    "date": fields.Datetime.now(),
                }
            )

    def test_the_wallet_tile_lists_the_cards_below_their_threshold(self):
        data = self.env["home.tile"].get_tiles(
            [{"id": "wallet_low_1", "type": "wallet_low"}]
        )["wallet_low_1"]["data"]
        ids = [card["id"] for card in data["cards"]]
        self.assertIn(self.low.id, ids)
        self.assertNotIn(self.fine.id, ids)
        row = next(card for card in data["cards"] if card["id"] == self.low.id)
        self.assertIn("120", row["balance"])
        self.assertIn("500", row["threshold"])

    def test_the_wallet_tile_keeps_its_statement_count(self):
        request = [{"id": "wallet_low_1", "type": "wallet_low"}]
        self.env["home.tile"].get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(9):
            self.env["home.tile"].get_tiles(request)
