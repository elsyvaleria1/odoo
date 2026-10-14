from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict

from odoo.addons.base.models.ir_access import predicate_arguments


class TestIrAccessCategory(models.Model):
    _name = "test_ir_access.category"
    _description = "Category read through ir.access"

    name = fields.Char()
    featured_item_id = fields.Many2one(comodel_name="test_ir_access.item")


class TestIrAccessItem(models.Model):
    _name = "test_ir_access.item"
    _description = "Item read through ir.access"

    name = fields.Char()
    val = fields.Integer()
    category_id = fields.Many2one(comodel_name="test_ir_access.category")


class TestIrAccessNode(models.Model):
    _name = "test_ir_access.node"
    _description = "Tree node read through ir.access"

    name = fields.Char()
    parent_id = fields.Many2one(comodel_name="test_ir_access.node")


class TestIrAccessDelegated(models.Model):
    _name = "test_ir_access.delegated"
    _description = "Delegates to an item through a column"
    _inherits = {"test_ir_access.item": "item_id"}

    item_id = fields.Many2one(
        comodel_name="test_ir_access.item",
        required=True,
        ondelete="cascade",
    )


class TestIrAccessDelegatedComputed(models.Model):
    _name = "test_ir_access.delegated_computed"
    _description = "Delegates to an item through a computed, searchable link"
    _inherits = {"test_ir_access.item": "item_id"}

    held_id = fields.Many2one(
        comodel_name="test_ir_access.item",
        ondelete="restrict",
    )
    item_id = fields.Many2one(
        comodel_name="test_ir_access.item",
        compute="_compute_item_id",
        search="_search_item_id",
        compute_sudo=True,
        store=False,
        required=True,
        ondelete="cascade",
    )

    @api.depends("held_id")
    def _compute_item_id(self):
        for record in self:
            record.item_id = record.held_id

    def _search_item_id(self, operator, value):
        return Domain("held_id", operator, value)

    def _create_or_update_parent_records(self, data_list):
        for data in data_list:
            data["stored"]["item_id"] = data["stored"].get("held_id")
        super()._create_or_update_parent_records(data_list)
        for data in data_list:
            data["stored"]["held_id"] = data["stored"].pop("item_id")


class TestIrAccessGuarded(models.Model):
    _name = "test_ir_access.guarded"
    _description = "Readable where its category is, by the model's own guard"

    name = fields.Char()
    category_id = fields.Many2one(comodel_name="test_ir_access.category")

    @api.model
    def _access_guard(self, operation):
        guard = super()._access_guard(operation)
        if operation == "read":
            return guard & Domain("category_id", "access", "read")
        return guard


class TestIrAccessOwned(models.Model):
    _name = "test_ir_access.owned"
    _description = "Follows the access of the item that owns it"
    _inherit = ["mixin.owner.access"]
    _access_owner_field = "item_id"

    name = fields.Char()
    item_id = fields.Many2one(comodel_name="test_ir_access.item")


class TestIrAccessReached(models.Model):
    _name = "test_ir_access.reached"
    _description = "Reached through the anchors it declares"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
            "assignee": models.Anchor("user_id", kind="owner", shared=True),
            "approver": models.Anchor("approver_ids", kind="owner"),
            "partner": "partner_id",
            "company": models.Anchor("company_id", shared=True),
            "parent_company": models.Anchor(
                "company_id", kind="company", shared=False, hierarchy="parent_of"
            ),
        }
    )

    name = fields.Char()
    user_id = fields.Many2one(comodel_name="res.users")
    approver_ids = fields.Many2many(comodel_name="res.users")
    partner_id = fields.Many2one(comodel_name="res.partner")
    company_id = fields.Many2one(comodel_name="res.company")
    is_mine = fields.Boolean(
        compute="_compute_is_mine",
        search="_search_is_mine",
    )

    @api.depends_context("uid")
    def _compute_is_mine(self):
        for record in self:
            record.is_mine = record.user_id == self.env.user

    def _search_is_mine(self, operator, value):
        if operator != "in":
            return NotImplemented
        mine = Domain("user_id", "=", self.env.uid)
        return mine if True in value else ~mine

    @predicate_arguments("name")
    def _access_predicate_named(self, bind, args):
        return Domain("name", "=", args["name"])


class TestIrAccessReachedReport(models.AbstractModel):
    _name = "test_ir_access.reached_report"
    _description = "A report read from a query, as project's analyses are"
    _auto = False
    _table_query = "SELECT id, name, company_id FROM test_ir_access_reached"

    name = fields.Char(readonly=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )


