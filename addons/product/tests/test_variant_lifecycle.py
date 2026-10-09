from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.product.models.utils import unlink_where_possible
from odoo.addons.product.tests.common import ProductVariantsCommon


@tagged("post_install", "-at_install")
class TestVariantUnlinkAndCopy(ProductVariantsCommon):
    def _template(self, name, values):
        return self.env["product.template"].create(
            {
                "name": name,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": values.attribute_id.id,
                            "value_ids": [Command.set(values.ids)],
                        }
                    )
                ],
            }
        )

    def test_unlinking_every_variant_at_once_removes_the_template(self):
        template = self._template(
            "Batch", self.color_attribute_red | self.color_attribute_blue
        )
        template.product_variant_ids.unlink()
        self.assertFalse(
            template.exists(),
            "a template whose every variant was deleted in one call must not"
            " survive with no variant at all",
        )

    def test_unlinking_some_variants_keeps_the_template(self):
        template = self._template(
            "Partial",
            self.color_attribute_red
            | self.color_attribute_blue
            | self.color_attribute_green,
        )
        template.product_variant_ids[:2].unlink()
        self.assertTrue(template.exists())
        self.assertEqual(len(template.product_variant_ids), 1)

    def test_copying_a_variant_returns_its_counterpart(self):
        copy = self.product_sofa_blue.copy()
        self.assertNotEqual(copy.product_tmpl_id, self.product_template_sofa)
        self.assertEqual(
            copy.product_template_attribute_value_ids.product_attribute_value_id,
            self.color_attribute_blue,
        )

    def test_copying_two_variants_of_one_template_copies_it_once(self):
        copies = (self.product_sofa_red | self.product_sofa_green).copy()
        self.assertEqual(len(copies), 2)
        self.assertEqual(len(copies.product_tmpl_id), 1)
        self.assertEqual(
            copies.product_template_attribute_value_ids.product_attribute_value_id,
            self.color_attribute_red | self.color_attribute_green,
        )


@tagged("post_install", "-at_install")
class TestParentExclusions(ProductVariantsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.accessory = cls.env["product.template"].create(
            {
                "name": "Cushion",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": cls.size_attribute.id,
                            "value_ids": [
                                Command.set(cls.size_attribute.value_ids.ids)
                            ],
                        }
                    )
                ],
            }
        )
        cls.red = cls.product_sofa_red.product_template_attribute_value_ids
        cls.accessory_ptav = {
            ptav.product_attribute_value_id: ptav
            for ptav in cls.accessory.attribute_line_ids.product_template_value_ids
        }

    def _exclude(self, template, values):
        self.env["product.template.attribute.exclusion"].create(
            {
                "product_template_attribute_value_id": self.red.id,
                "product_tmpl_id": template.id,
                "value_ids": [Command.set(values.ids)],
            }
        )

    def test_every_exclusion_row_of_a_parent_value_counts(self):
        small = self.accessory_ptav[self.size_attribute_s]
        medium = self.accessory_ptav[self.size_attribute_m]
        large = self.accessory_ptav[self.size_attribute_l]
        self._exclude(self.accessory, small)
        self._exclude(self.accessory, medium)

        self.assertEqual(
            set(self.accessory._get_parent_attribute_exclusions(self.red)[self.red.id]),
            {small.id, medium.id},
        )
        self.assertFalse(self.accessory._is_combination_possible(small, self.red))
        self.assertFalse(self.accessory._is_combination_possible(medium, self.red))
        self.assertTrue(self.accessory._is_combination_possible(large, self.red))

    def test_excluding_a_template_without_attributes_excludes_it(self):
        plain = self.env["product.template"].create({"name": "Plain"})
        self.assertTrue(
            list(plain._get_possible_combinations(parent_combination=self.red))
        )
        self._exclude(plain, self.env["product.template.attribute.value"])
        self.assertFalse(
            list(plain._get_possible_combinations(parent_combination=self.red)),
            "an exclusion with no value excludes the whole product, even one"
            " that has no attribute to exclude",
        )


@tagged("post_install", "-at_install")
class TestAttributeValueRehoming(ProductVariantsCommon):
    def test_a_value_on_an_archived_product_cannot_change_attribute(self):
        self.product_template_sofa.action_archive()
        with self.assertRaisesRegex(UserError, "Sofa"):
            self.color_attribute_red.attribute_id = self.size_attribute
        self.product_template_sofa.action_unarchive()
        self.assertEqual(
            self.product_template_sofa.attribute_line_ids.value_ids.attribute_id,
            self.color_attribute,
        )

    def test_an_unused_value_can_change_attribute(self):
        unused = self.env["product.attribute.value"].create(
            {"name": "teal", "attribute_id": self.color_attribute.id}
        )
        unused.attribute_id = self.size_attribute
        self.assertEqual(unused.attribute_id, self.size_attribute)


@tagged("post_install", "-at_install")
class TestPartnerSellerSelection(ProductVariantsCommon):
    def test_partner_ref_ignores_another_variants_seller(self):
        vendor = self.env["res.partner"].create({"name": "Vendor"})
        self.env["product.supplierinfo"].create(
            {
                "partner_id": vendor.id,
                "product_tmpl_id": self.product_template_sofa.id,
                "product_id": self.product_sofa_blue.id,
                "product_name": "Blue only",
                "product_code": "BLUE",
            }
        )
        red = self.product_sofa_red.with_context(partner_id=vendor.id)
        blue = self.product_sofa_blue.with_context(partner_id=vendor.id)
        self.assertNotIn("Blue only", red.partner_ref)
        self.assertFalse(red.code)
        self.assertEqual(blue.partner_ref, "[BLUE] Blue only")
        self.assertEqual(blue.code, "BLUE")

    def test_a_variant_seller_wins_over_a_template_seller(self):
        vendor = self.env["res.partner"].create({"name": "Vendor"})
        self.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": vendor.id,
                    "product_tmpl_id": self.product_template_sofa.id,
                    "product_code": "ANY",
                },
                {
                    "partner_id": vendor.id,
                    "product_tmpl_id": self.product_template_sofa.id,
                    "product_id": self.product_sofa_red.id,
                    "product_code": "RED",
                },
            ]
        )
        self.assertEqual(
            self.product_sofa_red.with_context(partner_id=vendor.id).code, "RED"
        )
        self.assertEqual(
            self.product_sofa_green.with_context(partner_id=vendor.id).code, "ANY"
        )


@tagged("post_install", "-at_install")
class TestUnlinkWherePossibleFaults(ProductVariantsCommon):
    def test_user_faults_are_reported_back_as_undeletable(self):
        def refuse(records):
            raise UserError("refused")

        self.assertEqual(
            unlink_where_possible(self.product_sofa_red, refuse),
            self.product_sofa_red,
        )

    def test_programming_errors_propagate(self):
        def broken(records):
            raise AttributeError("a bug, not a reason to archive")

        with self.assertRaises(AttributeError):
            unlink_where_possible(self.product_sofa_red, broken)
