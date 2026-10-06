from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestWebsiteSaleAccessMatrix(AccessMatrixCase):
    personas = {
        "visitor": Persona(public=True),
        "portal_c": Persona(portal="customer_c"),
        "portal_d": Persona(portal="customer_d"),
        "employee_a": Persona(),
        "salesman_a": Persona("sale.group_sale_salesman"),
        "manager_a": Persona("sale.group_sale_manager"),
    }
    cells = (
        Cell(
            "product.pricelist",
            "pricelist_offered",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.pricelist",
            "pricelist_promotion",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.pricelist",
            "pricelist_negotiated_c",
            portal_c="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.pricelist",
            "pricelist_negotiated_d",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.pricelist.item",
            "item_offered",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.pricelist.item",
            "item_negotiated_c",
            portal_c="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.pricelist.item",
            "item_negotiated_d",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.attribute.custom.value",
            "custom_value_c",
            portal_c="r",
            employee_a="r",
            salesman_a="rwcd",
            manager_a="rwcd",
        ),
        Cell(
            "product.attribute.custom.value",
            "custom_value_d",
            portal_d="r",
            employee_a="r",
            salesman_a="rwcd",
            manager_a="rwcd",
        ),
        Cell(
            "account.fiscal.position",
            "fiscal_position",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "account.tax",
            "tax",
            visitor="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.attribute",
            "attribute",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.attribute.value",
            "attribute_value",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.category",
            "category",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.feed",
            "feed",
        ),
        Cell(
            "product.image",
            "image",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.public.category",
            "public_category",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.ribbon",
            "ribbon",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "product.tag",
            "tag",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.template",
            "template",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
            # marin makes sales managers price managers
            installed={"marin": {"manager_a": "w"}},
        ),
        Cell(
            "product.product",
            "product",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
            # marin makes sales managers price managers
            installed={"marin": {"manager_a": "w"}},
        ),
        Cell(
            "product.template.attribute.line",
            "template_attribute_line",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.template.attribute.value",
            "template_attribute_value",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "product.template.attribute.exclusion",
            "template_attribute_exclusion",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "uom.uom",
            "uom",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="r",
        ),
        Cell(
            "website.base.unit",
            "base_unit",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
        Cell(
            "website.checkout.step",
            "checkout_step",
        ),
        Cell(
            "website.sale.extra.field",
            "extra_field",
            visitor="r",
            portal_c="r",
            portal_d="r",
            employee_a="r",
            salesman_a="r",
            manager_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a = cls.companies["a"]
        customer_c, customer_d = cls.partners["customer_c"], cls.partners["customer_d"]
        # the partner's own pricelist exists only where pricelists are on
        env.ref("base.group_user").write(
            {
                "implied_ids": [
                    Command.link(env.ref("product.group_product_pricelist").id)
                ]
            }
        )
        pricelists = env["product.pricelist"].with_context(default_website_id=False)

        def pricelist(name, **values):
            return pricelists.create(
                {
                    "name": name,
                    "company_id": a.id,
                    "website_id": False,
                    "item_ids": [
                        Command.create({"compute_price": "fixed", "fixed_price": 1.0})
                    ],
                    **values,
                }
            )

        offered = pricelist("matrix offered", selectable=True)
        promotion = pricelist("matrix promotion", code="MATRIXCODE")
        negotiated_c = pricelist("matrix negotiated c")
        negotiated_d = pricelist("matrix negotiated d")
        customer_c.property_product_pricelist = negotiated_c
        customer_d.property_product_pricelist = negotiated_d

        attribute = env["product.attribute"].create(
            {
                "name": "matrix engraving",
                "value_ids": [Command.create({"name": "custom", "is_custom": True})],
            }
        )
        template = env["product.template"].create(
            {
                "name": "matrix product",
                "sale_ok": True,
                "website_published": True,
                "list_price": 10.0,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [Command.set(attribute.value_ids.ids)],
                        }
                    )
                ],
            }
        )
        product = template.product_variant_id
        ptav = template.attribute_line_ids.product_template_value_ids[:1]

        def custom_value(partner):
            order = env["sale.order"].create(
                {
                    "partner_id": partner.id,
                    "company_id": a.id,
                    "line_ids": [
                        Command.create({"product_id": product.id, "product_qty": 1})
                    ],
                }
            )
            return env["product.attribute.custom.value"].create(
                {
                    "custom_product_template_attribute_value_id": ptav.id,
                    "sale_order_line_id": order.line_ids.id,
                    "custom_value": f"for {partner.name}",
                }
            )

        def one(model, domain=()):
            found = (
                env[model].with_context(active_test=False).search(list(domain), limit=1)
            )
            assert found, f"no {model} to ask about"
            return found

        return {
            "pricelist_offered": offered,
            "pricelist_promotion": promotion,
            "pricelist_negotiated_c": negotiated_c,
            "pricelist_negotiated_d": negotiated_d,
            "item_offered": offered.item_ids,
            "item_negotiated_c": negotiated_c.item_ids,
            "item_negotiated_d": negotiated_d.item_ids,
            "custom_value_c": custom_value(customer_c),
            "custom_value_d": custom_value(customer_d),
            "fiscal_position": env["account.fiscal.position"].create(
                {"name": "matrix position", "company_id": a.id}
            ),
            "tax": one("account.tax", [("company_ids", "in", a.ids)]),
            "attribute": attribute,
            "attribute_value": attribute.value_ids,
            "category": one("product.category"),
            "feed": env["product.feed"].create(
                {"name": "matrix feed", "website_id": one("website").id}
            ),
            "image": env["product.image"].create(
                {"name": "matrix image", "product_tmpl_id": template.id}
            ),
            "public_category": env["product.public.category"].create(
                {"name": "matrix category"}
            ),
            "ribbon": env["product.ribbon"].create({"name": "matrix ribbon"}),
            "tag": env["product.tag"].create({"name": "matrix tag"}),
            "template": template,
            "product": product,
            "template_attribute_line": template.attribute_line_ids,
            "template_attribute_value": ptav,
            "template_attribute_exclusion": env[
                "product.template.attribute.exclusion"
            ].create(
                {
                    "product_tmpl_id": template.id,
                    "product_template_attribute_value_id": ptav.id,
                    "value_ids": [],
                }
            ),
            "uom": one("uom.uom"),
            "base_unit": env["website.base.unit"].create({"name": "matrix unit"}),
            "checkout_step": one("website.checkout.step"),
            "extra_field": env["website.sale.extra.field"].search([], limit=1)
            or env["website.sale.extra.field"].create(
                {"field_id": env["ir.model.fields"]._get("product.template", "name").id}
            ),
        }
