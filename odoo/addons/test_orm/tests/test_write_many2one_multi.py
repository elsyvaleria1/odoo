from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestWriteMany2oneMulti(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categories = cls.env["test_orm.coherence.category"].create(
            [{"name": name} for name in ("north", "south", "east")]
        )
        cls.Order = cls.env["test_orm.coherence.order"]
        cls.Line = cls.env["test_orm.coherence.line"]

    def _orders(self, count=3):
        orders = self.Order.create(
            [{"name": f"order {index}"} for index in range(count)]
        )
        self.Line.create(
            [{"order_id": order.id, "qty": 1, "price": 10} for order in orders]
        )
        return orders

    def test_each_record_takes_its_own_value_as_one_write_each_would(self):
        north, south, _east = self.categories
        batched, single = self._orders(), self._orders()
        values = [north.id, south.id, False]

        batched._write_many2one_multi("category_id", values)
        for order, value in zip(single, values, strict=True):
            order.write({"category_id": value})

        self.assertEqual(
            batched.mapped("category_name"), single.mapped("category_name")
        )
        self.assertEqual(north.order_ids, batched[0] | single[0])
        self.env.invalidate_all()
        self.assertEqual(
            [order.category_id for order in batched],
            [order.category_id for order in single],
        )

    def test_the_cost_does_not_grow_with_the_records(self):
        def cost(count):
            orders = self._orders(count)
            self.env.flush_all()
            self.env.invalidate_all()
            values = [self.categories[index % 3].id for index in range(count)]
            before = self.env.cr.sql_statement_count
            orders._write_many2one_multi("category_id", values)
            self.env.flush_all()
            return self.env.cr.sql_statement_count - before

        cost(1)
        self.assertEqual(cost(2), cost(8))

    def test_dependents_are_recomputed_on_both_sides(self):
        north, south, _east = self.categories
        orders = self._orders(2)

        orders._write_many2one_multi("category_id", [north.id, south.id])

        self.assertEqual(orders.mapped("category_name"), ["north", "south"])
        self.assertEqual(
            (north.order_total, south.order_total), tuple(orders.mapped("total"))
        )
        self.assertEqual(
            orders.line_ids.mapped("order_category_id"), self.categories[:2]
        )

    def test_write_date_moves_as_a_write_does(self):
        orders = self._orders(2)
        self.env.cr.execute(
            "UPDATE test_orm_coherence_order SET write_date = '2020-01-01' WHERE id = ANY(%s)",
            [orders.ids],
        )
        self.env.invalidate_all()

        orders._write_many2one_multi("category_id", [False, self.categories[0].id])

        self.assertTrue(all(order.write_date.year > 2020 for order in orders))

    def test_only_a_plain_stored_many2one_is_accepted(self):
        orders = self._orders(1)
        for fname in ("name", "tag_ids", "category_name"):
            with self.assertRaises(ValueError):
                orders._write_many2one_multi(fname, [False])
        with self.assertRaises(ValueError):
            orders._write_many2one_multi("category_id", [])

    def test_access_is_checked_as_a_write_does(self):
        orders = self._orders(1)
        portal = self.env["res.users"].create(
            {
                "name": "Reader",
                "login": "many2one-multi-reader",
                "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
            }
        )
        with self.assertRaises(AccessError):
            orders.with_user(portal)._write_many2one_multi(
                "category_id", [self.categories[0].id]
            )
