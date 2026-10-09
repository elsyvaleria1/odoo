from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGelatoVariantSync(TransactionCase):
    def test_a_sync_matching_no_variant_keeps_the_product(self):
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
        template._create_attributes_from_gelato_info(
            {
                "variants": [
                    {
                        "productUid": "uid-s",
                        "variantOptions": [{"name": "Gelato size", "value": "S"}],
                    },
                    {
                        "productUid": "uid-m",
                        "variantOptions": [{"name": "Gelato size", "value": "M"}],
                    },
                ]
            }
        )
        self.assertTrue(
            template.exists(),
            "removing the variants Gelato does not know is cleanup, not a"
            " request to delete the product",
        )
