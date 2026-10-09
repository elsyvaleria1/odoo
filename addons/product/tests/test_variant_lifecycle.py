import importlib.util

from psycopg.errors import UniqueViolation

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.misc import file_path

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


@tagged("post_install", "-at_install")
class TestVariantRebuildAndChecks(ProductVariantsCommon):
    def _count_rebuilds(self):
        Template = type(self.env["product.template"])
        original = Template._create_variant_ids
        calls = []

        def counting(templates):
            if templates:
                calls.append(templates.ids)
            return original(templates)

        self.patch(Template, "_create_variant_ids", counting)
        return calls

    def test_a_template_save_rebuilds_its_variants_once(self):
        calls = self._count_rebuilds()
        template = self.env["product.template"].create(
            {
                "name": "Once",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.color_attribute.id,
                            "value_ids": [
                                Command.set(self.color_attribute.value_ids.ids)
                            ],
                        }
                    )
                ],
            }
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(template.product_variant_ids), 3)

        calls.clear()
        template.write(
            {
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.size_attribute.id,
                            "value_ids": [
                                Command.set(self.size_attribute.value_ids.ids)
                            ],
                        }
                    )
                ]
            }
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(template.product_variant_ids), 9)

    def test_enumeration_agrees_with_the_single_check(self):
        template = self.env["product.template"].create(
            {
                "name": "Grid",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [Command.set(attribute.value_ids.ids)],
                        }
                    )
                    for attribute in (self.color_attribute, self.size_attribute)
                ],
            }
        )
        red = template.attribute_line_ids[0].product_template_value_ids[0]
        small = template.attribute_line_ids[1].product_template_value_ids[0]
        red.write(
            {
                "exclude_for": [
                    Command.create(
                        {
                            "product_tmpl_id": template.id,
                            "value_ids": [Command.set(small.ids)],
                        }
                    )
                ]
            }
        )
        enumerated = list(template._get_possible_combinations())
        self.assertEqual(len(enumerated), 8)
        self.assertNotIn(red | small, enumerated)
        self.assertTrue(all(template._is_combination_possible(c) for c in enumerated))
        self.assertEqual(
            template._get_possible_variants(),
            template.product_variant_ids.filtered(lambda v: v._is_variant_possible()),
        )

    def test_an_attribute_on_an_archived_product_cannot_be_deleted(self):
        self.product_template_sofa.action_archive()
        with self.assertRaisesRegex(UserError, "Sofa"):
            self.color_attribute.unlink()

    def test_the_template_count_counts_active_templates(self):
        chair = self.env["product.template"].create(
            {
                "name": "Chair",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.color_attribute.id,
                            "value_ids": [Command.set(self.color_attribute_red.ids)],
                        }
                    )
                ],
            }
        )
        self.assertEqual(self.color_attribute.count_product_tmpl, 2)
        chair.action_archive()
        self.color_attribute.invalidate_recordset(["count_product_tmpl"])
        self.assertEqual(self.color_attribute.count_product_tmpl, 1)

    def test_an_attribute_sits_on_one_line_per_product(self):
        with mute_logger("odoo.db"), self.assertRaises(UniqueViolation):
            self.env["product.template.attribute.line"].create(
                {
                    "product_tmpl_id": self.product_template_sofa.id,
                    "attribute_id": self.color_attribute.id,
                    "value_ids": [Command.set(self.color_attribute_red.ids)],
                }
            )
            self.env.flush_all()

    def test_a_line_can_be_replaced_in_one_save(self):
        old_line = self.product_template_sofa.attribute_line_ids
        self.product_template_sofa.write(
            {
                "attribute_line_ids": [
                    Command.delete(old_line.id),
                    Command.create(
                        {
                            "attribute_id": self.color_attribute.id,
                            "value_ids": [Command.set(self.color_attribute_blue.ids)],
                        }
                    ),
                ]
            }
        )
        self.assertEqual(
            self.product_template_sofa.attribute_line_ids.value_ids,
            self.color_attribute_blue,
        )

    def test_product_attributes_stay_multi_valued(self):
        unused = self.env["product.attribute"].create({"name": "Unused"})
        with self.assertRaises(ValidationError):
            unused.value_type = "single"

    def test_a_template_value_name_follows_show_attribute(self):
        ptav = self.product_sofa_red.product_template_attribute_value_ids
        self.assertEqual(ptav.display_name, "Color: red")
        self.assertEqual(ptav.with_context(show_attribute=False).display_name, "red")


