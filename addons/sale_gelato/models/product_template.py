from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_gelato import utils

_debug = DebugLog(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    gelato_template_ref = fields.Char(
        string="Gelato Template Reference",
        help="Synchronize to fetch variants from Gelato",
    )
    gelato_product_uid = fields.Char(
        string="Gelato Product UID",
        compute="_compute_gelato_product_uid",
        inverse="_inverse_gelato_product_uid",
        readonly=True,
    )
    gelato_image_ids = fields.One2many(
        comodel_name="document.document",
        inverse_name="res_id",
        string="Gelato Print Images",
        readonly=True,
        domain=[("is_gelato", "=", True)],
    )
    gelato_missing_images = fields.Boolean(
        string="Missing Print Images",
        compute="_compute_gelato_missing_images",
    )

    @api.depends("product_variant_ids.gelato_product_uid")
    def _compute_gelato_product_uid(self) -> None:
        self._compute_template_field_from_variant_field("gelato_product_uid")

    def _inverse_gelato_product_uid(self) -> None:
        self._set_product_variant_field("gelato_product_uid")

    @api.depends("gelato_image_ids")
    def _compute_gelato_missing_images(self) -> None:
        for product in self:
            product.gelato_missing_images = any(
                not image.datas for image in product.gelato_image_ids
            )

    def action_sync_gelato_template_info(self):
        try:
            endpoint = f"templates/{self.gelato_template_ref}"
            template_info = utils.send_request(
                self.env.company.sudo().gelato_api_key,
                "ecommerce",
                "v1",
                endpoint,
                method="GET",
            )
        except UserError as e:
            _debug.logic("gelato_template_sync_failed", template=self, error=str(e))
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger",
                    "title": self.env._("Could not synchronize with Gelato"),
                    "message": str(e),
                    "sticky": True,
                },
            }

        _debug.pipeline(
            "gelato_template_synced",
            template=self,
            variants=len(template_info["variants"]),
        )
        self._create_attributes_from_gelato_info(template_info)
        self._create_print_images_from_gelato_info(template_info)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": self.env._("Successfully synchronized with Gelato"),
                "message": self.env._(
                    "Missing product variants and images have been successfully created."
                ),
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def _create_attributes_from_gelato_info(self, template_info):
        self.check_singleton()
        gelato_variants = template_info["variants"]
        if len(gelato_variants) == 1:
            _debug.logic("gelato_single_variant", template=self)
            self.gelato_product_uid = gelato_variants[0]["productUid"]
            return
        options_by_uid = self._plan_gelato_variants(gelato_variants)
        values_by_uid = self._ensure_gelato_attribute_values(options_by_uid)
        self._assign_gelato_variants(values_by_uid)

    def _plan_gelato_variants(self, gelato_variants) -> dict:
        options_by_uid = {}
        option_names = None
        for variant_data in gelato_variants:
            options = {
                option["name"]: option["value"]
                for option in variant_data["variantOptions"]
            }
            if len(options) != len(variant_data["variantOptions"]) or (
                option_names is not None and set(options) != option_names
            ):
                raise UserError(
                    self.env._(
                        "Gelato describes the variant %s with options that differ from"
                        " the other variants of the template.",
                        variant_data["productUid"],
                    )
                )
            option_names = set(options)
            options_by_uid[variant_data["productUid"]] = options
        combinations = [
            frozenset(options.items()) for options in options_by_uid.values()
        ]
        if len(set(combinations)) != len(combinations):
            raise UserError(
                self.env._("Gelato describes two variants with the same options.")
            )

        variant_attributes = self.valid_product_template_attribute_line_ids._without_no_variant_attributes().attribute_id
        not_offered = variant_attributes.filtered(
            lambda attribute: attribute.name not in option_names
        )
        if not_offered:
            raise UserError(
                self.env._(
                    "%(attributes)s is on %(product)s but Gelato does not offer it, so"
                    " no variant can match Gelato's. Remove it from the product, or"
                    " make it not create variants, then synchronize again.",
                    attributes=", ".join(not_offered.mapped("name")),
                    product=self.display_name,
                )
            )
        specified = self.specification_line_ids.attribute_id.filtered(
            lambda attribute: attribute.name in option_names
        )
        if specified:
            raise UserError(
                self.env._(
                    "%(attributes)s is a specification of %(product)s, while Gelato"
                    " makes variants of it.",
                    attributes=", ".join(specified.mapped("name")),
                    product=self.display_name,
                )
            )
        not_always = variant_attributes.filtered(
            lambda attribute: attribute.create_variant != "always"
        )
        if not_always:
            raise UserError(
                self.env._(
                    "%(attributes)s must create its variants instantly to be"
                    " synchronized with Gelato.",
                    attributes=", ".join(not_always.mapped("name")),
                )
            )
        return options_by_uid

    def _ensure_gelato_attribute_values(self, options_by_uid) -> dict:
        Attribute = self.env["product.attribute"]
        Value = self.env["product.attribute.value"]
        values_by_name = {}
        for options in options_by_uid.values():
            for name, value in options.items():
                values_by_name.setdefault(name, set()).add(value)

        lines_by_name = {
            line.attribute_id.name: line
            for line in self.valid_product_template_attribute_line_ids._without_no_variant_attributes()
        }
        attributes = {name: line.attribute_id for name, line in lines_by_name.items()}
        for attribute in Attribute.search(
            [
                (
                    "name",
                    "in",
                    [name for name in values_by_name if name not in attributes],
                ),
                ("create_variant", "=", "always"),
            ]
        ):
            attributes.setdefault(attribute.name, attribute)
        missing = [name for name in values_by_name if name not in attributes]
        for attribute in Attribute.create([{"name": name} for name in missing]):
            attributes[attribute.name] = attribute

        value_by_key = {
            (value.attribute_id.name, value.name): value
            for value in Value.search(
                [
                    (
                        "attribute_id",
                        "in",
                        [attribute.id for attribute in attributes.values()],
                    )
                ]
            )
        }
        missing = [
            {"name": value, "attribute_id": attributes[name].id}
            for name, values in values_by_name.items()
            for value in sorted(values)
            if (name, value) not in value_by_key
        ]
        for value in Value.create(missing):
            value_by_key[value.attribute_id.name, value.name] = value

        line_commands = []
        for name, values in values_by_name.items():
            wanted = Value.concat(
                *(value_by_key[name, value] for value in sorted(values))
            )
            line = lines_by_name.get(name)
            if not line:
                line_commands.append(
                    Command.create(
                        {
                            "attribute_id": attributes[name].id,
                            "value_ids": [Command.set(wanted.ids)],
                        }
                    )
                )
            elif wanted - line.value_ids:
                line_commands.append(
                    Command.update(
                        line.id,
                        {
                            "value_ids": [
                                Command.link(value.id)
                                for value in wanted - line.value_ids
                            ]
                        },
                    )
                )
        if line_commands:
            self.write({"attribute_line_ids": line_commands})

        return {
            uid: Value.concat(
                *(value_by_key[name, value] for name, value in options.items())
            )
            for uid, options in options_by_uid.items()
        }

    def _assign_gelato_variants(self, values_by_uid) -> None:
        variant_by_values = {
            frozenset(
                variant.product_template_attribute_value_ids.product_attribute_value_id.ids
            ): variant
            for variant in self.product_variant_ids
        }
        unmatched = [
            uid
            for uid, values in values_by_uid.items()
            if frozenset(values.ids) not in variant_by_values
        ]
        if unmatched:
            raise UserError(
                self.env._(
                    "Gelato's variants %(variants)s have no counterpart on %(product)s;"
                    " an exclusion on the product may forbid them.",
                    variants=", ".join(unmatched),
                    product=self.display_name,
                )
            )
        synced = self.env["product.product"]
        for uid, values in values_by_uid.items():
            variant = variant_by_values[frozenset(values.ids)]
            variant.gelato_product_uid = uid
            synced |= variant
        (self.product_variant_ids - synced)._unlink_or_archive()

    def _create_print_images_from_gelato_info(self, template_info) -> None:
        for print_image_data in template_info["variants"][0]["imagePlaceholders"]:
            if print_image_data["printArea"].lower() in ("1", "front"):
                print_image_data["printArea"] = "default"

            print_image_found = bool(
                self.env["document.document"].search_count(  # noqa: E8507 - one lookup per Gelato attribute; the record may have been created by an earlier pass
                    [
                        ("name", "ilike", print_image_data["printArea"]),
                        ("res_id", "=", self.id),
                        ("res_model", "=", "product.template"),
                        (
                            "is_gelato",
                            "=",
                            True,
                        ),
                    ],
                    limit=1,
                )
            )
            if not print_image_found:
                self.gelato_image_ids = [
                    Command.create(
                        {
                            "name": print_image_data["printArea"].lower(),
                            "res_id": self.id,
                            "res_model": "product.template",
                            "is_gelato": True,
                        }
                    )
                ]

    def _get_related_fields_variant_template(self):
        return super()._get_related_fields_variant_template() + ["gelato_product_uid"]

    def _get_domain_product_document(self):
        return super()._get_domain_product_document() & Domain("is_gelato", "=", False)
