from datetime import timedelta

from odoo.fields import Command, Date
from odoo.tests.common import TransactionCase, new_test_user


class TestOne2manyClearArchived(TransactionCase):
    def _create_family(self):
        Category = self.env["res.partner.tag"]
        parent = Category.create({"name": "parent"})
        active = Category.create({"name": "active child", "parent_id": parent.id})
        archived = Category.create(
            {"name": "archived child", "parent_id": parent.id, "active": False}
        )
        self.env.flush_all()
        return parent, active, archived

    def test_clear_detaches_archived_lines(self):
        parent, active, archived = self._create_family()
        parent.write({"child_ids": [Command.clear()]})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertFalse(active.exists(), "active line is removed by CLEAR")
        remaining = archived.exists()
        if remaining:
            self.assertFalse(
                remaining.parent_id,
                "archived line must be detached by CLEAR like an active one",
            )

    def test_set_detaches_archived_lines(self):
        parent, _active, archived = self._create_family()
        keeper = self.env["res.partner.tag"].create(
            {"name": "keeper", "parent_id": parent.id}
        )
        parent.write({"child_ids": [Command.set(keeper.ids)]})
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(keeper.parent_id, parent)
        remaining = archived.exists()
        if remaining:
            self.assertFalse(
                remaining.parent_id,
                "archived line must be detached by SET like an active one",
            )


class TestCompanyDependentInsertFallback(TransactionCase):
    def test_create_with_user_scoped_default_round_trips(self):
        user = new_test_user(self.env, "audit_cd_user", groups="base.group_system")
        IrDefault = self.env["ir.default"]
        IrDefault.set("test_orm.company", "foo", "GLOBAL")
        IrDefault.set("test_orm.company", "foo", "USERVAL", user_id=user.id)
        self.env.flush_all()
        self.env.registry.clear_cache()

        record = self.env["test_orm.company"].with_user(user).create({"foo": "USERVAL"})
        self.env.flush_all()
        self.env.invalidate_all()

        self.assertEqual(
            record.with_user(user).foo,
            "USERVAL",
            "the creating user must read back the value they wrote",
        )
        self.assertEqual(
            record.foo,
            "USERVAL",
            "other users must see the written value, not the global default",
        )
        self.env.cr.execute(
            "SELECT foo FROM test_orm_company WHERE id = %s", [record.id]
        )
        self.assertIsNotNone(self.env.cr.fetchone()[0])

    def test_create_matching_superuser_fallback_stores_null(self):
        IrDefault = self.env["ir.default"]
        IrDefault.set("test_orm.company", "foo", "GLOBAL")
        self.env.flush_all()
        self.env.registry.clear_cache()
        record = self.env["test_orm.company"].create({"foo": "GLOBAL"})
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT foo FROM test_orm_company WHERE id = %s", [record.id]
        )
        self.assertIsNone(self.env.cr.fetchone()[0])
        self.env.invalidate_all()
        self.assertEqual(record.foo, "GLOBAL")


class TestDefaultFieldCache(TransactionCase):
    def test_cached_defaults_keep_given_and_requested_fields_separate(self):
        partner = self.env["res.partner"].with_context(
            default_city="Default city", default_street="Default street"
        )
        cache = {}
        first = partner._prepare_values_with_defaults(
            {"city": "Given city"},
            _missing_defaults_cache=cache,
            only=["city", "street"],
        )
        second = partner._prepare_values_with_defaults(
            {"street": "Given street"},
            _missing_defaults_cache=cache,
            only=["city", "street"],
        )
        self.assertEqual(first, {"city": "Given city", "street": "Default street"})
        self.assertEqual(second, {"city": "Default city", "street": "Given street"})

    def test_cached_defaults_preserve_requested_field_order(self):
        partner = self.env["res.partner"]
        requested = []

        def default_get(records, fields):
            requested.append(list(fields))
            return {}

        self.patch(type(partner), "default_get", default_get)
        cache = {}
        for names in (["city", "street"], ["street", "city"]):
            partner._prepare_values_with_defaults(
                {}, _missing_defaults_cache=cache, only=names
            )
        self.assertEqual(requested, [["city", "street"], ["street", "city"]])

    def test_cached_field_selection_reads_default_values_from_each_environment(self):
        cache = {}
        for city in ("First city", "Second city"):
            partner = self.env["res.partner"].with_context(default_city=city)
            values = {"street": False}
            prepared = partner._prepare_values_with_defaults(
                values, _missing_defaults_cache=cache, only=["city", "street"]
            )
            self.assertEqual(prepared, {"city": city, "street": False})
            self.assertEqual(values, {"street": False})
            self.assertIsNot(prepared, values)


class TestDatetimeEqualsDate(TransactionCase):
    def test_equals_date_matches_whole_day(self):
        record = self.env["test_orm.mixed"].create({})
        self.env.flush_all()
        Model = self.env["test_orm.mixed"]
        today = Date.context_today(record, record.create_date)
        whole_day = Model.search_count(
            [
                "&",
                ("create_date", ">=", today),
                ("create_date", "<", today + timedelta(days=1)),
                ("id", "=", record.id),
            ]
        )
        self.assertEqual(whole_day, 1)
        self.assertEqual(
            Model.search_count([("create_date", "=", today), ("id", "=", record.id)]),
            1,
            "'=' with a date must cover the whole day",
        )
        self.assertEqual(
            Model.search_count([("create_date", "=", "today"), ("id", "=", record.id)]),
            1,
            "'=' with 'today' must cover the whole day",
        )
        self.assertEqual(
            Model.search_count([("create_date", "!=", today), ("id", "=", record.id)]),
            0,
            "'!=' with a date is the complement of the whole day",
        )
