from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict

from odoo.addons.base.models.mixin_access_graph import AccessGrantNames, AccessGraph


class Test_Access_RightSome_Obj(models.Model):
    _name = "test_access_right.some_obj"
    _description = "Object For Test Access Right"

    val = fields.Integer()
    categ_id = fields.Many2one(comodel_name="test_access_right.obj_categ")
    parent_id = fields.Many2one(comodel_name="test_access_right.some_obj")
    company_id = fields.Many2one(comodel_name="res.company")
    forbidden = fields.Integer(
        default=5,
        groups="test_access_rights.test_group,base.group_portal",
    )
    forbidden2 = fields.Integer(groups="test_access_rights.test_group")
    forbidden3 = fields.Integer(groups=fields.NO_ACCESS)
    forbidden_searchable = fields.Integer(
        compute="_compute_forbidden_searchable",
        search="_search_forbidden_searchable",
        groups=fields.NO_ACCESS,
    )
    write_gated = fields.Integer(write_groups="test_access_rights.test_group")
    write_gated_never = fields.Integer(write_groups=fields.NO_ACCESS)
    write_gated_on_stored = fields.Integer(
        write_groups=lambda records: (
            not records.ids
            or records.env.user.has_group("test_access_rights.test_group")
        )
    )
    read_and_write_gated = fields.Integer(
        write_groups="base.group_system",
        groups="test_access_rights.test_group",
    )

    @api.depends("val")
    def _compute_forbidden_searchable(self):
        for record in self:
            record.forbidden_searchable = record.val

    def _search_forbidden_searchable(self, operator, value):
        return [("val", operator, value)]


class Test_Access_RightContainer(models.Model):
    _name = "test_access_right.container"
    _description = "Test Access Right Container"

    some_ids = fields.Many2many(
        comodel_name="test_access_right.some_obj",
        relation="test_access_right_rel",
        column1="container_id",
        column2="some_id",
    )


class Test_Access_RightInherits(models.Model):
    _name = "test_access_right.inherits"
    _description = "Object for testing related access rights"

    _inherits = {"test_access_right.some_obj": "some_id"}

    some_id = fields.Many2one(
        comodel_name="test_access_right.some_obj",
        required=True,
        ondelete="restrict",
    )


class Test_Access_RightInheritsComputed(models.Model):
    _name = "test_access_right.inherits_computed"
    _description = "Object delegating through a computed, searchable link"

    _inherits = {"test_access_right.some_obj": "some_id"}

    held_id = fields.Many2one(
        comodel_name="test_access_right.some_obj",
        ondelete="restrict",
    )
    some_id = fields.Many2one(
        comodel_name="test_access_right.some_obj",
        compute="_compute_some_id",
        search="_search_some_id",
        compute_sudo=True,
        store=False,
        required=True,
        ondelete="cascade",
    )

    @api.depends("held_id")
    def _compute_some_id(self):
        for record in self:
            record.some_id = record.held_id

    def _search_some_id(self, operator, value):
        return Domain("held_id", operator, value)

    def _create_parent_records(self, data_list):
        for data in data_list:
            data["stored"]["some_id"] = data["stored"].get("held_id")
        super()._create_parent_records(data_list)
        for data in data_list:
            data["stored"]["held_id"] = data["stored"].pop("some_id")


class Test_Access_RightChild(models.Model):
    _name = "test_access_right.child"
    _description = "Object for testing company ir rule"

    parent_id = fields.Many2one(comodel_name="test_access_right.some_obj")


class Test_Access_RightObj_Categ(models.Model):
    _name = "test_access_right.obj_categ"
    _description = "Context dependent searchable model"

    name = fields.Char(required=True)

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        if self.env.context.get("only_media"):
            domain = Domain(domain) & Domain("name", "=", "Media")
        return super().search_fetch(domain, field_names, offset, limit, order)


class Test_Access_RightTicket(models.Model):
    _name = "test_access_right.ticket"
    _description = "Fake ticket For Test Access Right"

    name = fields.Char()
    message_partner_ids = fields.Many2many(comodel_name="res.partner")


class ResPartner(models.Model):
    _inherit = "res.partner"

    test_access_currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_test_access_currency_id",
        readonly=True,
    )
    test_access_monetary = fields.Monetary(currency_field="test_access_currency_id")

    @api.depends("company_id.currency_id")
    def _compute_test_access_currency_id(self):
        for partner in self:
            partner.test_access_currency_id = partner.sudo().company_id.currency_id


class Test_Access_RightSharedDoc(models.Model):
    _name = "test_access_right.shared_doc"
    _description = "A record shared by link"

    name = fields.Char()
    company_id = fields.Many2one(comodel_name="res.company")
    reader_ids = fields.Many2many(comodel_name="res.users")


