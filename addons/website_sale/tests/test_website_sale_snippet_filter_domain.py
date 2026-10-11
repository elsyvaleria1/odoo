from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSnippetFilterSearchDomain(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].browse(1)
        cls.category = cls.env["product.public.category"].create({"name": "Probe"})
        cls.templates = cls.env["product.template"].create(
            [
                {
                    "name": f"Probe product {index}",
                    "is_published": True,
                    "sale_ok": True,
                    "public_categ_ids": [(6, 0, cls.category.ids)],
                    "standard_price": 3 + index * 10,
                }
                for index in range(3)
            ]
        )
        supplier = cls.env["res.partner"].create({"name": "Acme Secret Supplier"})
        cls.env["product.supplierinfo"].create(
            {"partner_id": supplier.id, "product_tmpl_id": cls.templates[0].id}
        )
        order = cls.env["sale.order"].create(
            {
                "partner_id": cls.env.ref("base.partner_admin").id,
                "website_id": cls.website.id,
                "company_id": cls.website.company_id.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": template.product_variant_id.id,
                            "product_qty": 1,
                        },
                    )
                    for template in cls.templates
                ],
            }
        )
        order.state = "done"

    def _fetch(self, xmlid, search_domain):
        response = self.url_open(
            "/website/snippet/filters",
            json={
                "params": {
                    "filter_id": self.env.ref(xmlid).id,
                    "template_key": "website_sale.dynamic_filter_template_product_product_products_item",
                    "limit": 16,
                    "search_domain": search_domain,
                }
            },
        ).json()
        return "error" if "error" in response else "".join(response["result"])

    def test_a_visitor_filters_only_on_what_a_visitor_reads(self):
        for xmlid in (
            "website_sale.dynamic_filter_latest_sold_products",
            "website_sale.dynamic_filter_newest_products",
        ):
            for search_domain in (
                [["standard_price", "<", 5]],
                [["seller_ids", "any", [["partner_id.name", "ilike", "Acme Secret"]]]],
                [["seller_ids.partner_id.name", "ilike", "Acme Secret"]],
            ):
                with self.subTest(filter=xmlid, domain=search_domain):
                    self.assertEqual(self._fetch(xmlid, search_domain), "error")

    def test_the_current_category_option_lists_its_products(self):
        for xmlid in (
            "website_sale.dynamic_filter_latest_sold_products",
            "website_sale.dynamic_filter_newest_products",
        ):
            with self.subTest(filter=xmlid):
                html = self._fetch(
                    xmlid,
                    [["public_categ_ids.product_tmpl_ids", "=", self.templates[0].id]],
                )
                self.assertIn("Probe product 0", html)
