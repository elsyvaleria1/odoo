from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestQuantCounting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Quant = cls.env["stock.quant"]
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.customer = cls.env.ref("stock.stock_location_customers")

    def _product(self, name):
        return self.env["product.product"].create({"name": name, "is_storable": True})

    def _quants(self, product):
        return self.Quant.search(
            [("product_id", "=", product.id), ("location_id", "=", self.stock.id)]
        )

    def test_setting_on_hand_to_its_value_counts_nothing(self):
        product = self._product("Unchanged")
        self.Quant._update_available_quantity(product, self.stock, 5.0)
        quant = self._quants(product)
        date_before = quant.inventory_date

        product.qty_available = 5.0

        self.assertRecordValues(
            quant,
            [
                {
                    "quantity": 5.0,
                    "inventory_quantity_set": False,
                    "user_id": False,
                    "inventory_date": date_before,
                }
            ],
        )

    def test_setting_an_empty_product_to_zero_leaves_no_quant(self):
        product = self._product("Empty")
        product.qty_available = 0.0
        self.Quant._remove_zero_quants()
        self.assertFalse(self._quants(product))

    def test_on_hand_cannot_be_set_through_a_filtered_view(self):
        product = self._product("Filtered")
        owner = self.env["res.partner"].create({"name": "Owner"})
        self.Quant._update_available_quantity(product, self.stock, 5.0, owner_id=owner)
        with self.assertRaises(UserError):
            product.with_context(owner_id=owner.id).qty_available = 8.0
        self.assertEqual(sum(self._quants(product).mapped("quantity")), 5.0)

    def test_merging_counted_duplicates_keeps_both_differences(self):
        product = self._product("Duplicates")
        first, second = self.Quant.create(
            [
                {
                    "product_id": product.id,
                    "location_id": self.stock.id,
                    "quantity": 3.0,
                },
                {
                    "product_id": product.id,
                    "location_id": self.stock.id,
                    "quantity": 4.0,
                },
            ]
        )
        first.with_context(inventory_mode=True).inventory_quantity = 3.0
        second.with_context(inventory_mode=True).inventory_quantity = 6.0
        self.env.flush_all()

        self.Quant._merge_quants()

        merged = self._quants(product)
        self.assertRecordValues(
            merged,
            [
                {
                    "quantity": 7.0,
                    "inventory_quantity": 9.0,
                    "inventory_diff_quantity": 2.0,
                }
            ],
        )
        self.assertFalse(merged.is_outdated)
        merged.action_apply_inventory()
        self.assertEqual(merged.quantity, 9.0)

    def test_auto_applied_counts_are_validated_once(self):
        products = [self._product(f"Auto {index}") for index in range(4)]
        Move = type(self.env["stock.move"])
        with patch.object(
            Move, "_action_done", autospec=True, side_effect=Move._action_done
        ) as action_done:
            self.Quant.with_context(inventory_mode=True).create(
                [
                    {
                        "product_id": product.id,
                        "location_id": self.stock.id,
                        "inventory_quantity_auto_apply": 2.0,
                    }
                    for product in products
                ]
            )
        self.assertEqual(action_done.call_count, 1)
        for product in products:
            self.assertEqual(self._quants(product).quantity, 2.0)

    def test_an_imported_count_sets_the_quantity(self):
        product = self._product("Imported")
        self.Quant._update_available_quantity(product, self.stock, 7.0)
        self.Quant.with_context(inventory_mode=True, import_file=True).create(
            {
                "product_id": product.id,
                "location_id": self.stock.id,
                "inventory_quantity_auto_apply": 10.0,
            }
        )
        self.assertEqual(sum(self._quants(product).mapped("quantity")), 10.0)

    def test_imported_rows_of_one_place_add_up_to_one_count(self):
        product = self._product("Imported rows")
        bystander = self._product("Imported bystander")
        self.Quant._update_available_quantity(bystander, self.stock, 2.0)
        self._quants(bystander).with_context(
            inventory_mode=True
        ).inventory_quantity = 9.0
        self.Quant.with_context(inventory_mode=True, import_file=True).create(
            [
                {
                    "product_id": product.id,
                    "location_id": self.stock.id,
                    "inventory_quantity_auto_apply": quantity,
                }
                for quantity in (3.0, 4.0)
            ]
        )
        self.assertEqual(sum(self._quants(product).mapped("quantity")), 7.0)
        self.assertEqual(
            self._quants(bystander).quantity, 2.0, "another product's count waits"
        )

    def test_viewing_one_product_maintains_only_that_product(self):
        viewed, other = self._product("Viewed"), self._product("Other")
        for product in (viewed, other):
            self.Quant.create(
                [
                    {
                        "product_id": product.id,
                        "location_id": self.stock.id,
                        "quantity": 1.0,
                    }
                    for _copy in range(2)
                ]
            )
        self.env.flush_all()

        viewed.action_view_quants()

        self.assertEqual(len(self._quants(viewed)), 1)
        self.assertEqual(len(self._quants(other)), 2)

    def test_an_unreserved_move_counts_as_owned_by_nobody(self):
        product = self._product("Owners")
        move = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom_qty": 4.0,
                "location_id": self.stock.id,
                "location_dest_id": self.customer.id,
            }
        )
        move._action_confirm()
        self.assertFalse(move.move_line_ids)
        for context in ({}, {"owner_id": False}, {"owners": []}, {"owners": [False]}):
            with self.subTest(context=context):
                product.invalidate_recordset(["qty_outgoing"])
                self.assertEqual(product.with_context(**context).qty_outgoing, 4.0)
