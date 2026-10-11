from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain


class LoyaltyProgram(models.Model):
    _name = "loyalty.program"
    _description = "Loyalty Program"
    _order = "sequence"
    _rec_name = "name"

    _PAYMENT_PROGRAM_TYPES = ("gift_card", "ewallet")
    _TYPE_DEFAULT_CHILDREN = ("rule_ids", "reward_ids", "communication_plan_ids")

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        program_type = defaults.get("program_type")
        if program_type:
            program_default_values = self._program_type_default_values()
            if program_type in program_default_values:
                default_values = program_default_values[program_type]
                defaults.update(
                    {k: v for k, v in default_values.items() if k in fields}
                )
        return defaults

    name = fields.Char(
        string="Program Name",
        translate=True,
        required=True,
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(copy=False)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    currency_symbol = fields.Char(related="currency_id.symbol")
    pricelist_ids = fields.Many2many(
        comodel_name="product.pricelist",
        domain="[('currency_id', '=', currency_id)]",
        help="This program is specific to this pricelist set.",
    )

    total_order_count = fields.Integer(compute="_compute_total_order_count")

    rule_ids = fields.One2many(
        comodel_name="loyalty.rule",
        inverse_name="program_id",
        string="Conditional rules",
        compute="_compute_from_program_type",
        store=True,
        copy=True,
        readonly=False,
    )
    reward_ids = fields.One2many(
        comodel_name="loyalty.reward",
        inverse_name="program_id",
        string="Rewards",
        compute="_compute_from_program_type",
        store=True,
        copy=True,
        readonly=False,
    )
    communication_plan_ids = fields.One2many(
        comodel_name="loyalty.mail",
        inverse_name="program_id",
        compute="_compute_from_program_type",
        store=True,
        copy=True,
        readonly=False,
    )

    mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Email template",
        compute="_compute_mail_template_id",
        inverse="_inverse_mail_template_id",
        readonly=False,
    )
    trigger_product_ids = fields.Many2many(
        related="rule_ids.product_ids",
        readonly=False,
    )

    coupon_ids = fields.One2many(
        comodel_name="loyalty.card",
        inverse_name="program_id",
    )
    coupon_count = fields.Integer(compute="_compute_coupon_count")
    coupon_count_label = fields.Char(
        string="Items Name",
        compute="_compute_coupon_count_label",
        help="What this program's cards are called: coupons, gift cards, eWallets...",
    )
    coupon_count_display = fields.Char(
        string="Items",
        compute="_compute_coupon_count_display",
    )

    program_type = fields.Selection(
        selection=[
            ("coupons", "Coupons"),
            ("gift_card", "Gift Card"),
            ("loyalty", "Loyalty Cards"),
            ("promotion", "Promotions"),
            ("ewallet", "eWallet"),
            ("promo_code", "Discount Code"),
            ("buy_x_get_y", "Buy X Get Y"),
            ("next_order_coupons", "Next Order Coupons"),
        ],
        default="promotion",
        required=True,
    )
    date_from = fields.Date(
        string="Start Date",
        help="The start date is included in the validity period of this program",
    )
    date_to = fields.Date(
        string="End date",
        help="The end date is included in the validity period of this program",
    )
    limit_usage = fields.Boolean()
    max_usage = fields.Integer()
    applies_on = fields.Selection(
        selection=[
            ("current", "Current order"),
            ("future", "Future orders"),
            ("both", "Current & Future orders"),
        ],
        compute="_compute_from_program_type",
        default="current",
        store=True,
        readonly=False,
        required=True,
    )
    trigger = fields.Selection(
        selection=[("auto", "Automatic"), ("with_code", "Use a code")],
        compute="_compute_from_program_type",
        store=True,
        readonly=False,
        help="""
        Automatic: Customers will be eligible for a reward automatically in their cart.
        Use a code: Customers will be eligible for a reward if they enter a code.
        """,
    )
    portal_visible = fields.Boolean(
        default=False,
        help="""
        Show in web portal, PoS customer ticket, eCommerce checkout, the number of points available
         and used by reward.
        """,
    )
    portal_point_name = fields.Char(
        translate=True,
        compute="_compute_portal_point_name",
        store=True,
        readonly=False,
    )
    is_nominative = fields.Boolean(
        compute="_compute_is_nominative",
        search="_search_is_nominative",
        help="Whether this program's points accumulate on a card held by a customer,"
        " rather than being spent on the order that earned them.",
    )
    is_payment_program = fields.Boolean(compute="_compute_is_payment_program")

    payment_program_discount_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Discount Product",
        compute="_compute_payment_program_discount_product_id",
        readonly=True,
        help="Product used in the sales order to apply the discount.",
    )

    available_on = fields.Boolean(
        store=False,
        help="Manage where your program should be available for use.",
    )

    _check_max_usage = models.Constraint(
        "CHECK (limit_usage = False OR max_usage > 0)",
        "Max usage must be strictly positive if a limit is used.",
    )

    @api.constrains("currency_id", "pricelist_ids")
    def _check_pricelist_currency(self) -> None:
        if any(
            pricelist.currency_id != program.currency_id
            for program in self
            for pricelist in program.pricelist_ids
        ):
            raise ValidationError(
                self.env._(
                    "The loyalty program's currency must be the same as all its pricelists' ones."
                )
            )

    @api.constrains("date_from", "date_to")
    def _check_date_from_date_to(self) -> None:
        if any(p.date_to and p.date_from and p.date_from > p.date_to for p in self):
            raise ValidationError(
                self.env._(
                    "The validity period's start date must be anterior or equal to its end date."
                )
            )

    @api.constrains("reward_ids")
    def _check_reward_ids(self) -> None:
        if self.env.context.get("loyalty_skip_reward_check"):
            return
        if any(not program.reward_ids for program in self):
            raise ValidationError(
                self.env._("A program must have at least one reward.")
            )

    def _compute_total_order_count(self) -> None:
        self.total_order_count = 0

    @api.depends("program_type")
    def _compute_coupon_count_label(self) -> None:
        program_items_name = self._program_items_name()
        for program in self:
            program.coupon_count_label = (
                program_items_name.get(program.program_type) or ""
            )

    @api.depends("coupon_count", "coupon_count_label")
    def _compute_coupon_count_display(self) -> None:
        for program in self:
            program.coupon_count_display = (
                f"{program.coupon_count or 0} {program.coupon_count_label}"
            )

    @api.depends("communication_plan_ids.mail_template_id")
    def _compute_mail_template_id(self) -> None:
        for program in self:
            program.mail_template_id = program.communication_plan_ids.mail_template_id[
                :1
            ]

    def _inverse_mail_template_id(self) -> None:
        for program in self:
            if program.program_type not in self._PAYMENT_PROGRAM_TYPES:
                continue
            if not program.mail_template_id:
                program.communication_plan_ids = [Command.clear()]
            elif not program.communication_plan_ids:
                program.communication_plan_ids = self.env["loyalty.mail"].create(
                    {
                        "program_id": program.id,
                        "trigger": "create",
                        "mail_template_id": program.mail_template_id.id,
                    }
                )
            else:
                program.communication_plan_ids.write(
                    {
                        "trigger": "create",
                        "mail_template_id": program.mail_template_id.id,
                    }
                )

    @api.depends("company_id")
    def _compute_currency_id(self) -> None:
        for program in self:
            program.currency_id = (
                program.company_id.currency_id
                or program.currency_id
                or self.env.company.currency_id
            )

    @api.depends("coupon_ids")
    def _compute_coupon_count(self) -> None:
        read_group_data = self.env["loyalty.card"]._read_group(
            [("program_id", "in", self.ids)], ["program_id"], ["__count"]
        )
        count_per_program = {program.id: count for program, count in read_group_data}
        for program in self:
            program.coupon_count = count_per_program.get(program.id, 0)

    @api.model
    def _get_domain_nominative(self):
        return Domain("applies_on", "=", "both") | (
            Domain("program_type", "in", ("ewallet", "loyalty"))
            & Domain("applies_on", "=", "future")
        )

    @api.depends("program_type", "applies_on")
    def _compute_is_nominative(self) -> None:
        nominative_ids = set(self.filtered_domain(self._get_domain_nominative())._ids)
        for program in self:
            program.is_nominative = program.id in nominative_ids

    def _search_is_nominative(self, operator, value):
        if operator not in ("in", "not in") or set(value) not in ({True}, {False}):
            return NotImplemented
        domain = self._get_domain_nominative()
        return domain if (True in value) == (operator == "in") else ~domain

    @api.depends("program_type")
    def _compute_is_payment_program(self) -> None:
        for program in self:
            program.is_payment_program = (
                program.program_type in self._PAYMENT_PROGRAM_TYPES
            )

    @api.depends("reward_ids.discount_line_product_id")
    def _compute_payment_program_discount_product_id(self) -> None:
        for program in self:
            if program.is_payment_program:
                program.payment_program_discount_product_id = program.reward_ids[
                    :1
                ].discount_line_product_id
            else:
                program.payment_program_discount_product_id = False

    @api.model
    def _program_items_name(self) -> dict:
        return {
            "coupons": self.env._("Coupons"),
            "promotion": self.env._("Promos"),
            "gift_card": self.env._("Gift Cards"),
            "loyalty": self.env._("Loyalty Cards"),
            "ewallet": self.env._("eWallets"),
            "promo_code": self.env._("Discounts"),
            "buy_x_get_y": self.env._("Promos"),
            "next_order_coupons": self.env._("Coupons"),
        }

    @api.model
    def _program_type_default_values(self):
        first_sale_product = self.env["product.product"].search(
            [
                ("company_id", "in", [False, self.env.company.id]),
                ("sale_ok", "=", True),
            ],
            limit=1,
        )
        return {
            "coupons": self._coupons_default_values(first_sale_product),
            "promotion": self._promotion_default_values(first_sale_product),
            "gift_card": self._gift_card_default_values(first_sale_product),
            "loyalty": self._loyalty_default_values(first_sale_product),
            "ewallet": self._ewallet_default_values(first_sale_product),
            "promo_code": self._promo_code_default_values(first_sale_product),
            "buy_x_get_y": self._buy_x_get_y_default_values(first_sale_product),
            "next_order_coupons": self._next_order_coupons_default_values(
                first_sale_product
            ),
        }

    @api.model
    def _coupons_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "current",
            "trigger": "with_code",
            "portal_visible": False,
            "portal_point_name": self.env._("Coupon point(s)"),
            "rule_ids": [Command.clear()],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "required_points": 1,
                        "discount": 10,
                    }
                ),
            ],
            "communication_plan_ids": [
                Command.clear(),
                Command.create(
                    {
                        "trigger": "create",
                        "mail_template_id": (
                            self.env.ref(
                                "loyalty.mail_template_loyalty_card",
                                raise_if_not_found=False,
                            )
                            or self.env["mail.template"]
                        ).id,
                    }
                ),
            ],
        }

    @api.model
    def _promotion_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "current",
            "trigger": "auto",
            "portal_visible": False,
            "portal_point_name": self.env._("Promo point(s)"),
            "rule_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_point_amount": 1,
                        "reward_point_mode": "order",
                        "minimum_amount": 50,
                        "minimum_qty": 0,
                    }
                ),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "required_points": 1,
                        "discount": 10,
                    }
                ),
            ],
            "communication_plan_ids": [Command.clear()],
        }

    @api.model
    def _gift_card_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "future",
            "trigger": "auto",
            "portal_visible": True,
            "portal_point_name": self.env.company.currency_id.symbol,
            "rule_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_point_amount": 1,
                        "reward_point_mode": "money",
                        "reward_point_split": True,
                        "product_ids": self.env.ref(
                            "loyalty.gift_card_product_50", raise_if_not_found=False
                        ),
                        "minimum_qty": 0,
                    }
                ),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_type": "discount",
                        "discount_mode": "per_point",
                        "discount": 1,
                        "discount_applicability": "order",
                        "required_points": 1,
                        "description": self.env._("Gift Card"),
                    }
                ),
            ],
            "communication_plan_ids": [
                Command.clear(),
                Command.create(
                    {
                        "trigger": "create",
                        "mail_template_id": (
                            self.env.ref(
                                "loyalty.mail_template_gift_card",
                                raise_if_not_found=False,
                            )
                            or self.env["mail.template"]
                        ).id,
                    }
                ),
            ],
        }

    @api.model
    def _loyalty_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "both",
            "trigger": "auto",
            "portal_visible": True,
            "portal_point_name": self.env._("Loyalty point(s)"),
            "rule_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_point_mode": "money",
                    }
                ),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "discount": 5,
                        "required_points": 200,
                    }
                ),
            ],
            "communication_plan_ids": [Command.clear()],
        }

    @api.model
    def _ewallet_default_values(self, first_sale_product) -> dict:
        return {
            "trigger": "auto",
            "applies_on": "future",
            "portal_visible": True,
            "portal_point_name": self.env.company.currency_id.symbol,
            "rule_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_point_amount": "1",
                        "reward_point_mode": "money",
                        "reward_point_split": False,
                        "product_ids": self.env.ref(
                            "loyalty.ewallet_product_50", raise_if_not_found=False
                        ),
                    }
                ),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_type": "discount",
                        "discount_mode": "per_point",
                        "discount": 1,
                        "discount_applicability": "order",
                        "required_points": 1,
                        "description": self.env._("eWallet"),
                    }
                ),
            ],
            "communication_plan_ids": [Command.clear()],
        }

    @api.model
    def _promo_code_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "current",
            "trigger": "with_code",
            "portal_visible": False,
            "portal_point_name": self.env._("Discount point(s)"),
            "rule_ids": [
                Command.clear(),
                Command.create({"mode": "with_code", "minimum_qty": 0}),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "discount_applicability": "specific",
                        "discount_product_ids": first_sale_product,
                        "discount_mode": "percent",
                        "discount": 10,
                    }
                ),
            ],
            "communication_plan_ids": [Command.clear()],
        }

    @api.model
    def _buy_x_get_y_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "current",
            "trigger": "auto",
            "portal_visible": False,
            "portal_point_name": self.env._("Credit(s)"),
            "rule_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_point_mode": "unit",
                        "product_ids": first_sale_product,
                        "minimum_qty": 2,
                    }
                ),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_type": "product",
                        "reward_product_id": first_sale_product.id,
                        "required_points": 2,
                    }
                ),
            ],
            "communication_plan_ids": [Command.clear()],
        }

    @api.model
    def _next_order_coupons_default_values(self, first_sale_product) -> dict:
        return {
            "applies_on": "future",
            "trigger": "auto",
            "portal_visible": True,
            "portal_point_name": self.env._("Coupon point(s)"),
            "rule_ids": [
                Command.clear(),
                Command.create(
                    {
                        "minimum_amount": 100,
                        "minimum_qty": 0,
                    }
                ),
            ],
            "reward_ids": [
                Command.clear(),
                Command.create(
                    {
                        "reward_type": "discount",
                        "discount_mode": "percent",
                        "discount": 15,
                        "discount_applicability": "order",
                    }
                ),
            ],
            "communication_plan_ids": [
                Command.clear(),
                Command.create(
                    {
                        "trigger": "create",
                        "mail_template_id": (
                            self.env.ref(
                                "loyalty.mail_template_loyalty_card",
                                raise_if_not_found=False,
                            )
                            or self.env["mail.template"]
                        ).id,
                    }
                ),
            ],
        }

    @api.model
    def _get_child_default_values(self, program_type, field_name):
        creates = self._get_children_default_values(program_type, field_name)
        return creates[0] if len(creates) == 1 else {}

    @api.model
    def _get_children_default_values(self, program_type, field_name) -> list:
        defaults = self._program_type_default_values().get(program_type) or {}
        return [
            command[2]
            for command in defaults.get(field_name) or ()
            if isinstance(command, (list, tuple))
            and command[0] == Command.CREATE
            and isinstance(command[2], dict)
        ]

    @api.depends("program_type")
    def _compute_from_program_type(self) -> None:
        program_type_defaults = self._program_type_default_values()
        grouped_programs = defaultdict(lambda: self.env["loyalty.program"])
        for program in self:
            grouped_programs[program.program_type] |= program
        for program_type, programs in grouped_programs.items():
            if program_type in program_type_defaults:
                programs.write(program_type_defaults[program_type])

    @api.depends("currency_id", "program_type")
    def _compute_portal_point_name(self) -> None:
        for program in self:
            if program.program_type not in self._PAYMENT_PROGRAM_TYPES:
                continue
            program.portal_point_name = program.currency_id.symbol or ""

    def _get_valid_products(self, products):
        rule_products = {}
        for rule in self.rule_ids:
            domain = rule._get_domain_valid_product()
            if domain:
                rule_products[rule] = products.filtered_domain(domain)
            elif not domain and rule.program_type != "gift_card":
                rule_products[rule] = products
            else:
                continue
        return rule_products

    def action_view_loyalty_cards(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "loyalty.loyalty_card_action"
        )
        items_name = self.coupon_count_label
        action["name"] = items_name
        action["display_name"] = items_name
        action["context"] = {
            "program_type": self.program_type,
            "program_item_name": items_name,
            "default_program_id": self.id,
            "default_mode": "selected"
            if self.program_type == "ewallet"
            else "anonymous",
        }
        return action

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active(self) -> None:
        if any(program.active for program in self):
            raise UserError(
                self.env._("You can not delete a program in an active state")
            )

    @staticmethod
    def _commands_leave_a_reward(commands) -> bool:
        if not isinstance(commands, (list, tuple)):
            return bool(commands)
        count = None
        for command in commands:
            if not isinstance(command, (list, tuple)):
                count = (count or 0) + 1
                continue
            match command[0]:
                case Command.CREATE | Command.LINK:
                    count = (count or 0) + 1
                case Command.CLEAR:
                    count = 0
                case Command.SET:
                    count = len(command[2])
                case Command.DELETE | Command.UNLINK:
                    count = None if count is None else max(count - 1, 0)
                case _:
                    pass
        return bool(count)

    def write(self, vals):
        if "trigger_product_ids" in vals:
            target_type = vals.get("program_type")
            accepts = self.filtered(
                lambda program: (
                    (target_type or program.program_type) in self._PAYMENT_PROGRAM_TYPES
                )
            )
            if accepts != self:
                rest_vals = {
                    k: v for k, v in vals.items() if k != "trigger_product_ids"
                }
                result = accepts.write(vals) if accepts else True
                return (self - accepts).write(rest_vals) and result

        if "reward_ids" in vals and self._commands_leave_a_reward(vals["reward_ids"]):
            self = self.with_context(loyalty_skip_reward_check=True)
            if "program_type" in vals:
                res = super(
                    LoyaltyProgram, self.with_context(program_type=vals["program_type"])
                ).write(vals)
            else:
                res = True
                for program_type, programs in self.grouped("program_type").items():
                    programs = programs.with_context(program_type=program_type)
                    res = super(LoyaltyProgram, programs).write(vals) and res
        else:
            res = super().write(vals)

        if "active" in vals:
            for program in self.with_context(active_test=False):
                program.rule_ids.active = program.active
                program.reward_ids.active = program.active
                program.communication_plan_ids.active = program.active

        return res

    @api.model
    def get_program_templates(self):
        ctx_menu_type = self.env.context.get("menu_type")
        if ctx_menu_type == "gift_ewallet":
            return {
                "gift_card": {
                    "title": self.env._("Gift Card"),
                    "description": self.env._(
                        "Sell Gift Cards, that allows to purchase products"
                    ),
                    "icon": "gift_card",
                },
                "ewallet": {
                    "title": self.env._("eWallet"),
                    "description": self.env._(
                        "Fill in your eWallet, to pay future orders"
                    ),
                    "icon": "ewallet",
                },
            }
        return {
            "promotion": {
                "title": self.env._("Promotional Program"),
                "description": self.env._(
                    "Automatic promo: 10% off on orders higher than $50"
                ),
                "icon": "promotional_program",
            },
            "promo_code": {
                "title": self.env._("Promo Code"),
                "description": self.env._("Get 10% off on some products, with a code"),
                "icon": "promo_code",
            },
            "buy_x_get_y": {
                "title": self.env._("Buy X Get Y"),
                "description": self.env._(
                    "Buy 2 products and get a third one for free"
                ),
                "icon": "2_plus_1",
            },
            "next_order_coupons": {
                "title": self.env._("Next Order Coupon"),
                "description": self.env._(
                    "Send a coupon after an order, valid for next purchase"
                ),
                "icon": "coupons",
            },
            "loyalty": {
                "title": self.env._("Loyalty Card"),
                "description": self.env._(
                    "Win points with each purchase, and claim gifts"
                ),
                "icon": "loyalty_cards",
            },
            "coupons": {
                "title": self.env._("Coupon"),
                "description": self.env._(
                    "Generate and share unique coupons with your customers"
                ),
                "icon": "coupons",
            },
            "fidelity": {
                "title": self.env._("Fidelity Card"),
                "description": self.env._(
                    "Buy 10 products to get 10$ off on the 11th one"
                ),
                "icon": "fidelity_cards",
            },
        }

    @api.model
    def create_from_template(self, template_id):
        template_values = self._prepare_program_template_vals()
        if template_id not in template_values:
            return False
        program = self.create(template_values[template_id])
        action = {}
        if self.env.context.get("menu_type") == "gift_ewallet":
            action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "loyalty.loyalty_program_gift_ewallet_action"
            )
            action["views"] = [[False, "form"]]
        else:
            action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "loyalty.loyalty_program_discount_loyalty_action"
            )
            view_id = self.env.ref("loyalty.loyalty_program_view_form").id
            action["views"] = [[view_id, "form"]]
        action["view_mode"] = "form"
        action["res_id"] = program.id
        return action

    @api.model
    def _prepare_program_template_vals(self):
        program_type_defaults = self._program_type_default_values()
        product = self.env["product.product"].search([("sale_ok", "=", True)], limit=1)
        return {
            "gift_card": {
                "name": self.env._("Gift Card"),
                "program_type": "gift_card",
                **program_type_defaults["gift_card"],
            },
            "ewallet": {
                "name": self.env._("eWallet"),
                "program_type": "ewallet",
                **program_type_defaults["ewallet"],
            },
            "loyalty": {
                "name": self.env._("Loyalty Cards"),
                "program_type": "loyalty",
                **program_type_defaults["loyalty"],
            },
            "coupons": {
                "name": self.env._("Coupons"),
                "program_type": "coupons",
                **program_type_defaults["coupons"],
            },
            "promotion": {
                "name": self.env._("Promotional Program"),
                "program_type": "promotion",
                **program_type_defaults["promotion"],
            },
            "promo_code": {
                "name": self.env._("Discount code"),
                "program_type": "promo_code",
                **program_type_defaults["promo_code"],
            },
            "buy_x_get_y": {
                "name": self.env._("2+1 Free"),
                "program_type": "buy_x_get_y",
                **program_type_defaults["buy_x_get_y"],
            },
            "next_order_coupons": {
                "name": self.env._("Next Order Coupons"),
                "program_type": "next_order_coupons",
                **program_type_defaults["next_order_coupons"],
            },
            "fidelity": {
                "name": self.env._("Fidelity Cards"),
                "program_type": "loyalty",
                "applies_on": "both",
                "trigger": "auto",
                "rule_ids": [
                    Command.create(
                        {
                            "reward_point_mode": "unit",
                            "product_ids": product,
                        }
                    )
                ],
                "reward_ids": [
                    Command.create(
                        {
                            "discount_mode": "per_order",
                            "required_points": 11,
                            "discount_applicability": "specific",
                            "discount_product_ids": product,
                            "discount": 10,
                        }
                    )
                ],
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [
            self._with_point_name(self._with_program_type_values(vals))
            for vals in vals_list
        ]
        return super().create(vals_list)

    @api.model
    def _with_point_name(self, vals):
        if "portal_point_name" in vals:
            return vals
        program_type = vals.get("program_type") or self.default_get(
            ["program_type"]
        ).get("program_type")
        if program_type in self._PAYMENT_PROGRAM_TYPES:
            return vals
        return {**vals, "portal_point_name": "Points"}

    @api.model
    def _with_program_type_values(self, vals):
        program_type = vals.get("program_type")
        if not program_type:
            return vals
        completed = dict(vals)
        if program_type not in self._PAYMENT_PROGRAM_TYPES:
            completed.pop("trigger_product_ids", None)
        for field_name in self._TYPE_DEFAULT_CHILDREN:
            if field_name in completed:
                continue
            children = self._get_children_default_values(program_type, field_name)
            if children:
                completed[field_name] = [Command.create(vals) for vals in children]
        return completed
