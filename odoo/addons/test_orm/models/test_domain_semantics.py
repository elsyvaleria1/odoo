from odoo import api, fields, models


class TestOrmDomainPartner(models.Model):
    _name = "test_orm.domain.partner"
    _description = "the comodel a domain reaches through a many2one"

    name = fields.Char()
    rank = fields.Integer()
    since = fields.Date()
    active = fields.Boolean(default=True)
    props_definition = fields.PropertiesDefinition()


class TestOrmDomainTag(models.Model):
    _name = "test_orm.domain.tag"
    _description = "the comodel a domain reaches through a many2many"

    name = fields.Char()
    color = fields.Integer()
    active = fields.Boolean(default=True)


class TestOrmDomainItem(models.Model):
    _name = "test_orm.domain.item"
    _description = "a record holding one field of every kind a domain searches"
    _parent_store = True

    name = fields.Char()
    title = fields.Char(translate=True)
    code = fields.Char(size=5)
    note = fields.Text()
    summary = fields.Text(translate=True)
    qty = fields.Integer()
    amount = fields.Float()
    flag = fields.Boolean()
    day = fields.Date()
    moment = fields.Datetime()
    state = fields.Selection(
        [("draft", "Draft"), ("open", "Open"), ("done", "Done")],
    )
    active = fields.Boolean(default=True)
    company_qty = fields.Integer(company_dependent=True)
    company_label = fields.Char(company_dependent=True)
    company_tag_id = fields.Many2one("test_orm.domain.tag", company_dependent=True)

    partner_id = fields.Many2one("test_orm.domain.partner")
    owner_id = fields.Many2one("test_orm.domain.partner", required=True)
    user_id = fields.Many2one("res.users")
    props = fields.Properties(definition="owner_id.props_definition")
    parent_id = fields.Many2one("test_orm.domain.item", index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("test_orm.domain.item", "parent_id")
    line_ids = fields.One2many("test_orm.domain.line", "item_id")
    tag_ids = fields.Many2many("test_orm.domain.tag")
    detail_id = fields.One2one("test_orm.domain.detail", "item_id")

    partner_rank = fields.Integer(related="partner_id.rank")
    partner_name = fields.Char(related="partner_id.name")
    partner_since = fields.Date(related="partner_id.since")
    parent_title = fields.Char(related="parent_id.title")
    owner_rank = fields.Integer(related="owner_id.rank")
    owner_name = fields.Char(related="owner_id.name")
    parent_partner_rank = fields.Integer(related="parent_id.partner_id.rank")
    line_qty = fields.Integer(related="line_ids.qty")
    line_name = fields.Char(related="line_ids.name")
    line_done = fields.Boolean(related="line_ids.done")
    line_tag_id = fields.Many2one(related="line_ids.tag_id")
    tag_name = fields.Char(related="tag_ids.name")
    detail_value = fields.Integer(related="detail_id.value")
    detail_label = fields.Char(related="detail_id.label")
    partner_rank_stored = fields.Integer(related="partner_id.rank", store=True)

    qty_sign = fields.Integer(compute="_compute_qty_sign", store=True)
    line_count = fields.Integer(compute="_compute_line_count", store=True)
    label = fields.Char(compute="_compute_label", store=True)

    @api.depends("qty")
    def _compute_qty_sign(self):
        for item in self:
            item.qty_sign = (item.qty > 0) - (item.qty < 0)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for item in self:
            item.line_count = len(item.line_ids)

    @api.depends("name", "code")
    def _compute_label(self):
        for item in self:
            item.label = (item.name or "") + (item.code or "") or False


class TestOrmDomainLine(models.Model):
    _name = "test_orm.domain.line"
    _description = "the comodel a domain reaches through a one2many"

    item_id = fields.Many2one("test_orm.domain.item", required=True, ondelete="cascade")
    name = fields.Char()
    qty = fields.Integer()
    done = fields.Boolean()
    tag_id = fields.Many2one("test_orm.domain.tag")


class TestOrmDomainDetail(models.Model):
    _name = "test_orm.domain.detail"
    _description = "the comodel a domain reaches through a one2one"
    _rec_name = "item_id"

    item_id = fields.Many2one(
        "test_orm.domain.item", index="unique", ondelete="cascade"
    )
    value = fields.Integer()
    label = fields.Char()
