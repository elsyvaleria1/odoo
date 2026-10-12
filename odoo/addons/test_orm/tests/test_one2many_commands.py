from odoo import Command
from odoo.tests import TransactionCase


class TestOne2manyCommandsOnTheDatabase(TransactionCase):
    def test_an_unlink_after_a_set_detaches_the_line(self):
        foo = self.env["test_orm.related_foo"].create({"name": "foo"})
        line1, line2 = self.env["test_orm.related"].create(
            [{"name": "1"}, {"name": "2"}]
        )
        foo.write(
            {"foo_ids": [Command.set([line1.id, line2.id]), Command.unlink(line2.id)]}
        )
        self.env.invalidate_all()
        self.assertEqual(foo.foo_ids, line1)
        self.assertFalse(line2.foo_id)

    def test_a_delete_after_a_set_deletes_the_line(self):
        partner = self.env["res.partner"].create({"name": "p"})
        line1, line2 = self.env["test_orm.multi.line"].create(
            [{"name": "1"}, {"name": "2"}]
        )
        multi = self.env["test_orm.multi"].create({"partner": partner.id})
        multi.write(
            {"lines": [Command.set([line1.id, line2.id]), Command.delete(line2.id)]}
        )
        self.env.invalidate_all()
        self.assertEqual(multi.lines, line1)
        self.assertFalse(line2.exists())

    def test_a_set_names_the_model_of_a_many2one_reference_inverse(self):
        holder = self.env["test_orm.inverse_m2o_ref"].create({})
        refs = self.env["test_orm.model_many2one_reference"].create(
            [
                {"res_model": "res.partner", "res_id": 0},
                {"res_model": "res.partner", "res_id": 0},
            ]
        )
        holder.write({"model_ids": [Command.set(refs.ids)]})
        self.env.invalidate_all()
        self.assertEqual(
            {(ref.res_model, ref.res_id) for ref in refs},
            {("test_orm.inverse_m2o_ref", holder.id)},
        )
        self.assertEqual(holder.model_ids, refs)


class TestComputedOne2manyCommandList(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({"name": "Worker", "login": "worker"})

    def test_an_empty_command_list_assigns_an_empty_value(self):
        record = self.env["test_orm.compute.commands"].create({})
        self.assertFalse(record.linked_user_ids)
        self.assertEqual(record.read(["linked_user_ids"])[0]["linked_user_ids"], [])

    def test_an_empty_command_list_read_back_in_a_context_dependent_compute(self):
        record = self.env["test_orm.compute.commands"].create({})
        self.assertFalse(record.working_user_ids)
        self.assertFalse(record.last_working_user_id)
        self.env.invalidate_all()
        self.assertEqual(record.read(["working_user_ids"])[0]["working_user_ids"], [])

    def test_a_link_list_assigns_the_linked_records(self):
        record = self.env["test_orm.compute.commands"].create(
            {"user_ids": [Command.set(self.user.ids)]}
        )
        self.assertEqual(record.linked_user_ids, self.user)
        self.assertEqual(record.working_user_ids, self.user)
        self.assertEqual(record.last_working_user_id, self.user)

    def test_a_batch_mixing_empty_and_linked_values(self):
        empty, linked = self.env["test_orm.compute.commands"].create(
            [{}, {"user_ids": [Command.set(self.user.ids)]}]
        )
        self.env.invalidate_all()
        records = empty + linked
        self.assertEqual(
            [r["working_user_ids"] for r in records.read(["working_user_ids"])],
            [[], self.user.ids],
        )
        self.assertEqual(
            [r["linked_user_ids"] for r in records.read(["linked_user_ids"])],
            [[], self.user.ids],
        )

    def test_a_new_record_assigns_an_empty_value(self):
        record = self.env["test_orm.compute.commands"].new({})
        self.assertFalse(record.linked_user_ids)
        self.assertFalse(record.working_user_ids)
        self.assertFalse(record.watcher_ids)

    def test_a_many2many_gets_the_same_contract(self):
        empty, linked = self.env["test_orm.compute.commands"].create(
            [{}, {"user_ids": [Command.set(self.user.ids)]}]
        )
        self.env.invalidate_all()
        self.assertFalse(empty.watcher_ids)
        self.assertEqual(linked.watcher_ids, self.user)
