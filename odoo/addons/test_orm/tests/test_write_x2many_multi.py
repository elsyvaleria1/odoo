from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestWriteX2manyMulti(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tags = cls.env["test_orm.coherence.tag"].create(
            [{"name": name} for name in ("red", "green", "blue")]
        )
        cls.Order = cls.env["test_orm.coherence.order"]

    def _orders(self, count=3):
        return self.Order.create([{"name": f"order {index}"} for index in range(count)])

    def test_each_record_takes_its_own_value_as_one_write_each_would(self):
        red, green, blue = self.tags
        batched, single = self._orders(), self._orders()
        values = [
            [Command.set([red.id, green.id])],
            [Command.link(blue.id)],
            [Command.clear()],
        ]

        batched._write_x2many_multi("tag_ids", values)
        for order, value in zip(single, values, strict=True):
            order.write({"tag_ids": value})

        self.assertEqual(batched.mapped("tag_names"), single.mapped("tag_names"))
        self.env.invalidate_all()
        self.assertEqual(
            [order.tag_ids for order in batched], [order.tag_ids for order in single]
        )

    def test_the_cost_does_not_grow_with_the_records(self):
        def cost(count):
            orders = self._orders(count)
            self.env.flush_all()
            self.env.invalidate_all()
            values = [[Command.link(self.tags[index % 3].id)] for index in range(count)]
            before = self.env.cr.sql_statement_count
            orders._write_x2many_multi("tag_ids", values)
            self.env.flush_all()
            return self.env.cr.sql_statement_count - before

        cost(1)
        self.assertEqual(cost(2), cost(8))

    def test_dependents_are_recomputed_on_both_sides(self):
        red, green, _blue = self.tags
        orders = self._orders(2)

        orders._write_x2many_multi(
            "tag_ids", [[Command.link(red.id)], [Command.set([red.id, green.id])]]
        )

        self.assertEqual(orders.mapped("tag_names"), ["red", "green,red"])
        self.assertEqual((red.order_count, green.order_count), (2, 1))

    def test_write_date_moves_as_a_write_does(self):
        orders = self._orders(2)
        self.env.cr.execute(
            "UPDATE test_orm_coherence_order SET write_date = '2020-01-01' WHERE id = ANY(%s)",
            [orders.ids],
        )
        self.env.invalidate_all()

        orders._write_x2many_multi("tag_ids", [[], [Command.link(self.tags[0].id)]])

        self.assertTrue(all(order.write_date.year > 2020 for order in orders))

    def test_only_a_plain_stored_x2many_is_accepted(self):
        orders = self._orders(1)
        for fname in ("name", "tag_names"):
            with self.assertRaises(ValueError):
                orders._write_x2many_multi(fname, [False])
        with self.assertRaises(ValueError):
            orders._write_x2many_multi("tag_ids", [])

    def test_access_is_checked_as_a_write_does(self):
        orders = self._orders(1)
        portal = self.env["res.users"].create(
            {
                "name": "Reader",
                "login": "x2many-multi-reader",
                "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
            }
        )
        with self.assertRaises(AccessError):
            orders.with_user(portal)._write_x2many_multi(
                "tag_ids", [[Command.link(self.tags[0].id)]]
            )
