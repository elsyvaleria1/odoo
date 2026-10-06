import operator as pyoperator

from odoo.fields import Domain
from odoo.tests import TransactionCase

_PYOPS = {
    "<": pyoperator.lt,
    "<=": pyoperator.le,
    ">": pyoperator.gt,
    ">=": pyoperator.ge,
    "=": pyoperator.eq,
    "!=": pyoperator.ne,
}


def _reads(record_value, op, value):
    if op in ("=", "!="):
        return _PYOPS[op](record_value, value)
    return _PYOPS[op](record_value or type(value)(), value)


class TestRelatedSearchMissingStep(TransactionCase):
    def _assert_search_reads_values(self, records, fname, conditions):
        Model = records.browse()
        scope = Domain("id", "in", records.ids)
        for op, value in conditions:
            with self.subTest(field=fname, operator=op, value=value):
                expected = records.browse(
                    r.id for r in records if _reads(r[fname], op, value)
                )
                domain = Domain(fname, op, value)
                self.assertEqual(Model.search(scope & domain), expected)
                self.assertEqual(Model.search(scope & ~domain), records - expected)

    def test_a_float_through_an_empty_many2one_reads_zero(self):
        Foo = self.env["test_orm.related_foo"]
        Related = self.env["test_orm.related"]
        records = Related.create(
            [
                {},
                {"foo_id": Foo.create({"test_float": 0.0}).id},
                {"foo_id": Foo.create({"test_float": 3.0}).id},
                {"foo_id": Foo.create({"test_float": 9.0}).id},
            ]
        )
        self.assertEqual(records[0].foo_float_id, 0.0)
        self._assert_search_reads_values(
            records,
            "foo_float_id",
            [
                ("<=", 7.0),
                ("<", 3.0),
                ("<", 0.0),
                (">=", 0.0),
                (">=", -1.0),
                (">", -1.0),
                (">", 0.0),
                ("=", 0.0),
                ("!=", 3.0),
            ],
        )

    def test_an_integer_through_an_empty_many2one_reads_zero(self):
        Target = self.env["test_orm.model.some_access"]
        Source = self.env["test_orm.model2.some_access"]
        records = Source.create(
            [
                {},
                {"g_id": Target.create({"d": 0}).id},
                {"g_id": Target.create({"d": 3}).id},
                {"g_id": Target.create({"d": 9}).id},
            ]
        )
        self.assertEqual(records[0].g_d, 0)
        self._assert_search_reads_values(
            records,
            "g_d",
            [("<=", 7), ("<", 0), (">=", -1), (">", 0), ("=", 0), ("!=", 9)],
        )

    def test_a_char_through_two_empty_steps_reads_empty(self):
        Bar = self.env["test_orm.related_bar"]
        Foo = self.env["test_orm.related_foo"]
        Related = self.env["test_orm.related"]
        records = Related.create(
            [
                {},
                {"foo_id": Foo.create({}).id},
                {"foo_id": Foo.create({"bar_id": Bar.create({"name": "d"}).id}).id},
                {"foo_id": Foo.create({"bar_id": Bar.create({"name": "z"}).id}).id},
            ]
        )
        self.assertFalse(records[0].foo_bar_name_sudo)
        self.assertFalse(records[1].foo_bar_name_sudo)
        self._assert_search_reads_values(
            records,
            "foo_bar_name_sudo",
            [("<", "m"), ("<=", "d"), (">", "a"), (">=", "a"), ("!=", "d")],
        )

    def test_a_related_field_through_an_empty_one2one_reads_its_falsy_value(self):
        self.env["ir.model.fields"].create(
            {
                "model_id": self.env["ir.model"]._get_id("test_orm.seat.holder"),
                "name": "x_seat_name",
                "ttype": "char",
                "related": "seat_id.name",
                "store": False,
            }
        )
        Holder = self.env["test_orm.seat.holder"]
        records = Holder.create([{"name": n} for n in ("none", "d", "z")])
        self.env["test_orm.seat"].create(
            [
                {"name": "d", "holder_id": records[1].id},
                {"name": "z", "holder_id": records[2].id},
            ]
        )
        self.assertFalse(records._fields["x_seat_name"].store)
        self.assertFalse(records[0].x_seat_name)
        self._assert_search_reads_values(
            records,
            "x_seat_name",
            [("<", "m"), (">", "a"), ("=", False), ("!=", "d"), ("!=", False)],
        )
