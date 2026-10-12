from odoo.fields import Command
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyRewardDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "loyalty.compute_all_discount_product_ids", "disabled"
        )
        cls.program = cls.env["loyalty.program"].create(
            {
                "name": "Domain program",
                "reward_ids": [Command.create({})],
            }
        )
        cls.reward = cls.program.reward_ids
        cls.reward.discount_applicability = "specific"
        cls.product = cls.env["product.product"].create(
            {"name": "Discounted", "type": "consu"}
        )

    def _serialized_domain(self):
        return json_loads(self.reward.reward_product_domain)

    def test_domain_follows_the_products(self):
        before = self._serialized_domain()
        self.reward.discount_product_ids = [Command.set(self.product.ids)]
        after = self._serialized_domain()

        self.assertNotEqual(before, after)
        self.assertIn(str(self.product.id), json_dumps(after))

    def test_domain_follows_the_category(self):
        category = self.env["product.category"].create({"name": "Discounted category"})
        before = self._serialized_domain()
        self.reward.discount_product_category_id = category
        after = self._serialized_domain()

        self.assertNotEqual(before, after)

    def test_domain_follows_the_tag(self):
        tag = self.env["product.tag"].create({"name": "Discounted tag"})
        before = self._serialized_domain()
        self.reward.discount_product_tag_id = tag
        after = self._serialized_domain()

        self.assertNotEqual(before, after)

    def test_the_domain_stays_evaluable_in_the_browser(self):
        parent = self.env["product.category"].create({"name": "Parent"})
        self.env["product.category"].create({"name": "Child", "parent_id": parent.id})
        self.reward.discount_product_category_id = parent

        serialized = json_dumps(self._serialized_domain())

        self.assertNotIn("child_of", serialized)
        self.assertNotIn("parent_of", serialized)

    def test_the_expanded_category_covers_every_descendant(self):
        root = self.env["product.category"].create({"name": "Root"})
        mid = self.env["product.category"].create({"name": "Mid", "parent_id": root.id})
        leaf = self.env["product.category"].create(
            {"name": "Leaf", "parent_id": mid.id}
        )
        deep_product = self.env["product.product"].create(
            {"name": "Deep", "type": "consu", "categ_id": leaf.id}
        )
        self.reward.discount_product_category_id = root

        matched = self.env["product.product"].search(
            self.reward._get_domain_discount_product()
        )

        self.assertIn(deep_product, matched)

    def test_only_one_representation_is_filled_in(self):
        Param = self.env["ir.config_parameter"].sudo()
        self.reward.discount_product_ids = [Command.set(self.product.ids)]

        Param.set_param("loyalty.compute_all_discount_product_ids", "enabled")
        self.reward.invalidate_recordset(
            ["all_discount_product_ids", "reward_product_domain"]
        )
        self.assertEqual(self.reward.all_discount_product_ids, self.product)
        self.assertEqual(self.reward.reward_product_domain, "null")

        Param.set_param("loyalty.compute_all_discount_product_ids", "disabled")
        self.reward.invalidate_recordset(
            ["all_discount_product_ids", "reward_product_domain"]
        )
        self.assertFalse(self.reward.all_discount_product_ids)
        self.assertNotEqual(self.reward.reward_product_domain, "null")

    def test_a_stale_domain_would_be_observable(self):
        field = self.reward._fields["reward_product_domain"]

        self._serialized_domain()
        self.assertTrue(
            self.env.cache.contains(self.reward, field),
            "reading the domain must cache it, or a stale read is impossible to see",
        )

        self.reward.discount_product_ids = [Command.set(self.product.ids)]
        self.assertFalse(
            self.env.cache.contains(self.reward, field),
            "writing a dependency must drop the cached domain",
        )

    def test_reward_product_uom_follows_the_reward_type(self):
        product_reward = self.env["loyalty.reward"].create(
            {
                "program_id": self.program.id,
                "reward_type": "product",
                "reward_product_id": self.product.id,
            }
        )
        self.assertTrue(product_reward.reward_product_uom_id)

        product_reward.reward_type = "discount"

        self.assertFalse(product_reward.reward_product_ids)
        self.assertFalse(product_reward.reward_product_uom_id)
