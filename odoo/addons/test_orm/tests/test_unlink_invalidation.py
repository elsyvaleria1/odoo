from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUnlinkInvalidation(TransactionCase):
    def test_deleted_records_leave_no_cached_values(self):
        discussion = self.env["test_orm.discussion"].create(
            {"name": "d", "participants": [(4, self.env.user.id)]}
        )
        message = self.env["test_orm.message"].create(
            {"discussion": discussion.id, "body": "b"}
        )
        self.env.flush_all()
        self.assertEqual(message.body, "b")
        message.unlink()
        self.assertFalse(message.exists())
        self.assertNotIn("body", message._cache)

    def test_a_cascaded_child_is_not_served_from_cache(self):
        discussion = self.env["test_orm.discussion"].create(
            {"name": "d", "participants": [(4, self.env.user.id)]}
        )
        message = self.env["test_orm.message"].create(
            {"discussion": discussion.id, "body": "b"}
        )
        self.env.flush_all()
        self.assertEqual(message.body, "b")
        discussion.unlink()
        self.assertFalse(message.exists())
        self.assertNotIn("body", message._cache)

    def test_a_one2many_drops_the_deleted_child(self):
        discussion = self.env["test_orm.discussion"].create(
            {"name": "d", "participants": [(4, self.env.user.id)]}
        )
        kept, removed = self.env["test_orm.message"].create(
            [
                {"discussion": discussion.id, "body": "kept"},
                {"discussion": discussion.id, "body": "removed"},
            ]
        )
        self.env.flush_all()
        self.assertEqual(discussion.messages, kept + removed)
        removed.unlink()
        self.assertEqual(discussion.messages, kept)

    def test_a_many2one_to_a_deleted_record_reads_as_empty(self):
        discussion = self.env["test_orm.discussion"].create(
            {"name": "d", "participants": [(4, self.env.user.id)]}
        )
        category = self.env["test_orm.category"].create({"name": "c"})
        child = self.env["test_orm.category"].create(
            {"name": "child", "parent": category.id}
        )
        self.env.flush_all()
        self.assertEqual(child.parent, category)
        self.assertTrue(discussion)
        category.unlink()
        self.assertFalse(child.exists())

    def test_an_unrelated_model_keeps_its_cache(self):
        discussion = self.env["test_orm.discussion"].create(
            {"name": "d", "participants": [(4, self.env.user.id)]}
        )
        message = self.env["test_orm.message"].create(
            {"discussion": discussion.id, "body": "b"}
        )
        currency = self.env["res.currency"].search([], limit=1)
        self.env.flush_all()
        self.assertTrue(currency.name)
        self.assertIn("name", currency._cache)
        message.unlink()
        self.assertIn(
            "name",
            currency._cache,
            "unlinking a model unrelated to res.currency must not drop its cache",
        )

    def test_a_many2many_drops_the_deleted_peer(self):
        category = self.env["test_orm.category"].create({"name": "c"})
        discussion = self.env["test_orm.discussion"].create(
            {
                "name": "d",
                "categories": [(6, 0, category.ids)],
                "participants": [(4, self.env.user.id)],
            }
        )
        self.env.flush_all()
        self.assertEqual(discussion.categories, category)
        category.unlink()
        self.assertFalse(discussion.categories)

    def test_a_deleted_record_is_not_recomputed_by_the_unlink_flush(self):
        order = self.env["test_orm.order"].create({})
        line = self.env["test_orm.order.line"].create(
            {"order_id": order.id, "product": "p"}
        )
        self.env.flush_all()
        OrderLine = type(line)
        compute = OrderLine._compute_has_been_rewarded
        computed_ids = []

        def spy(records):
            computed_ids.extend(records.ids)
            return compute(records)

        self.patch(OrderLine, "_compute_has_been_rewarded", spy)
        line.reward = True
        line.unlink()
        self.assertNotIn(line.id, computed_ids)
        self.assertFalse(line.exists())

    def test_a_compute_reading_a_deleted_record_waits_for_the_deletion(self):
        # the part's own weight is still pending when it is deleted, and its
        # recompute is dropped: the tally's compute, pending too, must not run
        # in the deletion's flush on the value that was never computed
        tally = self.env["test_orm.unlink_tally"].create({})
        self.env["test_orm.unlink_tally_part"].create({"tally_id": tally.id, "size": 1})
        self.env.flush_all()
        doomed = self.env["test_orm.unlink_tally_part"].create(
            {"tally_id": tally.id, "size": 5}
        )
        Tally = type(tally)
        compute = Tally._compute_total
        seen = []

        def spy(records):
            seen.extend(part.id for part in records.part_ids)
            return compute(records)

        self.patch(Tally, "_compute_total", spy)
        doomed.unlink()
        self.assertNotIn(doomed.id, seen)
        self.assertEqual(tally.total, 2)
