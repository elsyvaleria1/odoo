from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


def gelato_variants(*options):
    return {
        "description": "",
        "variants": [
            {
                "productUid": f"uid-{index}",
                "variantOptions": [
                    {"name": name, "value": value} for name, value in variant.items()
                ],
            }
            for index, variant in enumerate(options)
        ]
    }


@tagged("post_install", "-at_install")
class TestGelatoVariantSync(TransactionCase):
    def _uids(self, template):
        return sorted(template.product_variant_ids.mapped("gelato_product_uid"))

    def test_a_sync_builds_one_variant_per_gelato_variant(self):
        template = self.env["product.template"].create({"name": "Poster"})
        info = gelato_variants({"Gelato size": "S"}, {"Gelato size": "M"})

        template._create_attributes_from_gelato_info(info)
        self.assertEqual(self._uids(template), ["uid-0", "uid-1"])

        variants = template.product_variant_ids
        template._create_attributes_from_gelato_info(info)
        self.assertEqual(
            template.product_variant_ids, variants, "a second sync changes nothing"
        )

    def test_a_value_gelato_no_longer_offers_leaves_the_product(self):
        template = self.env["product.template"].create({"name": "Mug"})
        template._create_attributes_from_gelato_info(
            gelato_variants({"Gelato mug": "S"}, {"Gelato mug": "M"}, {"Gelato mug": "L"})
        )
        template._create_attributes_from_gelato_info(
            gelato_variants({"Gelato mug": "S"}, {"Gelato mug": "M"})
        )
        self.assertEqual(len(template.product_variant_ids), 2)
        self.assertTrue(all(template.product_variant_ids.mapped("gelato_product_uid")))

    def test_a_product_attribute_gelato_does_not_offer_is_refused(self):
        color = self.env["product.attribute"].create(
            {
                "name": "Gelato test color",
                "value_ids": [
                    Command.create({"name": "Red"}),
                    Command.create({"name": "Blue"}),
                ],
            }
        )
        template = self.env["product.template"].create(
            {
                "name": "Poster",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": color.id,
                            "value_ids": [Command.set(color.value_ids.ids)],
                        }
                    )
                ],
            }
        )
        variants = template.product_variant_ids

        with self.assertRaisesRegex(UserError, "Gelato test color"):
            template._create_attributes_from_gelato_info(
                gelato_variants({"Gelato size": "S"}, {"Gelato size": "M"})
            )
        self.assertEqual(template.product_variant_ids, variants)
        self.assertEqual(template.attribute_line_ids.attribute_id, color)

    def test_variants_with_different_options_are_refused(self):
        template = self.env["product.template"].create({"name": "Card"})
        with self.assertRaises(UserError):
            template._create_attributes_from_gelato_info(
                gelato_variants({"Gelato size": "S"}, {"Gelato paper": "Matte"})
            )
        self.assertEqual(len(template.product_variant_ids), 1)
