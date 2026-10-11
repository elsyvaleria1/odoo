import difflib
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .geo_types import GEO_FIELD_TTYPES
from odoo.addons.base.models.ir_ui_view_arch import ElementHandler, register

_ARCH_FALSY = re.compile(r"^(false|0)$", re.IGNORECASE)


def _arch_flag(node, name: str, default: bool = False) -> bool:
    value = node.get(name)
    if value is None:
        return default
    return bool(value) and not _ARCH_FALSY.match(value)


class IrUIView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(
        selection_add=[("geoengine", "GeoEngine")],
        ondelete={"geoengine": "cascade"},
    )
    raster_layer_ids = fields.One2many(
        comodel_name="geoengine.raster.layer",
        inverse_name="view_id",
    )
    vector_layer_ids = fields.One2many(
        comodel_name="geoengine.vector.layer",
        inverse_name="view_id",
    )
    map_settings_ids = fields.One2many(
        comodel_name="geoengine.view.settings",
        inverse_name="view_id",
        string="Map Settings Records",
    )
    map_settings_id = fields.Many2one(
        comodel_name="geoengine.view.settings",
        compute="_compute_map_settings_id",
        inverse="_inverse_map_settings_id",
        help="Projection, extents, zoom, render engine and controls of the map. "
        "A geoengine view without one uses the defaults.",
    )

    @api.depends("map_settings_ids")
    def _compute_map_settings_id(self) -> None:
        for view in self:
            view.map_settings_id = view.map_settings_ids[:1]

    def _inverse_map_settings_id(self) -> None:
        for view in self:
            if view.map_settings_id and view.map_settings_id.view_id != view:
                view.map_settings_id.view_id = view

    def _map_settings(self):
        self.check_singleton()
        return self.map_settings_id or self.env["geoengine.view.settings"].new(
            {"view_id": self.id}
        )

    def _get_view_info(self):
        return {
            "geoengine": {"icon": "fa-solid fa-earth-americas"}
        } | super()._get_view_info()

    def _is_qweb_based_view(self, view_type) -> bool:
        return bool(view_type == "geoengine" or super()._is_qweb_based_view(view_type))

    def _check_info_box_template(self, arch, model_name) -> None:
        info_box_template = arch.xpath('//templates/t[@t-name="info_box"]')
        if not info_box_template:
            raise ValidationError(
                self.env._(
                    "Geoengine view for model '%(model)s' requires a template with "
                    "t-name='info_box' to display feature popups.\n\n"
                    "Add this to your view XML:\n"
                    "<templates>\n"
                    "    <t t-name='info_box'>\n"
                    "        <div>\n"
                    "            <strong><t t-out='record.display_name'/></strong>\n"
                    "        </div>\n"
                    "    </t>\n"
                    "</templates>",
                    model=model_name,
                )
            )

    def _check_geometry_field_present(self, arch, model_name, model_fields) -> None:
        for field_node in arch.xpath("//field"):
            field_name = field_node.get("name")
            if (
                field_name
                and field_name in model_fields
                and model_fields[field_name].type in GEO_FIELD_TTYPES
            ):
                return
        raise ValidationError(
            self.env._(
                "The geoengine view for '%(model)s' declares no geometry field. "
                "A map draws PostGIS geometry, so the arch must include one:\n\n"
                "   <geoengine>\n"
                "       <field name='the_geom'/>  <!-- geo_point, geo_polygon, ... -->\n"
                "   </geoengine>",
                model=model_name,
            )
        )

    def _check_client_attributes(
        self, arch, model_name, model_fields, fields_in_view
    ) -> None:
        for attribute in ("features_list_field", "features_list_group_by"):
            if field_name := arch.get(attribute):
                self._check_view_field(
                    attribute, field_name, model_name, model_fields, fields_in_view
                )
        if order := arch.get("default_order"):
            for term in order.split(","):
                field_name = term.strip().split(" ")[0]
                if field_name and field_name not in model_fields:
                    raise ValidationError(
                        self.env._(
                            "default_order='%(order)s' on the geoengine view for "
                            "'%(model)s' names '%(field)s', which is not a field. "
                            "Did you mean: %(suggestions)s",
                            order=order,
                            model=model_name,
                            field=field_name,
                            suggestions=self._suggest_fields(field_name, model_fields),
                        )
                    )

    def _check_webgl_trail_configuration(
        self, arch, model_name, model_fields, fields_in_view
    ) -> None:
        for attribute, default in (
            ("trail_timestamps_field", "trail_timestamps"),
            ("trail_color_field", "trail_color"),
        ):
            self._check_view_field(
                attribute,
                arch.get(attribute) or default,
                model_name,
                model_fields,
                fields_in_view,
            )

    def _check_view_field(
        self, attribute, field_name, model_name, model_fields, fields_in_view
    ) -> None:
        if field_name not in model_fields:
            raise ValidationError(
                self.env._(
                    "%(attribute)s='%(field)s' in the geoengine view for "
                    "'%(model)s' names a field that does not exist.\n\n"
                    "Did you mean: %(suggestions)s",
                    attribute=attribute,
                    field=field_name,
                    model=model_name,
                    suggestions=self._suggest_fields(field_name, model_fields),
                )
            )
        if field_name not in fields_in_view:
            raise ValidationError(
                self.env._(
                    "%(attribute)s='%(field)s' is set on the geoengine view for "
                    "'%(model)s' but the field is not declared in it.\n\n"
                    "Add this to your view XML:\n"
                    "    <field name='%(field)s'/>",
                    attribute=attribute,
                    field=field_name,
                    model=model_name,
                )
            )

    @staticmethod
    def _suggest_fields(field_name, model_fields, limit=5) -> str:
        close = difflib.get_close_matches(field_name, model_fields, n=limit, cutoff=0.5)
        return ", ".join(close or sorted(model_fields)[:limit])


@register("geoengine")
class GeoengineHandler(ElementHandler):
    __slots__ = ()

    def postprocess(self, view, node, name_manager, node_info) -> None:
        model_name = name_manager.model._name
        model_fields = name_manager.model._fields
        view._check_info_box_template(node, model_name)
        view._check_geometry_field_present(node, model_name, model_fields)
        fields_in_view = {field.get("name") for field in node.xpath("//field[@name]")}
        view._check_client_attributes(node, model_name, model_fields, fields_in_view)
        if _arch_flag(node, "webgl_trail"):
            view._check_webgl_trail_configuration(
                node, model_name, model_fields, fields_in_view
            )