class Test_Access_RightPropertyDoc(models.Model):
    _name = "test_access_right.property_doc"
    _description = "A record the access property test generates rows over"
    _access_anchors = frozendict({"owner": "owner_id"})

    name = fields.Char()
    a = fields.Integer()
    b = fields.Integer()
    flag = fields.Boolean()
    owner_id = fields.Many2one(comodel_name="res.users")
    company_id = fields.Many2one(comodel_name="res.company")
    parent_id = fields.Many2one(comodel_name="test_access_right.property_doc")


class Test_Access_RightPropertyLine(models.Model):
    _name = "test_access_right.property_line"
    _description = "A line whose owner follows its document"
    _access_anchors = frozendict({"owner": "owner_id"})

    name = fields.Char()
    doc_id = fields.Many2one(comodel_name="test_access_right.property_doc")
    owner_id = fields.Many2one(
        related="doc_id.owner_id",
        store=True,
    )


class Test_Access_RightGraphNode(models.Model):
    _name = "test_access_right.graph_node"
    _inherit = ["mixin.access.graph"]
    _description = "A node of a tree whose grants inherit"
    _parent_name = "parent_id"
    _parent_store = True
    _access_graph = AccessGraph(
        parent="parent_id",
        grants="grant_ids",
        roles=("view", "edit", "manage"),
        owner="owner_id",
        boundary="is_boundary",
        container=("is_container", True),
    )

    name = fields.Char()
    parent_id = fields.Many2one(
        comodel_name="test_access_right.graph_node",
        index=True,
        ondelete="cascade",
    )
    parent_path = fields.Char(index=True)
    is_container = fields.Boolean(default=True)
    is_boundary = fields.Boolean()
    owner_id = fields.Many2one(comodel_name="res.users")
    company_id = fields.Many2one(comodel_name="res.company")
    grant_ids = fields.One2many(
        comodel_name="test_access_right.graph_grant",
        inverse_name="node_id",
    )


class Test_Access_RightGraphGrant(models.Model):
    _name = "test_access_right.graph_grant"
    _inherit = ["mixin.access.grant"]
    _description = "A grant on a tree node"
    _access_grant_names = AccessGrantNames(resource="node_id")

    node_id = fields.Many2one(
        comodel_name="test_access_right.graph_node",
        index=True,
        required=True,
        ondelete="cascade",
    )
    role = fields.Selection(
        selection=[("view", "View"), ("edit", "Edit"), ("manage", "Manage")],
        required=True,
    )


class Test_Access_RightMemoFolder(models.Model):
    _name = "test_access_right.memo_folder"
    _description = "A folder tree the memo property's document rules read"
    _parent_name = "parent_id"
    _parent_store = True

    name = fields.Char()
    parent_id = fields.Many2one(
        comodel_name="test_access_right.memo_folder",
        index=True,
        ondelete="cascade",
    )
    parent_path = fields.Char(index=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(comodel_name="res.company")
    manager_id = fields.Many2one(comodel_name="res.users")


class Test_Access_RightMemoTag(models.Model):
    _name = "test_access_right.memo_tag"
    _description = "A tag the memo property's document rules read"

    name = fields.Char()
    color = fields.Integer()
    active = fields.Boolean(default=True)


class Test_Access_RightMemoDoc(models.Model):
    _name = "test_access_right.memo_doc"
    _description = "A document whose access the verdict memos keep"
    _access_anchors = frozendict(
        {"owner": "owner_id", "partner": "partner_id", "company": "company_id"}
    )

    name = fields.Char(translate=True)
    level = fields.Integer()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("open", "Open"), ("done", "Done")]
    )
    active = fields.Boolean(default=True)
    folder_id = fields.Many2one(
        comodel_name="test_access_right.memo_folder",
        ondelete="set null",
    )
    owner_id = fields.Many2one(comodel_name="res.users")
    partner_id = fields.Many2one(comodel_name="res.partner")
    company_id = fields.Many2one(comodel_name="res.company")
    line_ids = fields.One2many(
        comodel_name="test_access_right.memo_line",
        inverse_name="doc_id",
    )
    open_line_ids = fields.One2many(
        comodel_name="test_access_right.memo_line",
        inverse_name="doc_id",
        domain=[("kind", "=", "open")],
    )
    tag_ids = fields.Many2many(comodel_name="test_access_right.memo_tag")
    total = fields.Integer(compute="_compute_total", store=True)
    note = fields.Char(classification="test_access_rights.memo_note")

    @api.depends("line_ids.amount")
    def _compute_total(self) -> None:
        for doc in self:
            doc.total = sum(doc.line_ids.mapped("amount"))


class Test_Access_RightMemoLine(models.Model):
    _name = "test_access_right.memo_line"
    _description = "A line of a document the memo property judges"
    _access_anchors = frozendict({"owner": "owner_id", "partner": "doc_id.partner_id"})

    doc_id = fields.Many2one(
        comodel_name="test_access_right.memo_doc",
        ondelete="cascade",
    )
    amount = fields.Integer()
    kind = fields.Selection(selection=[("open", "Open"), ("closed", "Closed")])
    active = fields.Boolean(default=True)
    owner_id = fields.Many2one(comodel_name="res.users")
    label = fields.Char(translate=True)
