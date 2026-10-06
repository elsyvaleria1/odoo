from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError

# The precomputed fields here read their inputs through many2ones only: a
# precompute reading an x2many reads the draft twins of the saved lines,
# which keep values from before a later write.
#
# A compute reading an x2many over a model with `active` reads it filtered by
# the caller's `active_test`, and archiving a line changes that membership:
# as upstream, the dependency on `.active` and the context key are the
# declaration's to state. A stored compute runs in the environment of whoever
# needs it (a flush, a read), so the stored ones here filter on `active`
# themselves and store the same value whoever triggered them.


class TestOrmCoherenceCategory(models.Model):
    _name = "test_orm.coherence.category"
    _description = (
        "Category tree whose values derive from its ancestors and its subtree"
    )
    _parent_store = True

    name = fields.Char()
    code = fields.Char()
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one("test_orm.coherence.category", ondelete="cascade")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("test_orm.coherence.category", "parent_id")
    order_ids = fields.One2many("test_orm.coherence.order", "category_id")
    item_ids = fields.One2many("test_orm.coherence.item", "category_id")
    depth = fields.Integer(
        compute="_compute_depth", store=True, recursive=True, precompute=True
    )
    full_name = fields.Char(
        compute="_compute_full_name", store=True, recursive=True, precompute=True
    )
    trail = fields.Char(compute="_compute_trail", recursive=True)
    order_total = fields.Integer(compute="_compute_order_total", store=True)
    subtree_total = fields.Integer(
        compute="_compute_subtree_total", store=True, recursive=True
    )
    item_weight = fields.Integer(compute="_compute_item_weight", store=True)
    properties_definition = fields.PropertiesDefinition()

    @api.depends("parent_id.depth")
    def _compute_depth(self):
        for category in self:
            category.depth = category.parent_id.depth + 1 if category.parent_id else 0

    @api.depends("name", "parent_id.full_name")
    def _compute_full_name(self):
        for category in self:
            name = category.name or "-"
            parent = category.parent_id
            category.full_name = f"{parent.full_name}/{name}" if parent else name

    @api.depends("code", "parent_id.trail")
    def _compute_trail(self):
        for category in self:
            code = category.code or "."
            parent = category.parent_id
            category.trail = f"{parent.trail}>{code}" if parent else code

    @api.depends("order_ids.total", "order_ids.active")
    def _compute_order_total(self):
        for category in self:
            category.order_total = sum(
                category.order_ids.filtered("active").mapped("total")
            )

    @api.depends("order_total", "child_ids.subtree_total", "child_ids.active")
    def _compute_subtree_total(self):
        for category in self:
            category.subtree_total = category.order_total + sum(
                category.child_ids.filtered("active").mapped("subtree_total")
            )

    @api.depends("item_ids.weight")
    def _compute_item_weight(self):
        for category in self:
            category.item_weight = sum(category.item_ids.mapped("weight"))

    @api.model
    @tools.ormcache("code")
    def _get_category_id_by_code(self, code):
        found = self.with_context(active_test=False).search(
            [("code", "=", code)], order="id", limit=1
        )
        return found.id or None

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("code") for vals in vals_list):
            self.env.registry.clear_cache()
        return super().create(vals_list)

    def write(self, vals):
        if "code" in vals:
            self.env.registry.clear_cache()
        return super().write(vals)

    def unlink(self):
        self.env.registry.clear_cache()
        return super().unlink()