class TestIrAccessClassified(models.Model):
    _name = "test_ir_access.classified"
    _description = "Fields that name the classes a principal must hold"

    name = fields.Char()
    active = fields.Boolean(default=True)
    wage = fields.Float(classification="test_ir_access.pay")
    wage_note = fields.Char(
        classification="test_ir_access.pay",
        groups="base.group_system",
    )
    bonus = fields.Float(write_classification="test_ir_access.pay_write")
    system_note = fields.Char(groups="base.group_system")
    internal_note = fields.Char(groups="base.group_user,!base.group_portal")
    parent_id = fields.Many2one(comodel_name="test_ir_access.classified")
    company_id = fields.Many2one(comodel_name="res.company")
    payee_ids = fields.Many2many(
        comodel_name="res.partner",
        classification="test_ir_access.pay",
    )
    payslip = fields.Binary(
        attachment=True,
        classification="test_ir_access.pay",
    )
    parent_wage = fields.Float(related="parent_id.wage")
    wage_twice = fields.Float(
        compute="_compute_wage_twice",
        compute_sudo=True,
        store=True,
    )

    @api.depends("wage")
    def _compute_wage_twice(self) -> None:
        for record in self:
            record.wage_twice = record.wage * 2


class TestIrAccessWhitelisted(models.Model):
    _name = "test_ir_access.whitelisted"
    _description = "Whose fields are one class but for those it lists"
    _access_residual_class = "test_ir_access.internal"

    name = fields.Char(classification="test_ir_access.shared")
    secret = fields.Char()


class TestIrAccessProfile(models.Model):
    _name = "test_ir_access.profile"
    _description = "A record its owner reads more of than others do"
    _access_anchors = frozendict({"owner": "user_id"})

    name = fields.Char()
    user_id = fields.Many2one(comodel_name="res.users")
    salary = fields.Float(groups="base.group_system")
    note = fields.Char()
    badge = fields.Char(classification="test_ir_access.badge")

    @api.model
    def _access_field_class(self, field):
        if field.name == "badge":
            return "test_ir_access.badge_holders"
        return super()._access_field_class(field)

    @api.model
    def _access_field_alternative_class(self, field):
        if field.name == "salary":
            return "test_ir_access.own"
        return super()._access_field_alternative_class(field)

    @api.model
    def _access_field_write_class(self, field):
        if field.name == "note":
            return "test_ir_access.locked"
        return super()._access_field_write_class(field)


class TestIrAccessLabelled(models.Model):
    _name = "test_ir_access.labelled"
    _description = "A record whose sensitivity label is a field class"
    _access_label_field = "label_id"

    name = fields.Char()
    label_id = fields.Many2one(comodel_name="ir.access.class")


class TestIrAccessDocument(models.Model):
    _name = "test_ir_access.document"
    _description = "A document with a declared verb"
    _access_verbs = {
        "post": models.Verb(
            methods=("action_post",),
            checkpoints=("_check_postable", "_post_entries"),
            transition=("state", "*", "posted"),
        ),
        "retire": models.Verb(
            transition=("state", "*", "retired"),
            at_create=False,
        ),
        "clear": models.Verb(transition=("state", "*", False), at_create=False),
    }

    name = fields.Char()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("posted", "Posted"), ("retired", "Retired")],
        default="draft",
    )
    audit = fields.Char()

    def action_post(self):
        self._check_postable()
        self._post_entries()
        return True

    def _check_postable(self):
        return True

    def _post_entries(self):
        self.write({"state": "posted"})


class TestIrAccessDocumentLine(models.Model):
    _name = "test_ir_access.document_line"
    _description = "A line of a document with a declared verb"

    name = fields.Char()
    document_id = fields.Many2one(comodel_name="test_ir_access.document")


class IrAccessObligation(models.AbstractModel):
    _inherit = "ir.access.obligation"

    def _at_door(self, records, verb, call):
        if records._name == "test_ir_access.document":
            records.env.context.get("verb_calls", []).append(
                ("door", verb, records.ids)
            )
        return super()._at_door(records, verb, call)

    def _at_checkpoint(self, records, verb):
        if records._name == "test_ir_access.document":
            records.env.context.get("verb_calls", []).append(
                ("checkpoint", verb, records.ids)
            )
        return super()._at_checkpoint(records, verb)

    def _after_move(self, records, verb):
        if records._name == "test_ir_access.document":
            records.env.context.get("verb_landings", []).append(
                (verb, records.ids, records.mapped("state"))
            )
        return super()._after_move(records, verb)
