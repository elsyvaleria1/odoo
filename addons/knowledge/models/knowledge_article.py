import ast
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Self

from lxml import html
from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.db.schema import create_index, get_index_name
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.libs.web import urljoin as url_join
from odoo.tools import SQL, OrderedSet, get_lang
from odoo.tools.translate import html_translate

from odoo.addons.base.models.mixin_access_graph import AccessGraph
from odoo.addons.html_editor.tools import handle_history_divergence

_debug = DebugLog(__name__)

ARTICLE_PERMISSION_LEVEL = {"none": 0, "read": 1, "write": 2}


class KnowledgeArticle(models.Model):
    _name = "knowledge.article"
    _description = "Knowledge Article"
    _inherit = [
        "mixin.mail.thread",
        "mixin.mail.activity",
        "mixin.html.field.history",
        "mixin.access.graph",
    ]
    _order = "favorite_count desc, write_date desc, id desc"
    _mail_post_access = "read"
    _parent_store = True
    _access_graph = AccessGraph(
        parent="parent_id",
        grants="access_grant_ids",
        roles=("read", "write"),
        boundary="is_desynchronized",
    )

    def _get_fields_versioned(self):
        return [KnowledgeArticle.body.name]

    DEFAULT_ARTICLE_TRASH_LIMIT_DAYS = 30

    active = fields.Boolean(default=True)
    name = fields.Char(
        string="Title",
        index="trigram",
        tracking=20,
        default_export_compatible=True,
    )
    body = fields.Html(prefetch=False)
    icon = fields.Char(string="Emoji")
    cover_image_id = fields.Many2one(
        comodel_name="knowledge.cover",
        string="Article cover",
        index="btree_not_null",
    )
    cover_image_url = fields.Char(
        related="cover_image_id.attachment_url",
        string="Cover url",
    )
    cover_image_position = fields.Float(string="Cover vertical offset")
    is_locked = fields.Boolean(
        string="Locked",
        help="When locked, users cannot write on the body or change the title, "
        "even if they have write access on the article.",
    )
    full_width = fields.Boolean(
        string="Full width",
        help="When set, the article body will take the full width available on the article page. "
        "Otherwise, the body will have large horizontal margins.",
    )
    article_url = fields.Char(
        string="Article URL",
        compute="_compute_article_url",
        readonly=True,
    )
    internal_permission = fields.Selection(
        selection=[
            ("write", "Can edit"),
            ("read", "Can read"),
            ("none", "Members only"),
        ],
        compute="_compute_internal_permission",
        inverse="_inverse_internal_permission",
        search="_search_internal_permission",
        compute_sudo=True,
        help="Default permission for all internal users, set on this article: "
        "a grant to the employees. (External users can still have access to this "
        "article if they are added to its members)",
    )
    inherited_permission = fields.Selection(
        selection=[
            ("write", "Can edit"),
            ("read", "Can read"),
            ("none", "Members only"),
        ],
        compute="_compute_inherited_permission",
        search="_search_inherited_permission",
        compute_sudo=True,
    )
    inherited_permission_parent_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Inherited Permission Parent Article",
        compute="_compute_inherited_permission",
        compute_sudo=True,
    )
    access_grant_ids = fields.One2many(
        comodel_name="knowledge.article.member",
        inverse_name="article_id",
        string="Grants",
    )
    article_member_ids = fields.One2many(
        comodel_name="knowledge.article.member",
        inverse_name="article_id",
        string="Members Information",
        copy=True,
        domain=[("partner_id", "!=", False)],
    )
    user_has_access = fields.Boolean(
        string="Has Access",
        compute="_compute_user_has_access",
        search="_search_user_has_access",
    )
    user_has_access_parent_path = fields.Boolean(
        string="Can the user join?",
        compute="_compute_user_has_access_parent_path",
        recursive=True,
        help="Has the user access to each parent from current article until its root?",
    )
    user_has_write_access = fields.Boolean(
        string="Has Write Access",
        compute="_compute_user_has_write_access",
        search="_search_user_has_write_access",
    )
    user_can_read = fields.Boolean(
        string="Can Read",
        compute="_compute_user_can_read",
    )
    user_can_write = fields.Boolean(
        string="Can Edit",
        compute="_compute_user_can_write",
    )
    user_permission = fields.Selection(
        selection=[("write", "write"), ("read", "read"), ("none", "none")],
        string="User permission",
        compute="_compute_user_permission",
    )
    parent_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Parent Article",
        index=True,
        ondelete="cascade",
        tracking=30,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        comodel_name="knowledge.article",
        inverse_name="parent_id",
        string="Child Articles and Items",
        copy=True,
    )
    has_item_parent = fields.Boolean(
        related="parent_id.is_article_item",
        string="Is the parent an Item?",
    )
    has_item_children = fields.Boolean(
        string="Has article item children?",
        compute="_compute_has_article_children",
    )
    has_article_children = fields.Boolean(
        string="Has normal article children?",
        compute="_compute_has_article_children",
    )
    is_desynchronized = fields.Boolean(
        string="Desyncronized with parents",
        help="If set, this article won't inherit access rules from its parents anymore.",
    )
    sequence = fields.Integer(
        default=0,
        help="The sequence is computed only among the articles that have the same parent.",
    )
    root_article_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Menu Article",
        compute="_compute_root_article_id",
        compute_sudo=True,
        recursive=True,
        store=True,
        tracking=10,
        help="The subject is the title of the highest parent in the article hierarchy.",
    )
    is_article_item = fields.Boolean(
        string="Is Item?",
        index=True,
    )
    stage_id = fields.Many2one(
        comodel_name="knowledge.article.stage",
        string="Item Stage",
        compute="_compute_stage_id",
        store=True,
        readonly=False,
        group_expand="_read_group_stage_ids",
        domain="[('parent_id', '=', parent_id)]",
        tracking=True,
    )

    category = fields.Selection(
        selection=[
            ("workspace", "Workspace"),
            ("private", "Private"),
            ("shared", "Shared"),
        ],
        string="Section",
        compute="_compute_category_id",
        compute_sudo=True,
        store=True,
        index=True,
        help="Used to categorize articles in UI, depending on their main permission definitions.",
    )
    last_edition_uid = fields.Many2one(
        comodel_name="res.users",
        string="Last Edited by",
        copy=False,
        readonly=True,
    )
    last_edition_date = fields.Datetime(
        string="Last Edited on",
        copy=False,
        readonly=True,
    )
    last_edition_user_avatar = fields.Image(
        related="last_edition_uid.avatar_128",
        string="Last Editor's Avatar",
    )
    is_user_favorite = fields.Boolean(
        string="Is Favorited",
        compute="_compute_is_user_favorite",
        search="_search_is_user_favorite",
        order_by_sql="_order_by_sql_is_user_favorite",
    )
    user_favorite_sequence = fields.Integer(compute="_compute_is_user_favorite")
    favorite_ids = fields.One2many(
        comodel_name="knowledge.article.favorite",
        inverse_name="article_id",
        string="Favorite Articles",
        copy=False,
    )
    favorite_count = fields.Integer(
        string="#Is Favorite",
        compute="_compute_favorite_count",
        default=0,
        store=True,
        copy=False,
    )
    is_article_visible_by_everyone = fields.Boolean(
        string="Can everyone see the Article?",
        compute="_compute_is_article_visible_by_everyone",
        recursive=True,
        store=True,
        readonly=False,
    )
    is_article_visible = fields.Boolean(
        string="Can the user see the article?",
        compute="_compute_is_article_visible",
        search="_search_is_article_visible",
        recursive=True,
    )
    to_delete = fields.Boolean(
        string="Trashed",
        tracking=100,
        help="""When sent to trash, articles are flagged to be deleted
                days after last edit. knowledge.knowledge_article_trash_limit_days config
                parameter can be used to modify the number of days.
                (default is 30)""",
    )
    deletion_date = fields.Date(compute="_compute_deletion_date")
    article_properties_definition = fields.PropertiesDefinition(
        string="Article Item Properties"
    )
    article_properties = fields.Properties(
        definition="parent_id.article_properties_definition",
        string="Properties",
        copy=True,
    )

    is_listed_in_templates_gallery = fields.Boolean(
        string="Is listed in Templates Gallery?",
        help="If checked, the article will appear in the templates gallery under the 'Shared Templates' section",
    )
    is_template = fields.Boolean()
    template_body = fields.Text(translate=html_translate)
    template_category_id = fields.Many2one(
        comodel_name="knowledge.article.template.category",
        compute="_compute_template_category_id",
        inverse="_inverse_template_category_id",
        recursive=True,
        store=True,
    )
    template_category_sequence = fields.Integer(
        related="template_category_id.sequence",
        string="Template Category Sequence",
    )
    template_description = fields.Char(translate=True)
    template_name = fields.Char(
        string="Template Title",
        translate=True,
    )
    template_preview = fields.Html(compute="_compute_template_preview")
    template_sequence = fields.Integer(
        help="It determines the display order of the template within its category"
    )
    template_child_default_create = fields.Boolean(
        string="Auto-Create Child Article",
        default=True,
        help="If set, this will automatically create this child article when its parent template is used",
    )
    origin_template_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Template used to generate the article",
    )

    _check_desync_on_root = models.Constraint(
        "check(parent_id IS NOT NULL OR is_desynchronized IS NOT TRUE)",
        "Root articles cannot be desynchronized.",
    )
    _check_article_item_parent = models.Constraint(
        "check(is_article_item IS NOT TRUE OR parent_id IS NOT NULL)",
        "Article items must have a parent.",
    )
    _check_trash = models.Constraint(
        "check(to_delete IS NOT TRUE or active IS NOT TRUE)",
        "Trashed articles must be archived.",
    )
    _check_template_category_on_root = models.Constraint(
        "check(is_template IS NOT TRUE OR parent_id IS NOT NULL OR template_category_id IS NOT NULL)",
        "Root templates must have a category.",
    )
    _check_template_name_required = models.Constraint(
        "check(is_template IS NOT TRUE OR template_name IS NOT NULL)",
        "Templates should have a name.",
    )

    def init(self) -> None:
        super().init()

        self.env.cr.execute("""
            SELECT 1 FROM pg_ts_config WHERE cfgname = 'knowledge_config';
        """)

        if not self.env.cr.rowcount:
            self.env.cr.execute("""
                CREATE TEXT SEARCH CONFIGURATION knowledge_config
                    (PARSER = pg_catalog.default);
            """)

            self.env.cr.execute("""
                CREATE TEXT SEARCH DICTIONARY knowledge_dictionary
                    (TEMPLATE = pg_catalog.simple);
            """)

            self.env.cr.execute("""
                ALTER TEXT SEARCH CONFIGURATION knowledge_config
                    ALTER MAPPING FOR
                        asciiword, word, numword, asciihword, hword, numhword,
                        hword_asciipart, hword_part, hword_numpart, email, protocol,
                        url, host, url_path, file, sfloat, float, int, uint, version
                    WITH knowledge_dictionary;
            """)

            create_index(
                self.env.cr,
                get_index_name(self._table, "body"),
                self._table,
                ["to_tsvector('knowledge_config', body)"],
                method="GIN",
            )

    @api.constrains("internal_permission", "article_member_ids")
    def _check_is_writable(self) -> None:
        for article in self:
            if (
                article.inherited_permission != "write"
                and not article._has_write_member()
            ):
                raise ValidationError(
                    self.env._(
                        "The article '%s' needs at least one member with 'Write' access.",
                        article.display_name,
                    )
                )

    @api.constrains("parent_id")
    def _check_parent_id_recursion(self) -> None:
        if self._has_cycle():
            raise ValidationError(
                self.env._(
                    "Articles %s cannot be updated as this would create a recursive hierarchy.",
                    ", ".join(self.mapped("name")),
                )
            )

    @api.constrains("is_template", "parent_id")
    def _check_template_hierarchy(self) -> None:
        for article in self:
            if not article.parent_id:
                continue
            if article.is_template and not article.parent_id.is_template:
                raise ValidationError(
                    self.env._(
                        '"%(article_name)s" is a template and can not be a child of an article ("%(parent_article_name)s").',
                        article_name=article.name,
                        parent_article_name=article.parent_id.name,
                    )
                )
            if not article.is_template and article.parent_id.is_template:
                raise ValidationError(
                    self.env._(
                        '"%(article_name)s" is an article and can not be a child of a template ("%(parent_article_name)s")."',
                        article_name=article.name,
                        parent_article_name=article.parent_id.name,
                    )
                )

    def _compute_article_url(self) -> None:
        for article in self:
            if not article.ids:
                article.article_url = False
            else:
                article.article_url = url_join(
                    article.get_base_url(), "knowledge/article/%s" % article.id
                )

    @api.depends("child_ids", "child_ids.is_article_item")
    def _compute_has_article_children(self) -> None:
        results = self.env["knowledge.article"]._read_group(
            [("parent_id", "in", self.ids)], ["parent_id", "is_article_item"]
        )
        count_by_article_id = {
            (parent.id, is_article_item) for parent, is_article_item in results
        }
        for article in self:
            article.has_item_children = (article.id, True) in count_by_article_id
            article.has_article_children = (article.id, False) in count_by_article_id

    @api.depends("parent_id", "parent_id.root_article_id")
    def _compute_root_article_id(self) -> None:
        wparent = self.filtered("parent_id")
        for article in self - wparent:
            article.root_article_id = article

        if not wparent:
            return
        articles_byparent = defaultdict(lambda: self.env["knowledge.article"])
        for article in wparent:
            articles_byparent[article.parent_id] += article

        for parent, articles in articles_byparent.items():
            ancestors = self.env["knowledge.article"]
            while parent:
                if parent in ancestors:
                    raise ValidationError(
                        self.env._(
                            "Articles %s cannot be updated as this would create a recursive hierarchy.",
                            ", ".join(articles.mapped("name")),
                        )
                    )
                ancestors += parent
                parent = parent.parent_id
            articles.root_article_id = ancestors[-1:]

    @api.depends("parent_id", "is_article_item")
    def _compute_stage_id(self) -> None:
        articles = self.filtered(lambda article: not article.is_article_item)
        articles.stage_id = False
        if articles == self:
            return

        items = self - articles
        results = self.env["knowledge.article.stage"].search_read(
            [("parent_id", "in", items.parent_id.ids)], ["parent_id", "id"]
        )
        stages_by_parent_id = {}
        for result in results:
            parent_id = result["parent_id"][0] if result.get("parent_id") else False
            if parent_id and not stages_by_parent_id.get(parent_id):
                stages_by_parent_id[parent_id] = result["id"]
        for item in items:
            item.stage_id = stages_by_parent_id.get(item.parent_id.id)

    @api.depends("parent_id.template_category_id")
    def _compute_template_category_id(self) -> None:
        self._inherit_template_category_id()

    def _inverse_template_category_id(self) -> None:
        self._inherit_template_category_id()

    def _inherit_template_category_id(self) -> None:
        children = self.filtered("parent_id")
        _debug.logic(
            "template_category.inherited",
            articles=len(self),
            children=len(children),
        )
        for article in children:
            article.template_category_id = article.parent_id.template_category_id

    @api.depends("template_body")
    def _compute_template_preview(self) -> None:
        for template in self:
            template.template_preview = template._render_template()

    @api.model
    def _internal_audience_group(self):
        return self.env.ref("base.group_user").id

    def _own_audience_grant(self):
        self.check_singleton()
        audience = self._internal_audience_group()
        return self.access_grant_ids.filtered(
            lambda grant: grant.group_id.id == audience and not grant.company_id
        )

    @api.depends(
        "access_grant_ids.group_id",
        "access_grant_ids.permission",
        "parent_id",
        "is_desynchronized",
    )
    def _compute_internal_permission(self) -> None:
        for article in self:
            grant = article.id and article._own_audience_grant()
            if not article.id:
                article.internal_permission = False
            elif grant:
                article.internal_permission = grant.permission
            elif not article.parent_id or article.is_desynchronized:
                article.internal_permission = "none"
            else:
                article.internal_permission = False

    def _inverse_internal_permission(self) -> None:
        self._set_audience(
            {article.id: article.internal_permission for article in self}
        )

    def _set_audience(self, levels) -> None:
        audience = self._internal_audience_group()
        for article in self.with_privilege("knowledge.privilege_share_articles"):
            level = levels[article.id]
            if (
                level
                and article.parent_id
                and not article.is_desynchronized
                and ARTICLE_PERMISSION_LEVEL[level]
                < ARTICLE_PERMISSION_LEVEL[article.parent_id.inherited_permission]
            ):
                article.write(
                    article._desync_access_from_parents_values(
                        force_internal_permission=level
                    )
                )
                continue
            grant = article._own_audience_grant()
            Grant = article.env["knowledge.article.member"]
            if level in ("read", "write"):
                if grant:
                    grant.permission = level
                else:
                    Grant.create(
                        {
                            "article_id": article.id,
                            "group_id": audience,
                            "permission": level,
                            "cause": "manual",
                        }
                    )
            elif grant:
                grant.unlink()
        self.invalidate_recordset(
            ["internal_permission", "inherited_permission", "user_permission"]
        )

    def _search_internal_permission(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        audience = self._internal_audience_group()
        levels = {level for level in value if level}
        own = {
            level: Domain(
                "access_grant_ids",
                "any",
                Domain("group_id", "=", audience)
                & Domain("company_id", "=", False)
                & Domain("permission", "=", level),
            )
            for level in ("read", "write")
        }
        no_own = ~(own["read"] | own["write"])
        not_inheriting = Domain("parent_id", "=", False) | Domain(
            "is_desynchronized", "=", True
        )
        bands = {
            "read": own["read"],
            "write": own["write"],
            "none": no_own & not_inheriting,
        }
        domain = Domain.OR(bands[level] for level in levels if level in bands)
        if False in value:
            domain |= no_own & ~not_inheriting
        return domain if operator == "in" else ~domain

    @api.depends(
        "access_scope_path",
        "access_grant_ids.group_id",
        "access_grant_ids.permission",
        "internal_permission",
        "parent_id",
    )
    def _compute_inherited_permission(self) -> None:
        audience = self._internal_audience_group()
        saved = self.filtered("id")
        ranks = saved._access_graph_group_ranks(audience)
        levels = ("none", "read", "write")
        for article in self:
            if article.id:
                article.inherited_permission = levels[ranks.get(article.id, 0)]
            else:
                article.inherited_permission = article.parent_id.inherited_permission
            node = article
            while node and not node.internal_permission:
                node = node.parent_id
            article.inherited_permission_parent_id = (
                node if node and node != article else False
            )

    def _search_inherited_permission(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        reach = {
            role: self._access_graph_domain(
                role,
                groups=[self._internal_audience_group()],
                partner=False,
                owner=False,
            )
            for role in ("read", "write")
        }
        bands = {
            "none": ~reach["read"],
            "read": reach["read"] & ~reach["write"],
            "write": reach["write"],
        }
        domain = Domain.OR(bands[level] for level in value if level in bands)
        return domain if operator == "in" else ~domain

    @api.depends_context("uid")
    @api.depends("access_role")
    def _compute_user_permission(self) -> None:
        if self.env.user._is_public():
            self.user_permission = False
            return
        transient = self.filtered(lambda article: not article.ids)
        transient.user_permission = "write"
        for article in self - transient:
            article.user_permission = article.access_role or "none"

    @api.depends_context("uid")
    @api.depends("user_permission")
    def _compute_user_has_access(self) -> None:
        for article in self:
            article.user_has_access = (
                article.user_permission != "none" if article.user_permission else False
            )

    def _search_user_has_access(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        domain = (
            self._access_graph_domain("read") & self._access_label_reach("read")
        ) | self._reach_to_write()
        return domain if operator == "in" else ~domain

    def _reach_to_write(self):
        return self._access_graph_domain("write") & self._access_label_reach("write")

    @api.depends_context("uid")
    @api.depends("user_has_access", "parent_id.user_has_access_parent_path")
    def _compute_user_has_access_parent_path(self) -> None:
        roots = self.filtered(lambda article: not article.parent_id)
        for article in roots:
            article.user_has_access_parent_path = article.user_has_access
        children = self - roots
        ancestor_ids = {
            article: article._get_ancestor_ids_nearest_first() for article in children
        }
        every_ancestor = tuple(
            dict.fromkeys(id_ for ids in ancestor_ids.values() for id_ in ids)
        )
        for article in children:
            ancestors = (
                self.env["knowledge.article"]
                .browse(ancestor_ids[article])
                .with_prefetch(every_ancestor)
            )
            article.user_has_access_parent_path = not any(
                not ancestor.user_has_access for ancestor in ancestors
            )

    @api.depends_context("uid")
    @api.depends("user_permission")
    def _compute_user_has_write_access(self) -> None:
        for article in self:
            article.user_has_write_access = article.user_permission == "write"

    def _search_user_has_write_access(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        domain = self._reach_to_write()
        return domain if operator == "in" else ~domain

    @api.depends_context("uid")
    @api.depends("user_has_access")
    def _compute_user_can_read(self) -> None:
        if self.env.is_system():
            self.user_can_read = True
        else:
            readable = self.filtered_domain(self._get_domain_read())
            readable.user_can_read = True
            (self - readable).user_can_read = False

    @api.depends_context("uid")
    @api.depends("user_has_write_access")
    def _compute_user_can_write(self) -> None:
        if self.env.is_system():
            self.user_can_write = True
        else:
            for article in self:
                article.user_can_write = article.user_has_write_access

    @api.depends(
        "root_article_id.access_grant_ids.group_id",
        "root_article_id.access_grant_ids.partner_id",
        "root_article_id.access_grant_ids.permission",
    )
    def _compute_category_id(self) -> None:
        audience = self._internal_audience_group()
        for article in self:
            grants = article.root_article_id.access_grant_ids
            if grants.filtered(lambda grant: grant.group_id.id == audience):
                article.category = "workspace"
            elif len(grants.filtered("partner_id")) > 1:
                article.category = "shared"
            else:
                article.category = "private"

    @api.depends("favorite_ids")
    def _compute_favorite_count(self) -> None:
        favorites = self.env["knowledge.article.favorite"]._read_group(
            [("article_id", "in", self.ids)], ["article_id"], ["__count"]
        )
        favorites_count_by_article = {article.id: count for article, count in favorites}
        for article in self:
            article.favorite_count = favorites_count_by_article.get(article.id, 0)

    @api.depends_context("uid")
    @api.depends("favorite_ids.user_id")
    def _compute_is_user_favorite(self) -> None:
        if self.env.user._is_public():
            self.is_user_favorite = False
            return
        favorites = self.env["knowledge.article.favorite"].search(
            [
                ("article_id", "in", self.ids),
                ("user_id", "=", self.env.user.id),
            ]
        )
        not_fav_articles = self - favorites.article_id
        fav_articles = self - not_fav_articles
        fav_sequence_by_article = {f.article_id.id: f.sequence for f in favorites}
        if not_fav_articles:
            not_fav_articles.is_user_favorite = False
            not_fav_articles.user_favorite_sequence = -1
        if fav_articles:
            fav_articles.is_user_favorite = True
        for fav_article in fav_articles:
            fav_article.user_favorite_sequence = fav_sequence_by_article[fav_article.id]

    def _search_is_user_favorite(self, operator, value):
        if operator != "in":
            return NotImplemented
        return [
            (
                "favorite_ids",
                "in",
                self.env["knowledge.article.favorite"]
                .sudo()
                ._search([("user_id", "=", self.env.uid)]),
            )
        ]

    @api.depends(
        "is_article_visible_by_everyone",
        "article_member_ids",
        "root_article_id.article_member_ids",
    )
    @api.depends_context("uid")
    def _compute_is_article_visible(self) -> None:
        visible_articles = (
            self.filtered(lambda article: article.is_article_visible_by_everyone)
            if self.env.user._is_internal()
            else self.env["knowledge.article"]
        )
        visible_articles.is_article_visible = True
        if visible_articles == self:
            return

        member_only_articles = self - visible_articles
        results = self.env["knowledge.article.member"]._read_group(
            domain=[("partner_id", "=", self.env.user.partner_id.id)],
            groupby=["partner_id", "article_id"],
        )

        pids_by_article = defaultdict(list)
        for partner, article in results:
            pids_by_article[article.id].append(partner.id)

        current_pid = self.env.user.partner_id.id
        for article in member_only_articles:
            article.is_article_visible = current_pid in (
                pids_by_article[article.id]
                + pids_by_article[article.root_article_id.id]
            )

    def _search_is_article_visible(self, operator, value):
        if self.env.user._is_public():
            return Domain.FALSE
        if operator != "in":
            return NotImplemented
        members_from_partner = self.env["knowledge.article.member"]._search(
            [("partner_id", "=", self.env.user.partner_id.id)]
        )
        members_domain = Domain(
            "article_member_ids", "in", members_from_partner
        ) | Domain("root_article_id.article_member_ids", "in", members_from_partner)
        if not self.env.user._is_internal():
            return members_domain
        return Domain("is_article_visible_by_everyone", "=", True) | members_domain

    @api.depends("root_article_id.is_article_visible_by_everyone")
    def _compute_is_article_visible_by_everyone(self) -> None:
        root_articles = self.filtered(lambda article: not article.parent_id)
        for article in self - root_articles:
            article.is_article_visible_by_everyone = (
                article.root_article_id.is_article_visible_by_everyone
            )
        root_articles.is_article_visible_by_everyone = False

    @api.depends("to_delete", "write_date")
    def _compute_deletion_date(self) -> None:
        trashed_articles = self.filtered(lambda article: article.to_delete)
        (self - trashed_articles).deletion_date = False
        if trashed_articles:
            limit_days = self.env.registry.settings.get(
                self.env, "knowledge.knowledge_article_trash_limit_days", False
            )
            try:
                limit_days = int(limit_days)
            except ValueError:
                limit_days = self.DEFAULT_ARTICLE_TRASH_LIMIT_DAYS
            for article in trashed_articles:
                article.deletion_date = article.write_date + timedelta(days=limit_days)

    def _order_by_sql_is_user_favorite(
        self, field, alias, direction, nulls, query
    ) -> SQL:
        sql_field = SQL(
            "%s IN (SELECT article_id FROM knowledge_article_favorite WHERE user_id = %s)",
            SQL.identifier(alias, "id"),
            self.env.uid,
        )
        return self._order_value_to_sql(sql_field, direction, nulls, query)

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(
            ["article_member_ids", "internal_permission", "parent_id"]
        )
        vals_by_parent_id = {}
        vals_as_sudo = []
        rechecked = set()
        writerless = []
        child_levels = {}
        children_by_index = {}
        parent_ids = set()

        for index, vals in enumerate(vals_list):
            if not vals.get("is_template", False) and "body" not in vals:
                vals["body"] = (
                    Markup("<h1>%s</h1>") % vals["name"]
                    if vals.get("name")
                    else Markup('<h1 class="oe-hint"><br></h1>')
                )

            vals.update(
                {
                    "last_edition_date": fields.Datetime.now(),
                    "last_edition_uid": self.env.user.id,
                }
            )

            can_sudo = False
            member_ids = (
                vals.get("article_member_ids")
                or defaults.get("article_member_ids")
                or False
            )
            internal_permission = (
                vals.get("internal_permission")
                or defaults.get("internal_permission")
                or False
            )
            parent_id = vals.get("parent_id") or defaults.get("parent_id") or False
            if parent_id:
                parent_ids.add(parent_id)

            if not self.env.user._is_internal() and not self.env.su:
                if not parent_id and internal_permission != "none":
                    raise AccessError(
                        self.env._(
                            "Only internal users are allowed to create workspace root articles."
                        )
                    )

                if (
                    internal_permission != "none"
                    and "is_article_visible_by_everyone" in vals
                ):
                    del vals["is_article_visible_by_everyone"]

            if not parent_id and not internal_permission:
                vals.update(
                    {
                        "internal_permission": "write",
                        "parent_id": False,
                    }
                )

            level = vals.pop("internal_permission", None) or internal_permission
            if parent_id:
                if level:
                    child_levels[index] = level
            elif level not in ("read", "write") and not member_ids:
                writerless.append(vals.get("name") or "")
            elif level in ("read", "write"):
                vals["access_grant_ids"] = [
                    *vals.get("access_grant_ids", []),
                    *vals.pop("article_member_ids", []),
                    Command.create(
                        {
                            "group_id": self._internal_audience_group(),
                            "permission": level,
                            "cause": "manual",
                        }
                    ),
                ]

            check_for_sudo = (
                not self.env.su
                and not self.env.user._is_system()
                and not any(fname in vals for fname in ["favorite_ids", "child_ids"])
                and not parent_id
                and member_ids
                and len(member_ids) == 1
            )
            if check_for_sudo:
                self_member = (
                    member_ids[0][0] == Command.CREATE
                    and member_ids[0][2].get("partner_id")
                    == self.env.user.partner_id.id
                )
                if self_member:
                    can_sudo = True
            elif (
                not self.env.su
                and not self.env.user._is_system()
                and not parent_id
                and not member_ids
                and "access_grant_ids" in vals
                and "favorite_ids" not in vals
                and all(
                    command[0] == Command.CREATE
                    for command in vals.get("child_ids", [])
                )
            ):
                can_sudo = True
                rechecked.add(index)
                if children := vals.pop("child_ids", None):
                    children_by_index[index] = [command[2] for command in children]

            if not vals.get("sequence"):
                vals_by_parent_id.setdefault(parent_id, []).append(vals)
            vals_as_sudo.append(can_sudo)

        if parent_ids:
            if not self.browse(parent_ids).has_access("write"):
                raise AccessError(
                    self.env._(
                        "You cannot create an article under articles on which you cannot write"
                    )
                )

        max_sequence_by_parent = {}
        if vals_by_parent_id:
            parent_ids = list(vals_by_parent_id.keys())
            max_sequence_by_parent = self._get_max_sequence_inside_parents(parent_ids)

        for parent_id, article_vals in vals_by_parent_id.items():
            current_sequence = 0
            if parent_id in max_sequence_by_parent:
                current_sequence = max_sequence_by_parent[parent_id] + 1

            for vals in article_vals:
                if "sequence" in vals:
                    current_sequence = vals.get("sequence")
                else:
                    vals["sequence"] = current_sequence
                    current_sequence += 1

        if all(vals_as_sudo) or writerless:
            self.check_access("create")
        if writerless:
            raise ValidationError(
                self.env._(
                    "The article '%s' needs at least one member with 'Write' access.",
                    writerless[0],
                )
            )

        creator = self.with_context(
            {
                key: value
                for key, value in self.env.context.items()
                if key != "default_internal_permission"
            }
        )
        notsudo_articles = iter(
            super(KnowledgeArticle, creator).create(
                [
                    vals
                    for vals, can_sudo in zip(vals_list, vals_as_sudo, strict=False)
                    if not can_sudo
                ]
            )
        )
        sudo_articles = iter(
            super(KnowledgeArticle, creator.sudo())
            .create(
                [
                    vals
                    for vals, can_sudo in zip(vals_list, vals_as_sudo, strict=False)
                    if can_sudo
                ]
            )
            .with_env(self.env)
        )
        articles = self.env["knowledge.article"]
        for is_sudo in vals_as_sudo:
            if is_sudo:
                articles += next(sudo_articles)
            else:
                articles += next(notsudo_articles)
        articles.browse(
            [articles.ids[index] for index in sorted(rechecked)]
        ).check_access("create")
        for index, level in child_levels.items():
            articles[index]._set_audience({articles[index].id: level})
        if children_by_index:
            self.create(
                [
                    dict(child_vals, parent_id=articles[index].id)
                    for index, children in children_by_index.items()
                    for child_vals in children
                ]
            )

        if any(articles.mapped("is_template")) and not self.env.user.has_group(
            "base.group_system"
        ):
            raise ValidationError(
                self.env._("You are not allowed to create a new template.")
            )

        return articles

    def write(self, vals):
        if any(article.is_template for article in self) and not self.env.user.has_group(
            "base.group_system"
        ):
            raise ValidationError(
                self.env._("You are not allowed to update a template.")
            )
        if any(
            article.is_template != vals.get("is_template", False) for article in self
        ) and not self.env.user.has_group("base.group_system"):
            raise ValidationError(
                self.env._(
                    "You are not allowed to update the type of a article or a template."
                )
            )

        _resequence = False
        if not self.env.user._is_internal() and not self.env.su:
            writable_fields = self._get_portal_write_fields_allowlist()
            if all(article.category == "private" for article in self):
                writable_fields |= {"active", "to_delete", "parent_id"}

            if vals.keys() - writable_fields:
                raise AccessError(
                    self.env._(
                        "Only internal users are allowed to modify this information."
                    )
                )

        if "body" in vals:
            if len(self) == 1:
                handle_history_divergence(self, "body", vals)
            vals.update(
                {
                    "last_edition_date": fields.Datetime.now(),
                    "last_edition_uid": self.env.user.id,
                }
            )
        else:
            vals.pop("last_edition_date", False)
            vals.pop("last_edition_uid", False)

        if "parent_id" in vals:
            parent = self.env["knowledge.article"]
            if vals.get("parent_id") and self.filtered(
                lambda r: r.parent_id.id != vals["parent_id"]
            ):
                parent = self.browse(vals["parent_id"])
                if not parent.has_access("write"):
                    raise AccessError(
                        self.env._(
                            "You cannot move an article under %(parent_name)s as you cannot write on it",
                            parent_name=parent.display_name,
                        )
                    )
            if "sequence" not in vals:
                max_sequence = self._get_max_sequence_inside_parents(parent.ids).get(
                    parent.id, -1
                )
                vals["sequence"] = max_sequence + 1
            else:
                _resequence = True

        result = super().write(vals)
        if "internal_permission" in vals:
            self.invalidate_recordset(
                ["internal_permission", "inherited_permission", "user_permission"]
            )
        if "parent_id" in vals and not vals["parent_id"]:
            self._check_is_writable()

        if _resequence:
            self.sudo()._resequence()

        return result

    @api.ondelete(at_uninstall=False)
    def _check_template_deletion(self) -> None:
        if self.filtered("is_template") and not self.env.user.has_group(
            "base.group_system"
        ):
            raise ValidationError(
                self.env._("You are not allowed to delete a template.")
            )

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        for article, vals in zip(self, vals_list, strict=True):
            vals.setdefault("internal_permission", article.internal_permission)
        if default.get("name"):
            return vals_list
        for article, vals in zip(self, vals_list, strict=False):
            if article.name:
                vals["name"] = (
                    article.name
                    if article.parent_id
                    else self.env._(
                        "%(article_name)s (copy)", article_name=article.name
                    )
                )
        return vals_list

    def copy_batch(self, default=None):
        current_ids = set(self.ids)
        to_copy = self.filtered(
            lambda article: not article._get_ancestor_ids_nearest_first() & current_ids
        )

        duplicates = self.create(
            [
                article.with_context(active_test=False).copy_data(default=default)[0]
                for article in to_copy
            ]
        )
        for old, new in zip(to_copy, duplicates, strict=False):
            old.copy_translations(
                new,
                excluded=list(default.keys() if default else [])
                + ["name", "article_member_ids", "favorite_ids"],
            )

        return duplicates

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        search_domain = Domain("id", "in", stages.ids)
        if self.env.context.get("default_parent_id"):
            search_domain = (
                Domain("parent_id", "=", self.env.context["default_parent_id"])
                | search_domain
            )
        return stages.search(search_domain)

    def _get_domain_read(self):
        return [("user_has_access", "=", True)]

    @api.model
    def _get_portal_write_fields_allowlist(self) -> set:
        return {
            "article_properties",
            "article_properties_definition",
            "body",
            "full_width",
            "icon",
            "is_article_item",
            "is_locked",
            "name",
            "sequence",
            "stage_id",
        }

    _GC_TRASH_BATCH_SIZE = 100

    @api.autovacuum
    def _gc_trashed_articles(self) -> tuple:
        limit_days = self.env.registry.settings.get(
            self.env, "knowledge.knowledge_article_trash_limit_days", False
        )
        try:
            limit_days = int(limit_days)
        except ValueError:
            limit_days = self.DEFAULT_ARTICLE_TRASH_LIMIT_DAYS
        timeout_ago = datetime.now(UTC) - timedelta(days=limit_days)
        domain = [("write_date", "<", timeout_ago), ("to_delete", "=", True)]
        trashed = self.with_context(active_test=False).search(
            domain, limit=self._GC_TRASH_BATCH_SIZE
        )
        trashed.unlink()
        return len(trashed), len(trashed) == self._GC_TRASH_BATCH_SIZE

    def action_archive(self):
        self._action_archive_articles()

    @api.model
    def name_create(self, name):

        article_name, icon = self._extract_icon_from_name(name)
        if not icon:
            return super().name_create(name)

        record = self.create(
            {
                "name": article_name,
                "icon": icon,
            }
        )
        return record.id, record.display_name

    @api.depends("name", "template_name", "icon", "is_template")
    def _compute_display_name(self):
        for rec in self:
            name = (rec.template_name if rec.is_template else rec.name) or self.env._(
                "Untitled"
            )
            rec.display_name = f"{rec.icon or self._get_no_icon_placeholder()} {name}"

    def _get_no_icon_placeholder(self) -> str:
        return "📄"

    @api.model
    def _search_display_name(self, operator, value):

        if operator == "in":
            return Domain.OR(self._search_display_name("=", v) for v in value)
        if operator == "not in":
            return NotImplemented
        if operator not in ("=", "ilike") or not isinstance(value, str):
            return super()._search_display_name(operator, value)

        article_name, icon = self._extract_icon_from_name(value)
        if not icon:
            if operator == "=":
                operator = "in"
                value = [value]
            return super()._search_display_name(operator, value)

        if icon == self._get_no_icon_placeholder():
            domain = [
                ("name", operator, article_name),
                "|",
                ("icon", "=", icon),
                ("icon", "=", False),
            ]
        else:
            domain = [
                ("name", operator, article_name),
                ("icon", "=", icon),
            ]

        return domain

    def _get_transformed_body_from(self, source_article):
        fragment = html.fragment_fromstring(source_article.body, create_parent=True)

        for element in fragment.findall(".//*[@data-last-history-steps]"):
            del element.attrib["data-last-history-steps"]

        for element in fragment.findall(".//*[@data-embedded='view']"):
            embedded_props = json_loads(element.get("data-embedded-props"))
            view_props = embedded_props.get("viewProps", {})
            context = view_props.get("context", {})
            if (
                context.get("default_is_article_item")
                and context.get("active_id") == source_article.id
            ):
                context.update({"active_id": self.id, "default_parent_id": self.id})
                element.set("data-embedded-props", json_dumps(embedded_props))

        return html.tostring(fragment, encoding="unicode")

    def action_make_private_copy(self, preserve_name=False):
        self.check_singleton()
        name = (
            self.env._("%(article_name)s (copy)", article_name=self.name)
            if not preserve_name and self.name
            else self.name
        )

        article = self.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    Command.create(
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        }
                    )
                ],
                "article_properties_definition": self.article_properties_definition,
                "cover_image_id": self.cover_image_id.id,
                "cover_image_position": self.cover_image_position,
                "full_width": self.full_width,
                "icon": self.icon,
                "internal_permission": "none",
                "name": name,
            }
        )

        article.write({"body": article._get_transformed_body_from(self)})

        stages_mapping = {}
        for stage in self.env["knowledge.article.stage"].search(
            [("parent_id", "=", self.id)]
        ):
            new_stage = stage.copy({"parent_id": article.id})
            stages_mapping[stage.id] = new_stage.id

        article_items = self.child_ids.filtered(lambda article: article.is_article_item)
        self.env["knowledge.article"].create(
            [
                {
                    "article_properties": article_item.article_properties,
                    "body": article_item.body,
                    "cover_image_id": article_item.cover_image_id.id,
                    "cover_image_position": article_item.cover_image_position,
                    "full_width": article_item.full_width,
                    "icon": article_item.icon,
                    "is_article_item": True,
                    "name": article_item.name,
                    "parent_id": article.id,
                    "stage_id": stages_mapping.get(article_item.stage_id.id, False),
                }
                for article_item in article_items.sorted(lambda child: child.sequence)
            ]
        )

        return article

    def action_make_copy(self, preserve_name=False):
        self.check_singleton()
        article = self.action_make_private_copy(preserve_name)
        if self.parent_id and self.parent_id.user_can_write:
            article.write(
                {
                    "parent_id": self.parent_id.id,
                }
            )
        return article

    def action_home_page(self):
        article = self[0] if self else False
        if not article and self.env.context.get("res_id", False):
            article = self.browse([self.env.context["res_id"]])
            if not article.exists():
                raise UserError(
                    self.env._("The Article you are trying to access has been deleted")
                )
        if not article:
            article = self._get_first_accessible_article()

        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "knowledge.knowledge_article_action_form"
        )
        action["res_id"] = article.id
        return action

    def action_redirect_to_parent(self):
        self.check_singleton()
        return (
            self.parent_id.action_home_page()
            if self.parent_id and self.parent_id.user_has_access
            else self.env["knowledge.article"].action_home_page()
        )

    def action_set_lock(self, lock) -> None:
        self.is_locked = lock

    def action_toggle_user_favorite(self):
        if not self.has_access("read"):
            raise AccessError(
                self.env._("You cannot add or remove this article to your favorites")
            )

        to_favorite_sudo = self.sudo().filtered(
            lambda article: not article.is_user_favorite
        )
        to_unfavorite = self - to_favorite_sudo
        to_favorite_sudo.write(
            {"favorite_ids": [Command.create({"user_id": self.env.user.id})]}
        )
        if to_unfavorite:
            self.env["knowledge.article.favorite"].sudo().search(
                [
                    ("article_id", "in", to_unfavorite.ids),
                    ("user_id", "=", self.env.user.id),
                ]
            ).unlink()
        self.invalidate_recordset(fnames=["is_user_favorite", "favorite_ids"])
        return self[0].is_user_favorite if self else False

    def action_send_to_trash(self) -> None:
        self._action_archive_articles(send_to_trash=True)

    def _action_archive_articles(self, send_to_trash=False) -> None:
        articles = self + self._detach_unwritable_descendants().with_env(self.env)
        articles.filtered("active").active = False
        if send_to_trash:
            articles.to_delete = True
            articles._send_trash_notifications()

    def action_unarchive(self):
        for article_item in self.filtered(
            lambda article: (
                article.is_article_item
                and article.parent_id not in self
                and article.parent_id.sudo().to_delete
            )
        ):
            raise UserError(
                self.env._(
                    '"%(article_item_name)s" is an Article Item from "%(article_name)s" and cannot be restored on its own. Contact the owner of "%(article_name)s" to have it restored instead.',
                    article_item_name=article_item.display_name,
                    article_name=article_item.parent_id.display_name,
                )
            )

        writable_descendants = (
            self.with_context(active_test=False)
            ._detach_unwritable_descendants()
            .with_env(self.env)
        )
        articles_to_restore = self + writable_descendants
        articles_to_restore.filtered("to_delete").to_delete = False
        super(KnowledgeArticle, articles_to_restore).action_unarchive()
        for article_sudo in self.sudo().filtered(
            lambda article: article.parent_id.to_delete
        ):
            write_values = article_sudo._desync_access_from_parents_values()
            write_values.update({"parent_id": False, "is_desynchronized": False})
            article_sudo.write(write_values)

    def action_join(self):
        self.check_singleton()
        current_user = self.env.user
        if (
            current_user.share
            or not self.user_has_access
            or not self.user_has_access_parent_path
        ):
            raise AccessError(
                self.env._(
                    "You need to have access to this article in order to join its members."
                )
                if not self.parent_id
                else self.env._(
                    "You need to have access to this article's root in order to join its members."
                )
            )
        if self.parent_id:
            self.root_article_id.sudo()._add_members(
                current_user.partner_id, self.root_article_id.internal_permission
            )
            return self.action_home_page()
        else:
            self.sudo()._add_members(current_user.partner_id, self.internal_permission)
            return False

    def move_to(self, parent_id=False, before_article_id=False, category=False):
        self.check_singleton()
        before_article = (
            self.env["knowledge.article"].browse(before_article_id)
            if before_article_id
            else self.env["knowledge.article"]
        )
        parent = (
            self.env["knowledge.article"].browse(parent_id)
            if parent_id
            else self.env["knowledge.article"]
        )
        category = category or parent.category or before_article.category
        if not category:
            raise ValidationError(
                self.env._(
                    "The destination placement of %(article_name)s is ambiguous, you should specify the category.",
                    article_name=self.display_name,
                )
            )
        if (
            category == "shared"
            and not parent
            and (self.parent_id or self.category != "shared")
        ):
            return self._move_and_make_shared_root(before_article=before_article)
        if parent.is_article_item:
            raise ValidationError(
                self.env._(
                    "You can't move %(article_name)s under %(item_name)s, as %(item_name)s is an Article Item. "
                    "Convert %(item_name)s into an Article first.",
                    article_name=self.display_name,
                    item_name=parent.display_name,
                )
            )

        if category == "private":
            return self._move_and_make_private(
                parent=parent, before_article=before_article
            )

        values = {"parent_id": parent_id}
        if before_article:
            values["sequence"] = before_article.sequence
        if parent_id and not self.parent_id:
            values["internal_permission"] = False
        if not parent_id and category == "workspace":
            values.update({"internal_permission": "write", "is_desynchronized": False})

        return self.write(values)

    def _resequence(self) -> None:
        parent_ids = self.mapped("parent_id").ids
        if any(not article.parent_id for article in self):
            parent_ids.append(False)

        all_children = self.search([("parent_id", "in", parent_ids)])
        all_children = all_children.sorted(
            lambda article: (
                -1 * article.sequence,
                article in self,
                article.write_date,
                article.id,
            ),
            reverse=True,
        )

        article_to_update_by_sequence = defaultdict(
            self.env["knowledge.article"].browse
        )
        children_by_parent_id = all_children.grouped(lambda a: a.parent_id.id)
        for parent_id in parent_ids:
            children = children_by_parent_id.get(parent_id, all_children.browse())
            sequences = children.mapped("sequence")
            if len(sequences) == len(set(sequences)):
                return

            duplicate_index = next(
                idx for idx, item in enumerate(sequences) if item in sequences[:idx]
            )
            start_sequence = sequences[duplicate_index] + 1
            for i, child in enumerate(children[duplicate_index:]):
                article_to_update_by_sequence[i + start_sequence] |= child

        for sequence in article_to_update_by_sequence:
            super(KnowledgeArticle, article_to_update_by_sequence[sequence]).write(
                {"sequence": sequence}
            )

    @api.model
    def _get_max_sequence_inside_parents(self, parent_ids) -> dict:
        if parent_ids:
            domain = [("parent_id", "in", parent_ids)]
        else:
            domain = [("parent_id", "=", False)]
        rg_results = (
            self.env["knowledge.article"]
            .sudo()
            ._read_group(domain, ["parent_id"], ["sequence:max"])
        )
        return {parent.id: sequence_max for parent, sequence_max in rg_results}

    @api.model
    def article_create(
        self,
        title=False,
        parent_id=False,
        is_private=False,
        is_article_item=False,
        article_properties=False,
    ) -> Self:
        return self.create(
            self._prepare_article_create_values(
                title, parent_id, is_private, is_article_item, article_properties
            )
        )

    def _prepare_article_create_values(
        self,
        title=False,
        parent_id=False,
        is_private=False,
        is_article_item=False,
        article_properties=False,
    ):
        parent = self.browse(parent_id) if parent_id else self.env["knowledge.article"]
        values = {"is_article_item": is_article_item, "parent_id": parent.id}
        if title:
            values["name"] = title

        if parent:
            if not is_private and parent.category == "private":
                is_private = True
        else:
            values["internal_permission"] = "none" if is_private else "write"

            values["article_member_ids"] = [
                Command.create(
                    {
                        "partner_id": self.env.user.partner_id.id,
                        "permission": "write",
                    }
                )
            ]

        if is_private:
            if parent and parent.category != "private":
                raise ValidationError(
                    self.env._(
                        "Cannot create an article under article %(parent_name)s which is a non-private parent",
                        parent_name=parent.display_name,
                    )
                )

        if is_article_item and article_properties:
            values["article_properties"] = article_properties

        return values

    def get_user_sorted_articles(self, search_query, limit=40, hidden_mode=False):
        domain = Domain(
            [
                ("is_article_visible", "!=", hidden_mode),
                (
                    "user_has_access",
                    "=",
                    True,
                ),
            ]
        )
        if not search_query:
            if not hidden_mode:
                domain = Domain("is_user_favorite", "=", True)
            domain &= Domain("is_template", "=", False)
            return self.search_read(
                domain,
                limit=limit,
                fields=["id", "icon", "name", "is_user_favorite", "root_article_id"],
            )
        return self.get_sorted_articles(search_query, domain, limit)

    def get_sorted_articles(self, search_query, domain=False, limit=40):
        if not search_query:
            return []
        domain = Domain(domain or Domain.TRUE) & Domain("is_template", "=", False)
        query = self._search(domain)

        search_pattern = "%" + re.sub(r"(%|_|\\)", r"\\\1", search_query) + "%"
        ts_query = SQL(
            "plainto_tsquery('knowledge_config', %(search_query)s)",
            search_query=search_query,
        )
        cut_off = max(
            self.env.registry.settings.get(
                self.env, "knowledge.fts_search_cut_off", 100
            ),
            limit,
        )

        self.env.cr.execute(
            SQL(
                """
            WITH
            articles_matching_with_title_and_body AS (
                SELECT knowledge_article.id AS id,
                       1 AS order,
                       ts_rank_cd(to_tsvector('knowledge_config', knowledge_article.name), %(ts_query)s) AS score
                  FROM knowledge_article
                 WHERE knowledge_article.name ILIKE %(search_pattern)s
                   AND to_tsvector('knowledge_config', knowledge_article.body) @@ %(ts_query)s
                   AND %(sql_where_clause)s
                 LIMIT %(cut_off)s
            ),
            articles_matching_with_title AS (
                SELECT knowledge_article.id AS id,
                       2 AS order,
                       1 AS score
                  FROM knowledge_article
                 WHERE knowledge_article.name ILIKE %(search_pattern)s
                   AND knowledge_article.id NOT IN (
                       SELECT id FROM articles_matching_with_title_and_body)
                   AND %(sql_where_clause)s
                 LIMIT %(cut_off)s
                    - (SELECT COUNT(*) FROM articles_matching_with_title_and_body)
            ),
            articles_matching_with_body AS (
                SELECT knowledge_article.id AS id,
                       3 AS order,
                       ts_rank_cd(to_tsvector('knowledge_config', knowledge_article.body), %(ts_query)s) AS score
                  FROM knowledge_article
                 WHERE to_tsvector('knowledge_config', knowledge_article.body) @@ %(ts_query)s
                   AND knowledge_article.id NOT IN (
                        SELECT id FROM articles_matching_with_title_and_body
                        UNION ALL
                        SELECT id FROM articles_matching_with_title)
                   AND %(sql_where_clause)s
                 LIMIT %(cut_off)s
                    - (SELECT COUNT(*) FROM articles_matching_with_title_and_body)
                    - (SELECT COUNT(*) FROM articles_matching_with_title)
            ),
            all_matching_articles AS (
                SELECT * FROM articles_matching_with_title_and_body
                UNION ALL
                SELECT * FROM articles_matching_with_title
                UNION ALL
                SELECT * FROM articles_matching_with_body
            )
            SELECT
                knowledge_article.id,
                knowledge_article.icon,
                knowledge_article.name,
                CASE WHEN to_tsvector('knowledge_config', knowledge_article.body) @@ %(ts_query)s
                     THEN ts_headline('knowledge_config', knowledge_article.body, %(ts_query)s,
                            'StartSel=<strong>, StopSel=</strong>, MaxWords=20, MinWords=10, MaxFragments=3')
                     ELSE NULL END AS "headline",
                COALESCE(CAST(article_favorite.id AS BOOLEAN), FALSE) AS is_user_favorite,
                knowledge_article.root_article_id,
                root_article.id AS root_article_id,
                root_article.icon AS root_article_icon,
                root_article.name AS root_article_name
              FROM all_matching_articles
         LEFT JOIN knowledge_article
                ON knowledge_article.id = all_matching_articles.id
         LEFT JOIN knowledge_article AS root_article
                ON knowledge_article.root_article_id = root_article.id
         LEFT JOIN knowledge_article_favorite article_favorite
                ON knowledge_article.id = article_favorite.article_id
               AND article_favorite.user_id = %(user_id)s
          ORDER BY all_matching_articles.order ASC,
                   all_matching_articles.score DESC,
                   is_user_favorite DESC,
                   knowledge_article.id DESC
             LIMIT %(limit)s
            """,
                sql_where_clause=query.where_clause,
                search_pattern=search_pattern,
                ts_query=ts_query,
                user_id=self.env.user.id,
                cut_off=cut_off,
                limit=limit,
            )
        )

        sorted_articles = self.env.cr.dictfetchall()

        for sorted_article in sorted_articles:
            if sorted_article["icon"] is None:
                sorted_article["icon"] = False
            sorted_article["root_article_id"] = (
                sorted_article["root_article_id"],
                "%s %s"
                % (
                    sorted_article["root_article_icon"]
                    or self._get_no_icon_placeholder(),
                    sorted_article["root_article_name"] or self.env._("Untitled"),
                ),
            )
            del sorted_article["root_article_icon"]
            del sorted_article["root_article_name"]
            if sorted_article["headline"] is None:
                del sorted_article["headline"]
        return sorted_articles

    def get_suggested_templates(self):
        self.check_singleton()
        if not self.origin_template_id:
            return []

        all_articles_created_from_template = self.search(
            [
                ("is_template", "=", False),
                ("parent_id", "child_of", self.id),
                ("origin_template_id", "!=", False),
            ]
        )

        suggested_templates = []
        stack = [self.origin_template_id]

        while stack:
            template = stack.pop()
            if template not in all_articles_created_from_template.origin_template_id:
                suggested_templates.append(
                    {
                        "id": template.id,
                        "icon": template.icon,
                        "template_name": template.template_name,
                        "template_category_id": [
                            template.template_category_id.id,
                            template.template_category_id.display_name,
                        ],
                        "template_category_sequence": template.template_category_sequence,
                        "template_sequence": len(suggested_templates),
                    }
                )
            stack += list(
                template.child_ids.sorted(
                    lambda template: template.template_sequence, reverse=True
                )
            )

        return suggested_templates

    def load_suggested_template(self, template_id):
        self.check_singleton()
        if not template_id or not self.origin_template_id:
            return None
        template = self.search(
            [
                ("id", "=", template_id),
                ("is_template", "=", True),
                ("parent_id", "child_of", self.origin_template_id.id),
            ]
        )
        if not template:
            return None

        parent_article = self
        templates_to_load = []
        template_to_article_pairs = []

        all_articles_created_from_template = self.search(
            [
                ("is_template", "=", False),
                ("parent_id", "child_of", self.root_article_id.id),
                ("origin_template_id", "!=", False),
            ]
        )

        articles_by_origin_template = all_articles_created_from_template.grouped(
            "origin_template_id"
        )
        while template:
            article_created_from_template = articles_by_origin_template.get(template)
            if article_created_from_template:
                parent_article = article_created_from_template[0]
                break
            templates_to_load.append(template)
            template = template.parent_id

        for template in reversed(templates_to_load):
            sibling_articles = self.search(
                [
                    ("is_template", "=", False),
                    ("parent_id", "=", parent_article.id),
                    ("origin_template_id.parent_id", "=", template.parent_id.id),
                ]
            )
            article = self.env["knowledge.article"].create(
                {
                    "parent_id": parent_article.id,
                    "origin_template_id": template.id,
                    "icon": template.icon,
                    "name": template.template_name,
                }
            )
            if sibling_articles:
                articles_with_higher_template_sequence = sorted(
                    [
                        sibling_article
                        for sibling_article in sibling_articles
                        if sibling_article.origin_template_id.template_sequence
                        > template.template_sequence
                    ],
                    key=lambda sibling_article: (
                        sibling_article.origin_template_id.template_sequence
                    ),
                )
                if articles_with_higher_template_sequence:
                    article.move_to(
                        parent_id=parent_article.id,
                        before_article_id=articles_with_higher_template_sequence[0].id,
                    )
            template_to_article_pairs.append((template, article))
            all_articles_created_from_template |= article
            parent_article = article

        template_xml_id_to_article_id_mapping = {}
        all_ir_model_data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("model", "=", "knowledge.article"),
                    (
                        "res_id",
                        "in",
                        all_articles_created_from_template.mapped(
                            "origin_template_id.id"
                        ),
                    ),
                ]
            )
        )

        ir_model_data_by_res_id = all_ir_model_data.grouped("res_id")
        for article in all_articles_created_from_template:
            ir_model_data = ir_model_data_by_res_id.get(
                article.origin_template_id.id, all_ir_model_data.browse()
            )
            if ir_model_data:
                template_xml_id = ir_model_data.complete_name
                template_xml_id_to_article_id_mapping[template_xml_id] = article.id

        def ref(xml_id):
            return (
                template_xml_id_to_article_id_mapping[xml_id]
                if xml_id in template_xml_id_to_article_id_mapping
                else self.env.ref(xml_id).id
            )

        for template, article in template_to_article_pairs:
            article.write(
                {
                    "article_properties": template.article_properties or {},
                    "article_properties_definition": template.article_properties_definition,
                    "body": template.with_context(
                        target_article_id=article.id
                    )._render_template(ref),
                    "cover_image_id": template.cover_image_id.id,
                    "full_width": template.full_width,
                }
            )

        return parent_article

    def get_permission_panel_members(self):
        self.check_singleton()
        if not self.user_has_access:
            return []
        res_partner_fields_list = [
            ("name", "name"),
            ("partner_share", "partner_share"),
            ("id", "partner_id"),
        ]
        if self.env.user._is_internal():
            res_partner_fields_list.append(("email", "email"))
        return list(
            self._get_article_member_permissions(
                additional_fields={
                    "res.partner": res_partner_fields_list,
                    "knowledge.article": [
                        ("icon", "based_on_icon"),
                        ("name", "based_on_name"),
                    ],
                }
            )[self.id].values()
        )

    def restore_article_access(self):
        self.check_singleton()
        if not self.parent_id:
            return False
        if not self.env.su and not self.user_can_write:
            raise AccessError(
                self.env._(
                    "You have to be editor on %(article_name)s to restore it.",
                    article_name=self.display_name,
                )
            )
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(
                self.env._(
                    "Only internal users are allowed to restore the original article access information."
                )
            )

        member_permission = (self | self.parent_id)._get_article_member_permissions()
        article_members_permission = member_permission[self.id]
        parents_members_permission = member_permission[self.parent_id.id]

        members_values = []
        for partner, values in article_members_permission.items():
            permission = values["permission"]
            if (
                values["based_on"]
                or partner not in parents_members_permission
                or ARTICLE_PERMISSION_LEVEL[permission]
                > ARTICLE_PERMISSION_LEVEL[
                    parents_members_permission[partner]["permission"]
                ]
            ):
                continue
            members_values.append((3, values["member_id"]))

        return self.sudo().write(
            {
                "internal_permission": False,
                "article_member_ids": members_values,
                "is_desynchronized": False,
            }
        )

    def invite_members(self, partners, permission, message=None) -> bool:
        self.check_singleton()
        if permission == "none":
            self._exclude_partners(partners)
        else:
            unreachable_children = self.sudo().child_ids.filtered(
                lambda c: not c.user_has_write_access and not c.is_desynchronized
            )
            for child in unreachable_children:
                child.write(child._desync_access_from_parents_values())

            self._lower_inherited_members(partners, permission)
            members_command = self._add_members_command(partners, permission)
            self.sudo().write({"article_member_ids": members_command})
            self._send_invite_mail(partners, permission, message)

        return True

    def _members_reaching_from_above(self):
        if not self.parent_id or self.is_desynchronized:
            return {}
        return self.parent_id._get_article_member_permissions()[self.parent_id.id]

    def _lower_inherited_members(self, partners, permission) -> None:
        above = self._members_reaching_from_above()
        lowered = partners.filtered(
            lambda partner: (
                partner.id in above
                and ARTICLE_PERMISSION_LEVEL[above[partner.id]["permission"]]
                > ARTICLE_PERMISSION_LEVEL[permission]
            )
        )
        if lowered:
            self.with_privilege("knowledge.privilege_share_articles").write(
                self._desync_access_from_parents_values(
                    force_partners=lowered, force_member_permission=permission
                )
            )

    def _exclude_partners(self, partners) -> None:
        self.check_singleton()
        if not self.env.su and not self.user_can_write:
            raise AccessError(
                self.env._(
                    "You have to be editor on %(article_name)s to add members.",
                    article_name=self.display_name,
                )
            )
        sharing = self.with_privilege("knowledge.privilege_share_articles")
        if set(partners.ids) & self._members_reaching_from_above().keys():
            sharing.write(
                self._desync_access_from_parents_values(
                    force_partners=partners, force_member_permission="none"
                )
            )
        own = self.article_member_ids.filtered(lambda m: m.partner_id in partners)
        if own:
            sharing.write(
                {"article_member_ids": [Command.delete(member.id) for member in own]}
            )

    def set_internal_permission(self, permission):
        if not self.env.user._is_internal():
            raise AccessError(
                self.env._(
                    "Only internal users are allowed to alter internal permission."
                )
            )
        self.check_singleton()
        if self.user_has_write_access and permission != "write":
            self._add_members(self.env.user.partner_id, "write")

        downgrade = (
            not self.is_desynchronized
            and self.parent_id
            and ARTICLE_PERMISSION_LEVEL[self.parent_id.inherited_permission]
            > ARTICLE_PERMISSION_LEVEL[permission]
        )
        if downgrade:
            if not self.env.su and not self.user_can_write:
                raise AccessError(
                    self.env._(
                        "You have to be editor on %(article_name)s to change its internal permission.",
                        article_name=self.display_name,
                    )
                )
            return self.sudo().write(
                self._desync_access_from_parents_values(
                    force_internal_permission=permission
                )
            )

        values = {"internal_permission": permission}
        if (
            permission == self.parent_id.inherited_permission
            and not self.article_member_ids
        ):
            values.update({"internal_permission": False, "is_desynchronized": False})
        return self.write(values)

    def set_member_permission(self, member_id, permission) -> None:
        member = self.env["knowledge.article.member"].browse(member_id)
        if not member.exists():
            raise UserError(
                self.env._("The membership you are trying to edit has been deleted")
            )
        self.check_singleton()
        if not self.env.su and not self.user_can_write:
            raise AccessError(
                self.env._(
                    "You have to be editor on %(article_name)s to modify members permissions.",
                    article_name=self.display_name,
                )
            )
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(
                self.env._("Only internal users are allowed to alter memberships.")
            )

        if permission == "none":
            self._exclude_partners(member.partner_id)
            return
        if member.article_id != self:
            downgrade = (
                ARTICLE_PERMISSION_LEVEL[member.permission]
                > ARTICLE_PERMISSION_LEVEL[permission]
            )
            if downgrade:
                self.sudo().write(
                    self._desync_access_from_parents_values(
                        force_partners=member.partner_id,
                        force_member_permission=permission,
                    )
                )
            else:
                self._add_members(member.partner_id, permission)
        else:
            member.article_id.sudo().with_context(
                knowledge_member_skip_writable_check=True
            ).write(
                {
                    "article_member_ids": [
                        Command.update(member.id, {"permission": permission})
                    ]
                }
            )

    def set_is_article_visible_by_everyone(
        self, is_article_visible_by_everyone
    ) -> None:
        self.check_singleton()
        self.write({"is_article_visible_by_everyone": is_article_visible_by_everyone})

        if (
            not is_article_visible_by_everyone
            and self.env.user.partner_id not in self.article_member_ids.partner_id
            and self.user_permission in ("read", "write")
        ):
            self._add_members(self.env.user.partner_id, self.user_permission)

    def remove_member(self, member_id) -> None:
        self.check_singleton()
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(
                self.env._("Only internal users are allowed to remove memberships.")
            )

        member = self.env["knowledge.article.member"].browse(member_id)
        if not member.exists():
            raise UserError(
                self.env._(
                    "The selected member does not exist or has already been deleted."
                )
            )

        current_membership = self.article_member_ids.filtered(lambda m: m == member)

        remove_self = member.partner_id == self.env.user.partner_id
        if (
            remove_self
            and self.category == "private"
            and current_membership
            and len(self.article_member_ids) == 1
        ):
            self.action_send_to_trash()
            return

        self_escalation = not (
            remove_self
            and ARTICLE_PERMISSION_LEVEL[member.permission]
            >= ARTICLE_PERMISSION_LEVEL[self.inherited_permission]
        )
        if not self.env.su and self_escalation and not self.user_can_write:
            raise AccessError(
                self.env._(
                    "You have to be editor on %(article_name)s to remove or exclude member %(member_name)s.",
                    article_name=self.display_name,
                    member_name=member.display_name,
                )
            )
        if current_membership:
            self.sudo().write(
                {"article_member_ids": [Command.delete(current_membership.id)]}
            )
        else:
            self.sudo().write(
                self._desync_access_from_parents_values(
                    force_partners=self.article_member_ids.partner_id
                )
            )
            current_membership = self.article_member_ids.filtered(
                lambda m: m.partner_id == member.partner_id
            )
            if current_membership:
                self.sudo().write(
                    {"article_member_ids": [Command.delete(current_membership.id)]}
                )

    def _add_members(self, partners, permission, force_update=True):
        self.check_singleton()
        members_command = self._add_members_command(
            partners, permission, force_update=force_update
        )
        return self.sudo().write({"article_member_ids": members_command})

    def _add_members_command(self, partners, permission, force_update=True):
        self.check_singleton()
        if not self.env.su and not self.user_can_write:
            raise AccessError(
                self.env._(
                    "You have to be editor on %(article_name)s to add members.",
                    article_name=self.display_name,
                )
            )
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(
                self.env._("Only internal users are allowed to alter memberships.")
            )

        members_to_update = self.article_member_ids.filtered_domain(
            [("partner_id", "in", partners.ids)]
        )
        if permission == "none":
            return [Command.delete(member.id) for member in members_to_update]
        partners_to_create = partners - members_to_update.mapped("partner_id")

        members_command = [
            Command.create({"partner_id": partner.id, "permission": permission})
            for partner in partners_to_create
        ]
        if force_update:
            members_command += [
                (1, member.id, {"permission": permission})
                for member in members_to_update
            ]
        return members_command

    def _desync_access_from_parents_values(
        self,
        force_internal_permission=False,
        force_partners=False,
        force_member_permission=False,
    ) -> dict:
        self.check_singleton()
        level = force_internal_permission or self.inherited_permission
        members_commands = self._copy_access_from_parents_commands(
            force_partners=force_partners,
            force_member_permission=force_member_permission,
        )
        grant = self._own_audience_grant()
        if level in ("read", "write"):
            audience_commands = [
                Command.update(grant.id, {"permission": level})
                if grant
                else Command.create(
                    {
                        "group_id": self._internal_audience_group(),
                        "permission": level,
                        "cause": "manual",
                    }
                )
            ]
        else:
            audience_commands = [Command.delete(grant.id)] if grant else []

        return {
            "access_grant_ids": members_commands + audience_commands,
            "is_desynchronized": True,
        }

    def _copy_access_from_parents_commands(
        self, force_partners=False, force_member_permission=False
    ):
        self.check_singleton()
        members_permission = self._get_article_member_permissions()[self.id]

        members_commands = []
        for partner_id, values in members_permission.items():
            if not values["based_on"] or values["based_on"] == self.id:
                continue
            if (
                force_partners
                and force_member_permission
                and partner_id in force_partners.ids
            ):
                new_member_permission = force_member_permission
            else:
                new_member_permission = values["permission"]
            if new_member_permission == "none":
                continue

            members_commands.append(
                (
                    0,
                    0,
                    {
                        "partner_id": partner_id,
                        "permission": new_member_permission,
                    },
                )
            )
        return members_commands

    def _detach_unwritable_descendants(self):
        all_descendants_sudo = self.sudo()._get_descendants()
        writable_descendants_sudo = (
            all_descendants_sudo.with_env(self.env)._filtered_access("write").sudo()
        )
        other_descendants_sudo = all_descendants_sudo - writable_descendants_sudo

        for article_sudo in other_descendants_sudo.filtered(
            lambda article: not article.is_desynchronized
        ):
            article_sudo.write(
                {
                    "article_member_ids": article_sudo._copy_access_from_parents_commands()
                }
            )

        new_roots_woperm_sudo = other_descendants_sudo.filtered(
            lambda article: (
                article.parent_id in (self + writable_descendants_sudo)
                and not article.internal_permission
            )
        )
        new_roots_wperm_sudo = other_descendants_sudo.filtered(
            lambda article: (
                article.parent_id in (self + writable_descendants_sudo)
                and article.internal_permission
            )
        )
        if new_roots_wperm_sudo:
            new_roots_wperm_sudo.write({"is_desynchronized": False, "parent_id": False})
        for new_root_sudo in new_roots_woperm_sudo:
            new_root_sudo.write(
                {
                    "is_desynchronized": False,
                    "internal_permission": new_root_sudo.inherited_permission,
                    "parent_id": False,
                }
            )

        return writable_descendants_sudo

    def _move_and_make_private(self, parent=False, before_article=False):
        self.check_singleton()
        parent = parent if parent is not False else self.env["knowledge.article"]
        before_article = (
            before_article
            if before_article is not False
            else self.env["knowledge.article"]
        )

        try:
            (self + parent).check_access("write")
        except AccessError, UserError:
            if parent:
                raise AccessError(
                    self.env._(
                        "You are not allowed to move '%(article_name)s' under '%(parent_name)s'.",
                        article_name=self.display_name,
                        parent_name=parent.display_name,
                    )
                ) from None
            raise AccessError(
                self.env._(
                    "You are not allowed to make '%(article_name)s' private.",
                    article_name=self.display_name,
                )
            ) from None

        writable_descendants_sudo = self._detach_unwritable_descendants()

        article_values = {
            "internal_permission": False if parent else "none",
            "is_desynchronized": False,
            "parent_id": parent.id if parent else False,
        }
        if before_article:
            article_values["sequence"] = before_article.sequence

        self_sudo = self.sudo()
        members_to_remove = self_sudo.article_member_ids
        self_member_command = []
        if not parent:
            self_member = self_sudo.article_member_ids.filtered(
                lambda m: m.partner_id == self.env.user.partner_id
            )
            if self_member:
                self_member_command = [(1, self_member.id, {"permission": "write"})]
                members_to_remove = members_to_remove.filtered(
                    lambda member: member.partner_id != self.env.user.partner_id
                )
            else:
                self_member_command = [
                    Command.create(
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        }
                    )
                ]

        article_values["article_member_ids"] = [
            (2, member.id) for member in members_to_remove
        ] + self_member_command

        res = self_sudo.with_context(knowledge_member_skip_writable_check=True).write(
            article_values
        )

        writable_descendants_sudo.with_context(
            knowledge_member_skip_writable_check=True
        ).write(
            {
                "internal_permission": False,
                "article_member_ids": [(5, 0)],
            }
        )

        return res

    def _move_and_make_shared_root(self, before_article):
        self.check_singleton()
        if not self.has_access("write"):
            raise AccessError(
                self.env._(
                    "You are not allowed to move '%(article_name)s'.",
                    article_name=self.display_name,
                )
            )

        article_members = self._get_article_member_permissions()[self.id]
        members_commands = []
        nb_members = 0
        user_is_member = False
        for partner_id, values in article_members.items():
            if not partner_id or values["permission"] == "none":
                continue
            nb_members += 1
            if partner_id == self.env.user.partner_id.id:
                user_is_member = True
            if values["based_on"] and values["based_on"] != self.id:
                members_commands.append(
                    (
                        0,
                        0,
                        {"partner_id": partner_id, "permission": values["permission"]},
                    )
                )

        if not user_is_member:
            members_commands.append(
                (
                    0,
                    0,
                    {"partner_id": self.env.user.partner_id.id, "permission": "write"},
                )
            )
            nb_members += 1
        if nb_members < 2:
            raise ValidationError(
                self.env._("You need at least 2 members for the Article to be shared.")
            )

        self._detach_unwritable_descendants()

        values = {
            "article_member_ids": members_commands,
            "internal_permission": "none",
            "is_desynchronized": False,
            "parent_id": False,
        }
        if before_article:
            values["sequence"] = before_article.sequence

        return self.sudo().write(values)

    def _has_write_member(
        self, partners_to_exclude=False, members_to_exclude=False
    ) -> bool:
        self.check_singleton()
        partners_to_exclude = partners_to_exclude or self.env["res.partner"]
        members_to_exclude = members_to_exclude or self.env["knowledge.article.member"]
        node = self
        while node:
            if any(
                member.permission == "write"
                and member not in members_to_exclude
                and member.partner_id not in partners_to_exclude
                for member in node.article_member_ids
            ):
                return True
            if node.is_desynchronized:
                break
            node = node.parent_id
        return False

    def _get_article_member_permissions(self, additional_fields=False):
        self.env["res.partner"].flush_model()
        self.env["knowledge.article"].flush_model()
        self.env["knowledge.article.member"].flush_model()

        if not additional_fields:
            additional_fields = {}

        article_ids_clause = SQL()
        if self.ids:
            article_ids_clause = SQL("WHERE article.id = ANY(%s)", list(self.ids))

        alias = "ef"
        select_fields_clause = SQL()
        join_clauses = SQL()
        if additional_fields:
            supported_models = {
                "res.partner": "partner_id",
                "knowledge.article": "source_article_id",
                "knowledge.article.member": "member_id",
            }
            select_fields = []
            joins = {}
            for model_name, fields_list in additional_fields.items():
                if model_name not in supported_models:
                    continue

                model = self.env[model_name]
                table_name = self.env[model_name]._table

                if model_name not in joins:
                    joins[model_name] = SQL(
                        "JOIN %(table_name)s ON %(table_pkey)s = %(effective_membership_fkey)s",
                        table_name=SQL.identifier(table_name),
                        table_pkey=SQL.identifier(table_name, "id"),
                        effective_membership_fkey=SQL.identifier(
                            alias, supported_models[model_name]
                        ),
                    )

                for field_name, field_alias in fields_list:
                    field = model._fields.get(field_name)
                    has_column = bool(field and field.store and field.column_type)
                    select_key = SQL(
                        "%(table_column)s AS %(field_alias)s",
                        table_column=SQL.identifier(table_name, field_name),
                        field_alias=SQL.identifier(field_alias),
                    )
                    if has_column and select_key not in select_fields:
                        select_fields.append(select_key)

            if select_fields:
                select_fields_clause = SQL(
                    ", %s", SQL(", ").join(field for field in select_fields)
                )
            if joins:
                join_clauses = SQL("\n").join(joins.values())

        query = SQL(
            """
            WITH
                article_hierarchy     AS (
                    SELECT article.id,
                           chain.ancestor_id,
                           chain.depth
                      FROM knowledge_article AS article
                      CROSS JOIN LATERAL unnest(
                          string_to_array(rtrim(article.access_scope_path, '/'), '/')::int4[]
                      ) WITH ORDINALITY AS chain(ancestor_id, depth)
                      %(article_ids_clause)s
                ),
                article_memberships   AS (
                    SELECT h.id          AS target_article_id,
                           h.ancestor_id AS source_article_id,
                           m.id          AS member_id,
                           m.permission,
                           m.partner_id,
                           h.depth
                      FROM article_hierarchy h
                      JOIN knowledge_article_member m ON m.article_id = h.ancestor_id
                     WHERE m.partner_id IS NOT NULL
                       AND (m.date_to IS NULL OR m.date_to > now() AT TIME ZONE 'UTC')
                ),
                effective_memberships AS (
                    SELECT target_article_id,
                           source_article_id,
                           member_id,
                           permission,
                           partner_id
                      FROM (
                          SELECT *,
                                 RANK() OVER (
                                     PARTITION BY target_article_id, partner_id
                                     ORDER BY (permission = 'write') DESC, depth DESC
                                     ) AS priority_rank
                            FROM article_memberships
                      ) ranked_memberships
                     WHERE priority_rank = 1
                )
            SELECT %(alias)s.*
                   %(select_fields_clause)s
              FROM effective_memberships AS %(alias)s
                   %(join_clauses)s
            """,
            alias=SQL(alias),
            article_ids_clause=article_ids_clause,
            select_fields_clause=select_fields_clause,
            join_clauses=join_clauses,
        )
        results = self.env.execute_query_dict(query)

        article_members = defaultdict(dict)
        for result in results:
            article_id = result["target_article_id"]
            origin_id = result["source_article_id"]
            partner_id = result["partner_id"]
            article_members[article_id][partner_id] = {
                "member_id": result["member_id"],
                "based_on": origin_id if origin_id != article_id else False,
                "permission": result["permission"],
                **{
                    field_alias: result[field_alias]
                    if model != "knowledge.article" or origin_id != article_id
                    else False
                    for model, fields_list in additional_fields.items()
                    for field, field_alias in fields_list
                },
            }

        return article_members

    def _mail_track(self, tracked_fields, initial_values):
        changes, tracking_value_ids = super()._mail_track(
            tracked_fields, initial_values
        )
        if {
            "parent_id",
            "root_article_id",
        } & changes and not self.user_has_write_access:
            partner_name = self.env.user.partner_id.display_name
            message_body = self.env._(
                "Logging changes from %(partner_name)s without write access on article %(article_name)s due to hierarchy tree update",
                partner_name=partner_name,
                article_name=self.display_name,
            )
            self._track_set_log_message(Markup("<p>%s</p>") % message_body)
        return changes, tracking_value_ids

    def _send_invite_mail(self, partners, permission, message=None) -> None:
        self.check_singleton()

        partner_to_bodies = {}
        for partner in partners:
            partner_to_bodies[partner] = (
                self.env["ir.qweb"]
                .with_context(lang=partner.lang)
                ._render(
                    "knowledge.knowledge_article_mail_invite",
                    {
                        "record": self,
                        "user": self.env.user,
                        "permission": permission,
                        "message": message,
                    },
                )
            )

        if self.display_name:
            subject = self.env._("Article shared with you: %s", self.display_name)
        else:
            subject = self.env._("Invitation to access an article")

        if permission == "read":
            permission_label = self.env._("Read")
        else:
            permission_label = self.env._("Write")

        for partner, body in partner_to_bodies.items():
            self.with_context(lang=partner.lang).message_notify(
                body=body,
                email_layout_xmlid="mail.mail_notification_layout",
                partner_ids=partner.ids,
                subject=subject,
                subtitles=[
                    self.display_name,
                    self.env._("Your Access: %s", permission_label),
                ],
            )

    def _notify_get_recipients_groups(self, message, model_description, msg_vals=False):
        groups = super()._notify_get_recipients_groups(
            message, model_description, msg_vals=msg_vals
        )
        msg_vals = msg_vals or {}
        partner_ids = msg_vals.get("partner_ids", message.partner_ids.ids)
        if not self or not partner_ids:
            return groups
        new_group = [
            self._get_member_invitation_group(member)
            for member in self.article_member_ids.filtered(
                lambda member: (
                    member.partner_id.id in partner_ids
                    and member.partner_id.partner_share
                )
            )
        ]
        return new_group + groups

    def _get_member_invitation_group(self, member) -> tuple:
        url = url_join(
            self.get_base_url(),
            f"/knowledge/article/invite/{member.id}/{member._get_invitation_token()}",
        )
        partner_id = member.partner_id.id
        return (
            f"group_knowledge_member_{member.id}",
            lambda pdata: pdata["id"] == partner_id,
            {
                "has_button_access": True,
                "button_access": {
                    "url": url,
                },
            },
        )

    def _send_trash_notifications(self):
        partners_to_notify = self.article_member_ids.filtered(
            lambda member: member.permission in ["read", "write"]
        ).partner_id

        KnowledgeArticle = self.env["knowledge.article"].with_context(
            active_test=False, allowed_company_ids=[]
        )
        sent_messages = self.env["mail.message"]
        for partner in partners_to_notify.filtered(lambda p: not p.partner_share):
            if len(self) == 1:
                main_articles, children = self, KnowledgeArticle
            else:
                partner_user = partner.user_ids.filtered(lambda u: not u.share)[0]
                accessible_articles = KnowledgeArticle.with_user(partner_user).search(
                    [("id", "in", self.ids)]
                )

                main_articles = accessible_articles.sudo().filtered_domain(
                    [("parent_id", "not in", accessible_articles.ids)]
                )
                children = accessible_articles - main_articles

            partner_lang = get_lang(self.env, lang_code=partner.lang).code
            self = self.with_context(lang=partner_lang)

            if len(main_articles) == 1:
                subject = self.env._(
                    "%s has been sent to Trash",
                    main_articles.name or self.env._("Untitled"),
                )
            else:
                subject = self.env._("Some articles have been sent to Trash")

            body = (
                self.env["ir.qweb"]
                .with_context(lang=partner_lang)
                ._render(
                    "knowledge.knowledge_article_trash_notification",
                    {
                        "articles": main_articles,
                        "recipient": partner,
                        "child_articles": children,
                    },
                )
            )

            document_to_notify = (
                main_articles
                if len(main_articles) == 1
                else self.env["mixin.mail.thread"]
            )
            sent_messages += document_to_notify.with_context(
                lang=partner_lang
            ).message_notify(
                body=body,
                email_layout_xmlid="mail.mail_notification_light",
                partner_ids=partner.ids,
                subject=subject,
            )

        return sent_messages

    def create_article_from_template(self, parent_id=False):
        self.check_singleton()
        values = {"parent_id": parent_id}
        if not parent_id:
            values.update(
                {
                    "internal_permission": "none",
                    "article_member_ids": [
                        Command.create(
                            {
                                "partner_id": self.env.user.partner_id.id,
                                "permission": "write",
                            }
                        )
                    ],
                }
            )
        article = self.env["knowledge.article"].create(values)
        article.apply_template(self.id, skip_body_update=False)
        return article

    def apply_template(self, template_id, skip_body_update=False):
        self.check_singleton()
        template = self.env["knowledge.article"].browse(template_id)
        template.check_singleton()

        template_to_article_pairs = []
        stack = [(template, self)]

        while stack:
            (parent_template, parent_article) = stack.pop()
            template_to_article_pairs.append((parent_template, parent_article))

            parent_template_stages = self.env["knowledge.article.stage"].search(
                [("parent_id", "=", parent_template.id)]
            )
            parent_article_stages = self.env["knowledge.article.stage"].create(
                [
                    {
                        "name": stage.name,
                        "sequence": stage.sequence,
                        "fold": stage.fold,
                        "parent_id": parent_article.id,
                    }
                    for stage in parent_template_stages
                ]
            )

            child_templates = parent_template.child_ids
            if parent_article._is_load_all_annexes_required():
                child_templates = child_templates.filtered(
                    lambda template: template.template_child_default_create
                )
            child_templates = child_templates.sorted(
                lambda template: (template.write_date, template.id)
            )

            if not child_templates:
                continue

            child_articles_values = []
            for template in child_templates:
                article_values = {
                    "is_article_item": template.is_article_item,
                    "parent_id": parent_article.id,
                    "icon": template.icon,
                    "name": template.template_name,
                }
                article_stage = next(
                    (
                        article_stage
                        for (article_stage, template_stage) in zip(
                            parent_article_stages, parent_template_stages, strict=False
                        )
                        if template_stage == template.stage_id
                    ),
                    False,
                )
                if article_stage:
                    article_values["stage_id"] = article_stage.id
                child_articles_values.append(article_values)

            child_articles = self.env["knowledge.article"].create(child_articles_values)
            stack.extend(zip(child_templates, child_articles, strict=False))

        template_xml_id_to_article_id_mapping = {}
        all_ir_model_data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("model", "=", "knowledge.article"),
                    (
                        "res_id",
                        "in",
                        [template.id for (template, _) in template_to_article_pairs],
                    ),
                ]
            )
        )

        ir_model_data_by_res_id = all_ir_model_data.grouped("res_id")
        for template, article in template_to_article_pairs:
            ir_model_data = ir_model_data_by_res_id.get(
                template.id, all_ir_model_data.browse()
            )

            if ir_model_data:
                template_xml_id = ir_model_data.complete_name
                template_xml_id_to_article_id_mapping[template_xml_id] = article.id

        def ref(xml_id):
            return (
                template_xml_id_to_article_id_mapping[xml_id]
                if xml_id in template_xml_id_to_article_id_mapping
                else self.env.ref(xml_id).id
            )

        (root_template, root_article) = template_to_article_pairs.pop(0)
        for template, article in reversed(template_to_article_pairs):
            article.write(
                {
                    "article_properties": template.article_properties or {},
                    "article_properties_definition": template.article_properties_definition,
                    "body": template.with_context(
                        target_article_id=article.id
                    )._render_template(ref),
                    "cover_image_id": template.cover_image_id.id,
                    "full_width": template.full_width,
                    "origin_template_id": template.id,
                }
            )

        values = {
            "article_properties": root_template.article_properties or {},
            "article_properties_definition": root_template.article_properties_definition,
            "cover_image_id": root_template.cover_image_id.id,
            "full_width": root_template.full_width,
            "icon": root_template.icon,
            "name": root_article.name or root_template.template_name,
            "origin_template_id": root_template.id,
        }
        body = root_template.with_context(
            target_article_id=root_article.id
        )._render_template(ref)
        if not skip_body_update:
            values["body"] = body
        root_article.write(values)

        return body

    def _render_template(self, ref=False):
        self.check_singleton()
        if not self.is_template or not self.template_body:
            return False

        if not ref:

            def ref(xml_id):
                return self.env.ref(xml_id).id

        fragment = self._prepare_template(ref)
        elements = [
            html.tostring(child, encoding="unicode", method="html")
            for child in fragment.getchildren()
        ]
        return "".join(elements)

    def _prepare_template(self, ref):
        def transform_xmlid_to_res_id(match):
            return str(ref(match.group("xml_id")))

        fragment = html.fragment_fromstring(self.template_body, create_parent="div")

        for element in fragment.xpath('//*[@data-embedded="view"]'):
            embedded_props = ast.literal_eval(
                re.sub(
                    r"(?<![\w])ref\(\'(?P<xml_id>\w+\.\w+)\'\)",
                    transform_xmlid_to_res_id,
                    element.get("data-embedded-props"),
                )
            )
            element.set("data-embedded-props", json_dumps(embedded_props))

        for element in fragment.xpath(
            '//*[contains(@class, "o_knowledge_article_link")]'
        ):
            article_id = ast.literal_eval(
                re.sub(
                    r"(?<![\w])ref\(\'(?P<xml_id>\w+\.\w+)\'\)",
                    transform_xmlid_to_res_id,
                    element.get("data-res_id"),
                )
            )
            element.set("href", "/knowledge/article/%s" % (article_id))
            element.set("data-res_id", "%s" % (article_id))

        target_article = (
            self.env["knowledge.article"].browse(
                self.env.context.get("target_article_id", False)
            )
            or self
        )

        for element in fragment.xpath('//*[@data-embedded="articleIndex"]'):
            embedded_props = json_loads(element.get("data-embedded-props", "{}"))
            if embedded_props.get("showAllChildren"):

                def get_article_index(parent_article):
                    return [
                        {
                            "id": child_article.id,
                            "name": child_article.display_name,
                            "childIds": get_article_index(child_article),
                        }
                        for child_article in parent_article.child_ids
                        if not child_article.is_article_item
                    ]

                articles = get_article_index(target_article)
            else:
                articles = [
                    {
                        "id": child_article.id,
                        "name": child_article.display_name,
                        "childIds": [],
                    }
                    for child_article in target_article.child_ids
                    if not child_article.is_article_item
                ]
            element.set(
                "data-embedded-props",
                json_dumps(
                    {
                        "articles": articles,
                        "showAllChildren": embedded_props.get("showAllChildren", False),
                    }
                ),
            )
        return fragment

    def apply_article_as_template(self, article_id):
        self.check_singleton()
        article = self.env["knowledge.article"].browse(article_id)
        article.check_singleton()

        self.write(
            {
                "article_properties_definition": article.article_properties_definition,
                "cover_image_id": article.cover_image_id.id,
                "cover_image_position": article.cover_image_position,
                "full_width": article.full_width,
                "icon": article.icon,
                "name": article.name,
            }
        )

        body = self._get_transformed_body_from(article)

        stages_mapping = {}
        for stage in self.env["knowledge.article.stage"].search(
            [("parent_id", "=", article.id)]
        ):
            new_stage = stage.copy({"parent_id": self.id})
            stages_mapping[stage.id] = new_stage.id

        article_items = article.child_ids.filtered(
            lambda article: article.is_article_item
        ).sorted(lambda child: child.sequence)
        new_article_items = self.create(
            [
                {
                    "article_properties": article_item.article_properties,
                    "cover_image_id": article_item.cover_image_id.id,
                    "cover_image_position": article_item.cover_image_position,
                    "full_width": article_item.full_width,
                    "icon": article_item.icon,
                    "is_article_item": True,
                    "name": article_item.name,
                    "parent_id": self.id,
                    "stage_id": stages_mapping.get(article_item.stage_id.id, False),
                }
                for article_item in article_items
            ]
        )

        stages_by_parent_id = (
            self.env["knowledge.article.stage"]
            .search([("parent_id", "in", article_items.ids)])
            .grouped("parent_id")
        )

        for article_item, new_article_item in zip(
            article_items, new_article_items, strict=False
        ):
            stages = stages_by_parent_id.get(article_item)
            if stages:
                stages.copy({"parent_id": new_article_item.id})
            new_article_item.write(
                {
                    "body": new_article_item._get_transformed_body_from(article_item),
                }
            )

        return body

    @api.model
    def get_available_templates(self) -> dict:
        articles = self.env["knowledge.article"].search_read(
            [("is_listed_in_templates_gallery", "=", True)],
            ["id", "icon", "name", "user_can_write"],
        )

        templates = self.env["knowledge.article"].search_read(
            self._get_domain_available_template(),
            [
                "id",
                "icon",
                "template_name",
                "template_category_id",
                "template_category_sequence",
                "template_sequence",
            ],
        )

        return {"articles": articles, "templates": templates}

    @api.model
    def _get_domain_available_template(self):
        return [("is_template", "=", True), ("parent_id", "=", False)]

    def create_default_item_stages(self) -> None:
        stage_count = self.env["knowledge.article.stage"].search_count(
            [("parent_id", "=", self.id)]
        )
        if not stage_count:
            self.env["knowledge.article.stage"].create(
                [
                    {
                        "name": stage_name,
                        "sequence": sequence,
                        "parent_id": self.id,
                        "fold": fold,
                    }
                    for stage_name, sequence, fold in [
                        (self.env._("New"), 0, False),
                        (self.env._("Ongoing"), 1, False),
                        (self.env._("Done"), 2, True),
                    ]
                ]
            )

    def _is_load_all_annexes_required(self) -> bool:
        self.check_singleton()
        return True

    @api.model
    def _extract_icon_from_name(self, name) -> tuple:
        if not isinstance(name, str) or len(name) < 3:
            return name, None

        emoji_match = re.match(r"([^\w.,;:_%+!\\/@$€#&()*=~-]) (.*)", name)
        if not emoji_match or len(emoji_match.groups()) != 2:
            return name, None

        emoji = emoji_match.groups(1)[0]
        article_name = emoji_match.groups(1)[1]
        return article_name, emoji

    def _get_ancestor_ids_nearest_first(self):
        ancestor_ids = OrderedSet()
        for article in self:
            if article.id in ancestor_ids:
                continue
            for ancestor_id in reversed(list(article._get_ancestor_ids())):
                if ancestor_id in ancestor_ids:
                    break
                ancestor_ids.add(ancestor_id)
        return ancestor_ids

    def _get_invite_url(self, partner):
        self.check_singleton()
        member = self.env["knowledge.article.member"].search(
            [("article_id", "=", self.id), ("partner_id", "=", partner.id)]
        )
        return url_join(
            self.get_base_url(),
            "/knowledge/article/invite/%s/%s"
            % (member.id, member._get_invitation_token()),
        )

    def _get_first_accessible_article(self):
        article = self.env["knowledge.article"]
        if not self.env.user._is_public():
            article = (
                self.env["knowledge.article.favorite"]
                .search(
                    [("user_id", "=", self.env.uid), ("is_article_active", "=", True)],
                    limit=1,
                )
                .article_id
            )
        if not article:
            article = self.search(
                Domain.AND(
                    [
                        [("parent_id", "=", False), ("is_template", "=", False)],
                        self._get_domain_read(),
                        [("is_article_visible", "=", True)],
                    ]
                ),
                limit=1,
                order="sequence, category desc",
            )
        return article

    def get_valid_parent_options(self, search_term=""):
        return self.search_read(
            domain=[
                "&",
                "&",
                "&",
                "&",
                "&",
                ("is_template", "=", False),
                ("name", "ilike", search_term),
                ("id", "not in", self.ids),
                "!",
                ("parent_id", "child_of", self.ids),
                ("user_has_access", "=", True),
                ("is_article_item", "=", False),
            ],
            fields=["id", "display_name", "root_article_id"],
            limit=15,
        )

    def _get_descendants(self):
        return self.env["knowledge.article"].search(
            [("id", "not in", self.ids), ("parent_id", "child_of", self.ids)]
        )

    @api.model
    def get_empty_list_help(self, help_message):
        if "search_default_filter_trashed" not in self.env.context:
            return super().get_empty_list_help(help_message)
        get_param = self.env["ir.config_parameter"].sudo().get_param
        limit_days = get_param("knowledge.knowledge_article_trash_limit_days")
        try:
            limit_days = int(limit_days)
        except ValueError:
            limit_days = self.DEFAULT_ARTICLE_TRASH_LIMIT_DAYS
        title = self.env._("No Article in Trash")
        description = Markup(
            self.env._("""Deleted articles are stored in Trash an extra <b>%(threshold)s</b> days
                 before being permanently removed for your database""")
        ) % {"threshold": limit_days}

        return super().get_empty_list_help(
            f'<p class="o_view_nocontent_smiling_face">{title}</p><p>{description}</p>'
        )

    def get_visible_articles(self, root_articles_ids, unfolded_ids):
        if root_articles_ids:
            visible_articles_domain = [
                "|",
                ("id", "in", root_articles_ids),
                "&",
                "&",
                ("parent_id", "in", unfolded_ids),
                ("id", "child_of", root_articles_ids),
                ("is_article_item", "=", False),
            ]

            return self.env["knowledge.article"].search(
                visible_articles_domain,
                order="sequence, id",
            )
        return self.env["knowledge.article"]

    def _get_accessible_root_ancestors(self):
        accessible_root_ancestor = self

        def update_has_access(parent):
            return parent.has_access("read")

        accessible_root_ancestors = (
            accessible_root_ancestor
            if update_has_access(accessible_root_ancestor)
            else self.env["knowledge.article"]
        )
        while (
            update_has_access(accessible_root_ancestor)
            and update_has_access(accessible_root_ancestor.parent_id)
            and accessible_root_ancestor.parent_id.id
        ):
            accessible_root_ancestor = accessible_root_ancestor.parent_id
            accessible_root_ancestors |= accessible_root_ancestor
        return accessible_root_ancestors

    def get_sidebar_articles(self, unfolded_ids=False) -> dict:

        root_articles_domain = [
            ("parent_id", "=", False),
            ("is_template", "=", False),
            ("is_article_visible", "=", True),
        ]
        has_root_access = self.root_article_id.has_access("read")

        root_articles_ids = (
            self.env["knowledge.article"].sudo().search(root_articles_domain).ids
        )

        active_article_accessible_ancestors = False
        if self and not has_root_access and self.id not in root_articles_ids:
            active_article_accessible_ancestors = self._get_accessible_root_ancestors()
            root_articles_ids += [active_article_accessible_ancestors[-1].id]
            unfolded_ids += active_article_accessible_ancestors.ids

        favorite_articles_ids = (
            self.env["knowledge.article.favorite"]
            .sudo()
            .search(
                [("user_id", "=", self.env.user.id), ("is_article_active", "=", True)]
            )
            .article_id.filtered(lambda article: article.user_has_access)
            .ids
        )

        root_articles_ids += favorite_articles_ids

        if unfolded_ids is False:
            unfolded_ids = []

        if self.is_article_visible:
            if self.parent_id:
                unfolded_ids += self._get_ancestor_ids_nearest_first()
        elif not self.parent_id and self.id:
            root_articles_ids += [self.id]

        all_visible_articles = self.get_visible_articles(
            root_articles_ids, unfolded_ids
        )

        return {
            "articles": all_visible_articles.read(
                [
                    "name",
                    "icon",
                    "parent_id",
                    "category",
                    "is_locked",
                    "user_can_write",
                    "is_user_favorite",
                    "is_article_item",
                    "has_article_children",
                ],
                None,
            ),
            "favorite_ids": favorite_articles_ids,
            "active_article_accessible_root_id": active_article_accessible_ancestors[
                -1
            ].id
            if active_article_accessible_ancestors
            else False,
        }

    def get_article_hierarchy(self, exclude_article_ids=False):
        self.check_singleton()
        ancestor_ids = self._get_ancestor_ids_nearest_first()
        if exclude_article_ids:
            ancestor_ids.difference_update(exclude_article_ids)
        return (
            self.sudo()
            .browse(reversed(list(ancestor_ids)))
            .read(["display_name", "user_has_access"])
        )