class TestOrmCoherenceOrder(models.Model):
    _name = "test_orm.coherence.order"
    _description = "Order whose totals derive from its lines, tags and category"

    name = fields.Char()
    active = fields.Boolean(default=True)
    category_id = fields.Many2one("test_orm.coherence.category", ondelete="set null")
    line_ids = fields.One2many("test_orm.coherence.line", "order_id")
    tag_ids = fields.Many2many(
        "test_orm.coherence.tag",
        "test_orm_coherence_order_tag_rel",
        "order_id",
        "tag_id",
    )
    priority = fields.Integer(company_dependent=True)
    fallback_tag_id = fields.Many2one("test_orm.coherence.tag", company_dependent=True)
    priority_label = fields.Char(compute="_compute_priority_label")
    attributes = fields.Properties(definition="category_id.properties_definition")
    total = fields.Integer(compute="_compute_total", store=True)
    line_count = fields.Integer(compute="_compute_line_count")
    tag_names = fields.Char(compute="_compute_tag_names", store=True)
    tag_labels = fields.Char(compute="_compute_tag_labels")
    category_name = fields.Char(related="category_id.full_name", store=True)
    category_depth = fields.Integer(related="category_id.depth")

    @api.depends("line_ids.amount", "line_ids.active")
    def _compute_total(self):
        for order in self:
            order.total = sum(order.line_ids.filtered("active").mapped("amount"))

    @api.depends("priority", "fallback_tag_id.name")
    @api.depends_context("company")
    def _compute_priority_label(self):
        for order in self:
            order.priority_label = (
                f"{order.priority}:{order.fallback_tag_id.name or '-'}"
            )

    @api.depends("line_ids.active")
    @api.depends_context("active_test")
    def _compute_line_count(self):
        for order in self:
            order.line_count = len(order.line_ids)

    @api.depends("tag_ids.name", "tag_ids.active")
    def _compute_tag_names(self):
        for order in self:
            order.tag_names = ",".join(
                sorted(order.tag_ids.filtered("active").mapped(lambda t: t.name or ""))
            )

    @api.depends("tag_ids.label", "tag_ids.active")
    @api.depends_context("lang", "active_test")
    def _compute_tag_labels(self):
        for order in self:
            order.tag_labels = ",".join(
                sorted(order.tag_ids.mapped(lambda t: t.label or ""))
            )


class TestOrmCoherenceLine(models.Model):
    _name = "test_orm.coherence.line"
    _description = "Order line whose amount reads its order's category two hops away"

    order_id = fields.Many2one("test_orm.coherence.order", ondelete="set null")
    active = fields.Boolean(default=True)
    qty = fields.Integer()
    price = fields.Integer()
    amount = fields.Integer(compute="_compute_amount", store=True, precompute=True)
    order_category_id = fields.Many2one(
        related="order_id.category_id", store=True, string="Order Category"
    )
    order_name = fields.Char(related="order_id.name", string="Order Name")

    @api.depends("qty", "price", "order_id.category_id.depth")
    def _compute_amount(self):
        for line in self:
            line.amount = line.qty * line.price + line.order_id.category_id.depth

    @api.constrains("qty")
    def _check_qty_not_negative(self):
        if any(line.qty < 0 for line in self):
            raise ValidationError(self.env._("A line's quantity cannot be negative."))


class TestOrmCoherenceTag(models.Model):
    _name = "test_orm.coherence.tag"
    _description = "Tag counted by the orders it is on"

    name = fields.Char()
    label = fields.Char(translate=True)
    active = fields.Boolean(default=True)
    order_ids = fields.Many2many(
        "test_orm.coherence.order",
        "test_orm_coherence_order_tag_rel",
        "tag_id",
        "order_id",
    )
    order_count = fields.Integer(compute="_compute_order_count", store=True)

    @api.depends("order_ids.active")
    def _compute_order_count(self):
        for tag in self:
            tag.order_count = len(tag.order_ids.filtered("active"))


class TestOrmCoherenceItem(models.Model):
    _name = "test_orm.coherence.item"
    _description = (
        "Root of a table-inheritance tree whose subtype derives from its columns"
    )
    _table = "test_orm_coherence_item"
    _table_inheritance_root = "test_orm_coherence_item"

    name = fields.Char()
    weight = fields.Integer()
    category_id = fields.Many2one("test_orm.coherence.category", ondelete="set null")


class TestOrmCoherenceItemSpecial(models.Model):
    _name = "test_orm.coherence.item.special"
    _description = "Subtype of the item tree, with its own table and computes"
    _inherit = ["test_orm.coherence.item"]
    _table = "test_orm_coherence_item_special"
    _table_inheritance_root = "test_orm_coherence_item"

    extra = fields.Integer()
    load = fields.Integer(compute="_compute_load", store=True)
    weight_label = fields.Char(compute="_compute_weight_label")

    @api.depends("weight", "extra")
    def _compute_load(self):
        for item in self:
            item.load = item.weight * 10 + item.extra

    @api.depends("weight", "category_id.name")
    def _compute_weight_label(self):
        for item in self:
            item.weight_label = f"{item.category_id.name or '-'}:{item.weight}"