@tagged("post_install", "-at_install")
class TestSpecificationLines(ProductVariantsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grapes = cls.env["product.attribute"].create(
            {
                "name": "Grapes",
                "value_ids": [
                    Command.create({"name": "Merlot"}),
                    Command.create({"name": "Malbec"}),
                ],
            }
        )

    def _wine(self, **values):
        return self.env["product.template"].create(
            {
                "name": "Wine",
                "specification_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.grapes.id,
                            "value_ids": [Command.set(self.grapes.value_ids.ids)],
                        }
                    )
                ],
                **values,
            }
        )

    def test_a_specification_describes_without_varying(self):
        wine = self._wine()
        line = wine.specification_line_ids
        self.assertEqual(line.purpose, "specification")
        self.assertFalse(wine.attribute_line_ids)
        self.assertEqual(len(wine.product_variant_ids), 1)
        self.assertFalse(line.product_template_value_ids)
        self.assertFalse(wine.has_configurable_attributes)
        self.assertEqual(wine._get_attribute_lines_for_display(), line)
        self.assertEqual(
            wine.product_variant_id._get_attribute_lines_for_display(), line
        )

    def test_specifications_sit_beside_variant_lines(self):
        wine = self._wine(
            attribute_line_ids=[
                Command.create(
                    {
                        "attribute_id": self.size_attribute.id,
                        "value_ids": [Command.set(self.size_attribute.value_ids.ids)],
                    }
                )
            ]
        )
        self.assertEqual(len(wine.product_variant_ids), 3)
        self.assertEqual(
            wine.product_variant_ids.product_template_attribute_value_ids.attribute_id,
            self.size_attribute,
        )

    def test_an_attribute_is_a_variant_or_a_specification_not_both(self):
        wine = self._wine()
        with mute_logger("odoo.db"), self.assertRaises(UniqueViolation):
            wine.write(
                {
                    "attribute_line_ids": [
                        Command.create(
                            {
                                "attribute_id": self.grapes.id,
                                "value_ids": [Command.set(self.grapes.value_ids.ids)],
                            }
                        )
                    ]
                }
            )
            self.env.flush_all()

    def test_turning_a_variant_line_into_a_specification_drops_the_dimension(self):
        template = self.product_template_sofa
        self.assertEqual(len(template.product_variant_ids), 3)
        template.attribute_line_ids.purpose = "specification"
        self.assertEqual(len(template.product_variant_ids), 1)
        self.assertFalse(
            template.product_variant_ids.product_template_attribute_value_ids
        )
        self.assertEqual(
            template.specification_line_ids.value_ids, self.color_attribute.value_ids
        )

        template.specification_line_ids.purpose = "variant"
        self.assertEqual(len(template.product_variant_ids), 3)


@tagged("post_install", "-at_install")
class TestSpecificationMigration(ProductVariantsCommon):
    def _migrate(self):
        spec = importlib.util.spec_from_file_location(
            "product_pre_migrate_1_12",
            file_path("product/migrations/1.12/pre-migrate.py"),
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.env.flush_all()
        migration.migrate(self.env.cr, "1.11")
        self.env.invalidate_all()

    def _repeat_line(self, template, values):
        self.env.cr.execute(
            "DROP INDEX product_template_attribute_line_attribute_unique_per_product"
        )
        for value in values:
            self.env.cr.execute(
                """
                INSERT INTO product_template_attribute_line
                       (product_tmpl_id, attribute_id, active, sequence, purpose)
                VALUES (%s, %s, true, 20, 'variant') RETURNING id
                """,
                [template.id, value.attribute_id.id],
            )
            (line_id,) = self.env.cr.fetchone()
            self.env.cr.execute(
                """
                INSERT INTO product_attribute_value_product_template_attribute_line_rel
                       (product_template_attribute_line_id, product_attribute_value_id)
                VALUES (%s, %s)
                """,
                [line_id, value.id],
            )

    def test_repeated_single_value_lines_become_one_specification(self):
        template = self.env["product.template"].create(
            {
                "name": "Margaux",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.size_attribute.id,
                            "value_ids": [Command.set(self.size_attribute_s.ids)],
                        }
                    )
                ],
            }
        )
        variant = template.product_variant_id
        self.assertTrue(variant.product_template_attribute_value_ids)
        self._repeat_line(template, self.size_attribute_m | self.size_attribute_l)

        self._migrate()

        self.assertFalse(template.attribute_line_ids)
        self.assertEqual(
            template.specification_line_ids.value_ids, self.size_attribute.value_ids
        )
        self.assertFalse(variant.product_template_attribute_value_ids)
        self.assertEqual(variant.combination_indices, "")

    def test_a_repeated_line_of_several_values_stops_the_upgrade(self):
        self._repeat_line(self.product_template_sofa, self.color_attribute_red)
        with self.assertRaisesRegex(
            UserError, "product.template %s" % self.product_template_sofa.id
        ):
            self._migrate()
