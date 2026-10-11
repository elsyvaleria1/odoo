import functools
import random
import uuid
from typing import Self

from lxml import etree
from lxml.builder import E

from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools.template_inheritance import apply_inheritance_specs

from ..controllers.keyed_xml_differ import KeyedXmlDiffer

_debug = DebugLog(__name__)

CONTAINER_TYPES = (
    "group",
    "page",
    "sheet",
    "div",
    "ul",
    "li",
    "notebook",
)


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def _get_view_cache_key(self, *args, **kwargs):
        if self.env.context.get("studio"):
            self = self.with_context(no_address_format=True)
        key = super()._get_view_cache_key(*args, **kwargs)
        return key + (self.env.context.get("studio"),)

    @api.model
    def _get_view_field_attributes(self):
        keys = super()._get_view_field_attributes()
        if self.env.context.get("studio"):
            keys.append("manual")
        return keys

    @api.model
    def get_views(self, views, options=None):
        if options and options.get("studio"):
            self = self.with_context(studio=True, no_address_format=True)
        return super().get_views(views, options)


class IrUiView(models.Model):
    _name = "ir.ui.view"
    _description = "View"
    _inherit = ["mixin.studio", "ir.ui.view"]

    TEMPLATE_VIEWS_BLACKLIST = [
        "web.html_container",
        "web.report_layout",
        "web.external_layout",
        "web.internal_layout",
        "web.basic_layout",
        "web.minimal_layout",
        "web.external_layout_striped",
        "web.external_layout_boxed",
        "web.external_layout_bold",
        "web.external_layout_standard",
        "web.external_layout_folder",
        "web.external_layout_wave",
        "web.external_layout_bubble",
    ]

    def _get_closest_primary_view(self):
        self.check_singleton()
        view = self
        while view.mode != "primary":
            view = view.inherit_id
        return view

    def _get_x2many_missing_view_archs(self, field, field_node, node_info):
        missing = super()._get_x2many_missing_view_archs(field, field_node, node_info)
        if not missing or not self.env.context.get("studio"):
            return missing

        for arch in missing:
            arch.set("studio_subview_inlined", "1")

        return missing

    def _postprocess_debug_to_cache(self, tree):
        if self.env.context.get("studio"):
            return tree
        return super()._postprocess_debug_to_cache(tree)

    def _postprocess_debug(self, tree):
        if self.env.context.get("studio"):
            for node in tree.xpath("//*[@__debug__]"):
                node.attrib.pop("__debug__")
            return tree
        else:
            return super()._postprocess_debug(tree)

    def _postprocess_access_rights(self, tree):

        if self.env.context.get("studio"):
            group_definitions = self.env["res.groups"]._get_group_definitions()

            node_groups = {}
            set_invisible_nodes = set()

            for node in tree.xpath("//*[@groups]"):
                if node.get("groups"):
                    node_groups[node] = node.get("groups")

            @functools.cache
            def has_access(groups_key):
                groups = group_definitions.from_key(groups_key)
                return groups.matches(user_group_ids)

            user_group_ids = self.env.user._get_group_ids()
            for node in tree.xpath("//*[@__groups_key__]"):
                if not has_access(node.attrib.pop("__groups_key__")):
                    set_invisible_nodes.add(node)

                if (
                    node.tag == "field"
                    and "model_groups" in node.attrib
                    and not has_access(node.attrib.pop("model_groups"))
                ):
                    node.set("studio_no_fetch", "1")

            def is_in_list(node) -> bool:
                parent = node.getparent()
                return parent is not None and parent.tag == "list"

            for node in set_invisible_nodes:
                if is_in_list(node):
                    column_invisible = "True"
                    node.set("column_invisible", column_invisible)
                else:
                    invisible = "True"
                    node.set("invisible", invisible)

            model = tree.get("model_access_rights")
            res = super()._postprocess_access_rights(tree)

            for node, groups in node_groups.items():
                node.set("groups", groups)
                self.set_studio_groups(node)
            if tree.tag == "map":
                self.set_studio_map_popup_fields(model, tree)
            if tree.tag == "pivot":
                self.set_studio_pivot_measure_fields(model, tree)

            return res

        return super()._postprocess_access_rights(tree)

    def _postprocess_attributes(self, node, name_manager, node_info) -> None:
        if self.env.context.get("studio"):
            groups = node.get("groups", "")
            super()._postprocess_attributes(node, name_manager, node_info)
            if groups:
                node.attrib["groups"] = groups
            if node.tag == "field" and node.get("__groups_key__"):
                node.set("model_groups", node_info["model_groups"].key)
        else:
            super()._postprocess_attributes(node, name_manager, node_info)

    @api.model
    def set_studio_groups(self, node) -> None:
        studio_groups = []
        for xml_id in node.attrib["groups"].split(","):
            forbid = xml_id.startswith("!")
            if forbid:
                xml_id = xml_id[1:]
            group = self.env.ref(xml_id, raise_if_not_found=False)
            if group:
                studio_groups.append(
                    {
                        "id": group.id,
                        "name": group.name,
                        "display_name": group.display_name,
                        "forbid": forbid,
                    }
                )
        node.attrib["studio_groups"] = json_dumps(studio_groups)

    @api.model
    def set_studio_map_popup_fields(self, model, node) -> None:
        field_names = [field.get("name") for field in node.findall("field")]
        field_ids = (
            self.env["ir.model.fields"]
            .search([("model", "=", model), ("name", "in", field_names)])
            .ids
        )
        if field_ids:
            node.attrib["studio_map_field_ids"] = json_dumps(field_ids)

    @api.model
    def set_studio_pivot_measure_fields(self, model, node) -> None:
        field_names = [
            field.get("name")
            for field in node.findall("field")
            if field.get("type") == "measure"
        ]
        field_ids = (
            self.env["ir.model.fields"]
            .search([("model", "=", model), ("name", "in", field_names)])
            .ids
        )
        if field_ids:
            node.attrib["studio_pivot_measure_field_ids"] = json_dumps(field_ids)

    @api.model
    def create_automatic_views(self, res_model):
        model = self.env[res_model]
        views = self.env["ir.ui.view"]
        views |= self.auto_list_view(res_model)
        views |= self.auto_form_view(res_model)
        views |= self.auto_search_view(res_model)
        if "x_studio_date" in model._fields:
            views |= self.auto_calendar_view(res_model)
        if (
            "x_studio_date_start" in model._fields
            and "x_studio_date_stop" in model._fields
        ):
            views |= self.auto_gantt_view(res_model)
        if "x_studio_stage_id" in model._fields:
            views |= self.auto_kanban_view(res_model)
        if "x_studio_partner_id" in model._fields:
            views |= self.auto_map_view(res_model)
        if "x_studio_value" in model._fields:
            views |= self.auto_pivot_view(res_model)
            views |= self.auto_graph_view(res_model)
        return views

    def auto_list_view(self, res_model) -> Self:
        model = self.env[res_model]
        rec_name = model._get_rec_name_fallback()
        fields = []
        if "x_studio_sequence" in model._fields:
            fields.append(E.field(name="x_studio_sequence", widget="handle"))
        fields.append(E.field(name=rec_name))
        if "x_studio_partner_id" in model._fields:
            fields.append(E.field(name="x_studio_partner_id"))
        if "x_studio_user_id" in model._fields:
            fields.append(
                E.field(name="x_studio_user_id", widget="many2one_avatar_user")
            )
        if "x_studio_company_id" in model._fields:
            fields.append(
                E.field(name="x_studio_company_id", groups="base.group_multi_company")
            )
        if (
            "x_studio_currency_id" in model._fields
            and "x_studio_value" in model._fields
        ):
            fields.append(E.field(name="x_studio_currency_id", invisible="1"))
            fields.append(E.field(name="x_studio_value", sum=self.env._("Total")))
        if "x_studio_tag_ids" in model._fields:
            fields.append(
                E.field(
                    name="x_studio_tag_ids",
                    widget="many2many_tags",
                    options="{'color_field': 'x_color'}",
                )
            )
        if "x_color" in model._fields:
            fields.append(E.field(name="x_color", widget="color_picker"))
        order = ["id desc"]
        if "x_studio_sequence" in model._fields:
            order.append("x_studio_sequence asc")
        if "x_studio_priority" in model._fields:
            order.append("x_studio_priority desc")
        order = ",".join(reversed(order))
        tree_params = (
            {}
            if not self.env.context.get("list_editable")
            else {"editable": self.env.context.get("list_editable")}
        )
        tree = E.list(**tree_params, default_order=order)
        tree.extend(fields)
        arch = etree.tostring(tree, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "list",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("list", res_model),
            }
        )

    def auto_form_view(self, res_model) -> Self:
        ir_model = self.env["ir.model"]._get(res_model)
        model = self.env[res_model]
        rec_name = model._get_rec_name_fallback()
        sheet_content = []
        header_content = []
        if "x_studio_stage_id" in model._fields:
            header_content.append(
                E.field(
                    name="x_studio_stage_id",
                    widget="statusbar",
                    options="{'clickable': '1'}",
                )
            )
            sheet_content.append(
                E.field(name="x_studio_kanban_state", widget="state_selection")
            )
        if "x_active" in model._fields:
            sheet_content.append(
                E.widget(
                    name="web_ribbon",
                    text=self.env._("Archived"),
                    bg_color="text-bg-danger",
                    invisible="x_active",
                )
            )
            sheet_content.append(E.field(name="x_active", invisible="1"))
        if "x_studio_image" in model._fields:
            sheet_content.append(
                E.field(
                    {"class": "oe_avatar", "widget": "image", "name": "x_studio_image"}
                )
            )
        title = etree.fromstring(
            """
            <div class="oe_title">
                <h1>
                    <field name="%(field_name)s" required="1" placeholder="Name..."/>
                </h1>
            </div>
        """
            % {"field_name": rec_name}
        )
        sheet_content.append(title)
        group_name = "studio_group_" + str(uuid.uuid4())[:6]
        left_group = E.group(name=group_name + "_left")
        right_group = E.group(name=group_name + "_right")
        left_group_content, right_group_content = [], []
        if "x_studio_user_id" in model._fields:
            right_group_content.append(
                E.field(name="x_studio_user_id", widget="many2one_avatar_user")
            )
        if "x_studio_partner_id" in model._fields:
            left_group_content.append(E.field(name="x_studio_partner_id"))
            left_group_content.append(
                E.field(name="x_studio_partner_phone", widget="many2many_tags")
            )
            left_group_content.append(
                E.field(name="x_studio_partner_email", widget="email")
            )
        if (
            "x_studio_currency_id" in model._fields
            and "x_studio_value" in model._fields
        ):
            right_group_content.append(
                E.field(name="x_studio_currency_id", invisible="1")
            )
            right_group_content.append(E.field(name="x_studio_value"))
        if "x_studio_tag_ids" in model._fields:
            right_group_content.append(
                E.field(
                    name="x_studio_tag_ids",
                    widget="many2many_tags",
                    options="{'color_field': 'x_color'}",
                )
            )
        if "x_studio_company_id" in model._fields:
            right_group_content.append(
                E.field(
                    name="x_studio_company_id",
                    groups="base.group_multi_company",
                    options="{'no_create': True}",
                )
            )
        if "x_studio_date" in model._fields:
            left_group_content.append(E.field(name="x_studio_date"))
        if (
            "x_studio_date_start" in model._fields
            and "x_studio_date_stop" in model._fields
        ):
            left_group_content.append(
                E.field(
                    name="x_studio_date_start",
                    string="Dates",
                    widget="daterange",
                    options="{'end_date_field': 'x_studio_date_stop'}",
                )
            )
            left_group_content.append(E.field(name="x_studio_date_stop", invisible="1"))
        if not left_group_content:
            left_group_content = right_group_content
            right_group_content = []
        left_group.extend(left_group_content)
        right_group.extend(right_group_content)
        sheet_content.append(E.group(left_group, right_group, name=group_name))
        if "x_studio_notes" in model._fields:
            sheet_content.append(
                E.group(
                    E.field(
                        name="x_studio_notes",
                        placeholder=self.env._("Type down your notes here..."),
                        nolabel="1",
                        colspan="2",
                    )
                )
            )

        lines_field = [f for f in model._fields if ("%s_line_ids" % model._name) in f]
        if lines_field:
            xml_node = E.notebook()
            xml_node_page = E.page({"string": "Details", "name": "lines"})
            xml_node_page.append(E.field(name=lines_field[0]))

            xml_node.insert(0, xml_node_page)
            sheet_content.append(xml_node)

        form = E.form(
            E.header(*header_content),
            E.sheet(*sheet_content, string=model._description),
        )
        if ir_model.is_mail_thread:
            form.append(E.chatter())
        arch = etree.tostring(form, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "form",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("form", res_model),
            }
        )

    def auto_search_view(self, res_model) -> Self:
        model = self.env[res_model]
        rec_name = model._get_rec_name_fallback()
        fields = []
        filters = []
        groupbys = []
        fields.append(E.field(name=rec_name))
        if isinstance(model, self.pool["mixin.mail.activity"]):
            filters.append(
                E.filter(
                    name="filter_activities_my",
                    domain="[['activity_user_id', '=', uid]]",
                )
            )
        if "x_studio_partner_id" in model._fields:
            fields.append(E.field(name="x_studio_partner_id", operator="child_of"))
            groupbys.append(
                E.filter(
                    name="groupby_x_partner",
                    string=self.env._("Partner"),
                    context="{'group_by': 'x_studio_partner_id'}",
                    domain="[]",
                )
            )
        if "x_studio_user_id" in model._fields:
            fields.append(E.field(name="x_studio_user_id"))
            filters.append(
                E.filter(
                    string=self.env._("My %s", model._description),
                    name="my_%s" % res_model,
                    domain="[['x_studio_user_id', '=', uid]]",
                )
            )
            groupbys.append(
                E.filter(
                    name="groupby_x_user",
                    string=self.env._("Responsible"),
                    context="{'group_by': 'x_studio_user_id'}",
                    domain="[]",
                )
            )
        date_filters = []
        if "x_studio_date" in model._fields:
            date_filters.append(
                E.filter(
                    date="x_studio_date",
                    name="studio_filter_date",
                    string=self.env._("Date"),
                )
            )
        if (
            "x_studio_date_start" in model._fields
            and "x_studio_date_stop" in model._fields
        ):
            date_filters.append(
                E.filter(
                    date="x_studio_date_start",
                    name="studio_filter_date_start",
                    string=self.env._("Start Date"),
                )
            )
            date_filters.append(
                E.filter(
                    date="x_studio_date_stop",
                    name="studio_filter_date_stop",
                    string=self.env._("End Date"),
                )
            )
        if date_filters:
            filters.append(E.separator())
            filters.extend(date_filters)
        if "x_active" in model._fields:
            filters.append(E.separator())
            filters.append(
                E.filter(
                    string=self.env._("Archived"),
                    name="archived_%s" % res_model,
                    domain="[['x_active', '=', False]]",
                )
            )
            filters.append(E.separator())
        if "x_studio_tag_ids" in model._fields:
            fields.append(E.field(name="x_studio_tag_ids"))
        if "x_studio_stage_id" in model._fields:
            groupbys.append(
                E.filter(
                    name="x_studio_stage_id",
                    string=self.env._("Stage"),
                    context="{'group_by': 'x_studio_stage_id'}",
                    domain="[]",
                )
            )
        search = E.search(*fields)
        search.extend(filters)
        if groupbys:
            groupby = E.group(string=self.env._("Group By"))
            groupby.extend(groupbys)
            search.extend(groupby)
        arch = etree.tostring(search, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "search",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("search", res_model),
            }
        )

    def auto_calendar_view(self, res_model) -> Self:
        model = self.env[res_model]
        if "x_studio_date" not in model._fields:
            return self
        calendar = E.calendar(date_start="x_studio_date", create_name_field="x_name")
        arch = etree.tostring(calendar, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "calendar",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("calendar", res_model),
            }
        )

    def auto_gantt_view(self, res_model) -> Self:
        gantt = E.gantt(
            date_start="x_studio_date_start", date_stop="x_studio_date_stop"
        )
        arch = etree.tostring(gantt, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "gantt",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("gantt", res_model),
            }
        )

    def auto_map_view(self, res_model) -> Self:
        field = E.field(name="x_studio_partner_id", string=self.env._("Partner"))
        map_view = E.map(field, res_partner="x_studio_partner_id")
        arch = etree.tostring(map_view, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "map",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("map", res_model),
            }
        )

    def auto_pivot_view(self, res_model) -> Self:
        model = self.env[res_model]
        fields = []
        fields.append(E.field(name="x_studio_value", type="measure"))
        if "x_studio_stage_id" in model._fields:
            fields.append(E.field(name="x_studio_stage_id", type="col"))
        if "x_studio_date" in model._fields:
            fields.append(E.field(name="x_studio_date", type="row"))
        pivot = E.pivot(sample="1")
        pivot.extend(fields)
        arch = etree.tostring(pivot, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "pivot",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("pivot", res_model),
            }
        )

    def auto_graph_view(self, res_model) -> Self:
        fields = []
        fields.append(E.field(name="x_studio_value", type="measure"))
        fields.append(E.field(name="create_date", type="row"))
        graph = E.graph(sample="1")
        graph.extend(fields)
        arch = etree.tostring(graph, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "graph",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("graph", res_model),
            }
        )

    def auto_kanban_view(self, res_model) -> Self:
        model = self.env[res_model]
        pre_fields = []
        pre_fields.append(E.field(name="x_color"))
        card_main = E.main()
        card_header = E.div({"name": "studio_auto_kanban_header", "class": "d-flex"})
        card_header.append(
            E.field(name="x_studio_priority", widget="boolean_favorite", nolabel="1")
        )
        card_header.append(E.field({"name": "display_name", "class": "h5"}))
        card_body = E.div({"name": "studio_auto_kanban_body"})
        card_footer = E.footer()
        bottom_right_div = E.div({"class": "ms-auto d-flex align-items-center"})
        card_main.extend([card_header, card_body, card_footer])
        if "x_studio_sequence" in model._fields:
            card_header.append(
                E.field(name="x_studio_sequence", widget="handle", invisible="1")
            )
        if "x_studio_kanban_state" in model._fields:
            status = E.field(name="x_studio_kanban_state", widget="state_selection")
            bottom_right_div.append(status)
        if "x_studio_user_id" in model._fields:
            img = E.field(
                {
                    "class": "ms-1",
                    "name": "x_studio_user_id",
                    "widget": "kanban.many2one_avatar_user",
                }
            )
            bottom_right_div.append(img)
        if "x_studio_value" and "x_studio_currency_id" in model._fields:
            pre_fields.append(E.field(name="x_studio_currency_id"))
            card_footer.append(E.field(name="x_studio_value"))
        if "x_studio_tag_ids" in model._fields:
            card_body.append(
                E.field(name="x_studio_tag_ids", options="{'color_field': 'x_color'}")
            )
        kanban_card = E.t({"t-name": "card", "class": "flex-row"})
        if "x_studio_image" in model._fields:
            image_field = E.field(
                {
                    "name": "x_studio_image",
                    "widget": "image",
                    "options": '{"zoom": true, "background": true, "preventClicks": false}',
                }
            )
            card_aside = E.aside()
            card_aside.append(image_field)
            kanban_card.append(card_aside)
        card_footer.append(bottom_right_div)
        kanban_card.append(card_main)
        kanban_menu = E.t({"t-name": "menu"})
        kanban_menu.extend(
            [
                E.a(
                    {
                        "t-if": "widget.editable",
                        "role": "menuitem",
                        "type": "open",
                        "class": "dropdown-item",
                    },
                    self.env._("Edit"),
                ),
                E.a(
                    {
                        "t-if": "widget.deletable",
                        "role": "menuitem",
                        "type": "delete",
                        "class": "dropdown-item",
                    },
                    self.env._("Delete"),
                ),
                E.field({"widget": "kanban_color_picker", "name": "x_color"}),
            ]
        )
        templates = E.templates(kanban_menu, kanban_card)
        order = (
            "x_studio_priority desc,x_studio_sequence asc,id desc"
            if "x_studio_sequence" in model._fields
            else "x_studio_priority desc,id desc"
        )
        kanban = E.kanban(
            default_group_by="x_studio_stage_id",
            default_order=order,
            highlight_color="x_color",
        )
        kanban.extend(pre_fields)
        if "x_studio_value" in model._fields:
            progressbar = E.progressbar(
                field="x_studio_kanban_state",
                colors='{"normal": "200", "done": "success", "blocked": "danger"}',
                sum_field="x_studio_value",
            )
        else:
            progressbar = E.progressbar(
                field="x_studio_kanban_state",
                colors='{"normal": "200", "done": "success", "blocked": "danger"}',
            )
        kanban.append(progressbar)
        kanban.append(templates)
        arch = etree.tostring(kanban, encoding="unicode", pretty_print=True)

        return self.create(
            {
                "type": "kanban",
                "model": res_model,
                "arch": arch,
                "name": "Default %s view for %s" % ("kanban", res_model),
            }
        )

    def _is_studio_view(self) -> bool:
        return self.xml_id.startswith("studio_customization")

    def _apply_studio_specs(self, source, specs_tree):
        specs = (
            specs_tree.iterchildren(tag=etree.Element)
            if specs_tree.tag == "data"
            else [specs_tree]
        )
        for spec in specs:
            if self.env.context.get("studio"):
                source = super().apply_inheritance_specs(source, spec)
                continue
            try:
                source = super().apply_inheritance_specs(source, spec)
            except ValueError as e:
                _debug.logic(
                    "studio_spec_skipped",
                    view=self.id,
                    spec=spec.tag,
                    expr=spec.get("expr"),
                    error=type(e).__name__,
                )
        return source

    @api.model
    def apply_inheritance_specs(self, source, specs_tree):
        if self and self._is_studio_view():
            return self._apply_studio_specs(source, specs_tree)
        return super().apply_inheritance_specs(source, specs_tree)

    def normalize(self, arch_to_normalize=None):
        if self.mode == "primary":
            base_arch = self.get_combined_arch()
        else:
            base_arch = self.with_context(
                ir_ui_view_tree_cut_off_view=self
            ).get_combined_arch()
            arch_to_normalize = arch_to_normalize or self.arch

        if not arch_to_normalize or not base_arch:
            return ""

        return self.normalize_with_keyed_tree(
            base_arch=base_arch, arch_to_normalize=arch_to_normalize
        )

    @api.model
    def normalize_with_keyed_tree(self, base_arch, arch_to_normalize) -> str:
        old_tree = etree.fromstring(base_arch)
        KeyedXmlDiffer.update_node_ids_for_diff(old_tree)
        old_str = etree.tostring(old_tree)

        new_tree = apply_inheritance_specs(
            old_tree, etree.fromstring(arch_to_normalize)
        )

        def on_new_node(node):
            if node.tag in CONTAINER_TYPES and not node.get("name"):
                uid = str(uuid.UUID(int=random.getrandbits(128)))[:6]
                node.set("name", "studio_%s_%s" % (node.tag, uid))

        def is_subtree(node) -> bool:
            parent = node.getparent()
            return parent is None or parent.tag == "field"

        def get_moving_candidate_key(node):
            return ("field", node.get("name")) if node.tag == "field" else None

        return KeyedXmlDiffer(
            on_new_node=on_new_node,
            is_subtree=is_subtree,
            get_moving_candidate_key=get_moving_candidate_key,
        ).diff_xpath(old_str, etree.tostring(new_tree), flat=True)

    def copy_qweb_template(self):
        new = self.copy()
        new.inherit_id = False

        domain = [
            ("type", "=", "qweb"),
            ("key", "!=", self.key),
            ("key", "=like", "%s_copy_%%" % self.key),
            "!",
            ("key", "=like", "%s_copy_%%_copy_%%" % self.key),
        ]
        old_copies = self.with_context(active_test=False).search_read(
            domain, order="key desc"
        )
        nos = [
            int(old_copy.get("key").split("_copy_").pop()) for old_copy in old_copies
        ]
        copy_no = ((nos and max(nos)) or 0) + 1
        new_key = "%s_copy_%s" % (self.key, copy_no)

        cloned_templates = self.env.context.get("cloned_templates", {})
        source_key = self.key
        self = self.with_context(cloned_templates=cloned_templates)
        cloned_templates[source_key] = new_key

        arch_tree = self._get_view_etrees()[0]

        for node in arch_tree.findall(".//t[@t-call]"):
            tcall = node.get("t-call")
            if "{" in tcall:
                continue
            if tcall in self.TEMPLATE_VIEWS_BLACKLIST:
                continue
            if tcall not in cloned_templates:
                callview = self.search(
                    [("type", "=", "qweb"), ("key", "=", tcall)], limit=1
                )
                if not callview:
                    raise UserError(self.env._("Template '%s' not found", tcall))
                callview.copy_qweb_template()
            node.set("t-call", cloned_templates[tcall])

        subtree = arch_tree.xpath("//*[@t-name]")
        if subtree:
            subtree[0].set("t-name", new_key)
            arch_tree = subtree[0]

        root = self
        view_ids = []
        while True:
            view_ids.append(root.id)
            if not root.inherit_id:
                break
            root = root.inherit_id
        combined_views = self.browse(view_ids)._get_views_inheriting()

        new.write(
            {
                "name": "%s copy(%s)" % (new.name, copy_no),
                "key": new_key,
                "arch_base": etree.tostring(arch_tree, encoding="unicode"),
            }
        )

        fields_to_ignore = {field for field in self._fields if field != "arch_db"}
        for view in combined_views - self:
            view.copy_translations(new, fields_to_ignore)

        return new

    def _is_subtree_branded(self, node) -> bool:
        if not self.env.context.get("studio"):
            return super()._is_subtree_branded(node)
        if node.tag == "t" and ("t-raw" in node.attrib or "t-call" in node.attrib):
            return True
        return any(self.is_node_branded(child) for child in node.iterdescendants())

    def is_node_branded(self, node) -> bool:
        if self.env.context.get("studio"):
            if "data-oe-model" in node.attrib:
                return True
            if (
                node.tag is etree.ProcessingInstruction
                and node.target == "apply-inheritance-specs-node-removal"
            ):
                return True
            if any(
                att in ("t-out", "t-raw", "t-esc") and node.get(att) == "0"
                for att in node.attrib
            ):
                return True
            if node.tag == "t" and "t-set" in node.attrib and len(node) > 0:
                return True
            return node.tag == "t" and "t-call" in node.attrib
        return super().is_node_branded(node)

    @api.model
    def save_embedded_field(self, el):
        if self.env.context.get("studio"):
            return None
        return super().save_embedded_field(el)
