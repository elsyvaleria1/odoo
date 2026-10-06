import typing
import uuid

from odoo.exceptions import MissingError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import fast_clone
from odoo.libs.utils import has_list_types, is_list_of

from .._recordset import is_recordset
from ._property_values import RELATIONAL_PROPERTY_TYPES
from .base import Field

if typing.TYPE_CHECKING:
    from .properties import Property

    _PropertiesMixinBase = Field[Property]
else:
    _PropertiesMixinBase = object

_debug = DebugLog("odoo.orm.fields.properties")


NoneType = type(None)


def _visible_names(records: typing.Any) -> dict[int, str | None]:
    # the existence check costs a query, paid only when a target is gone
    try:
        names = records._visible_display_names()
    except MissingError:
        names = records.exists()._visible_display_names()
    return typing.cast("dict[int, str | None]", names)


class _PropertiesJsonMixin(_PropertiesMixinBase):
    __slots__ = ()

    if typing.TYPE_CHECKING:
        ALLOWED_TYPES: tuple[str, ...]

    @classmethod
    def _add_display_name(
        cls,
        values_list: list[dict[str, typing.Any]],
        env: typing.Any,
        value_keys: tuple[str, ...] = ("value", "default"),
    ) -> None:
        for property_definition in values_list:
            property_type = property_definition.get("type")
            property_model = property_definition.get("comodel")
            if not property_model:
                continue

            for value_key in value_keys:
                property_value = property_definition.get(value_key)

                if (
                    property_type == "many2one"
                    and property_value
                    and isinstance(property_value, int)
                ):
                    names = _visible_names(env[property_model].browse(property_value))
                    property_definition[value_key] = (
                        (property_value, names[property_value])
                        if property_value in names
                        else False
                    )

                elif (
                    property_type == "many2many"
                    and property_value
                    and is_list_of(property_value, int)
                ):
                    names = _visible_names(env[property_model].browse(property_value))
                    property_definition[value_key] = [
                        (id_, names[id_]) for id_ in property_value if id_ in names
                    ]

    @classmethod
    def _remove_display_name(
        cls,
        values_list: list[dict[str, typing.Any]],
        value_key: str = "value",
    ) -> None:
        for property_definition in values_list:
            if not isinstance(property_definition, dict) or not property_definition.get(
                "name"
            ):
                continue

            property_value = property_definition.get(value_key)
            if not property_value:
                continue

            property_type = property_definition.get("type")

            if property_type == "many2one" and has_list_types(
                property_value, [int, (str, NoneType)]
            ):
                property_definition[value_key] = property_value[0]

            elif property_type == "many2many":
                if is_list_of(property_value, (list, tuple)):
                    property_definition[value_key] = [
                        many2many_value[0] for many2many_value in property_value
                    ]

    @classmethod
    def _add_missing_names(cls, values_list: list[dict[str, typing.Any]]) -> None:
        generated = 0  # debuglog
        for definition in values_list:
            if definition.get("definition_changed") and not definition.get("name"):
                definition["name"] = str(uuid.uuid4()).replace("-", "")[:16]
                generated += 1  # debuglog
        if _debug.lifecycle.enabled and generated:
            _debug.lifecycle(
                "field.properties.names_generated",
                generated=generated,
                properties=len(values_list),
            )

    @classmethod
    def _parse_json_types(
        cls,
        values_list: list[dict[str, typing.Any]],
        env: typing.Any,
        res_ids_per_model: dict[str, set[int]],
    ) -> None:
        for property_definition in values_list:
            property_value = property_definition.get("value")
            property_type = property_definition.get("type")
            res_model = property_definition.get("comodel") or ""

            if property_type not in cls.ALLOWED_TYPES:
                raise ValueError(f"Wrong property type {property_type!r}")

            if property_value is None:
                continue

            if property_type == "boolean":
                property_value = bool(property_value)

            elif property_type in ("char", "text") and not isinstance(
                property_value, str
            ):
                property_value = False

            elif property_value and property_type == "selection":
                options = property_definition.get("selection") or []
                options = {option[0] for option in options if option}
                if property_value not in options:
                    property_value = False

            elif property_value and property_type == "tags":
                all_tags = {tag[0] for tag in property_definition.get("tags") or ()}
                property_value = [tag for tag in property_value if tag in all_tags]

            elif property_type == "many2one":
                if (
                    not isinstance(property_value, int)
                    or res_model not in env
                    or property_value not in res_ids_per_model[res_model]
                ):
                    property_value = False

            elif property_type == "many2many":
                if not is_list_of(property_value, int):
                    property_value = []

                elif len(property_value) != len(set(property_value)):
                    property_value = list(dict.fromkeys(property_value))

                property_value = (
                    [
                        id_
                        for id_ in property_value
                        if id_ in res_ids_per_model[res_model]
                    ]
                    if res_model in env
                    else []
                )

            elif property_type == "html":
                property_value = (
                    property_definition["name"].endswith("_html") and property_value
                )

            if (
                _debug.logic.enabled
                and property_value in (False, [])
                and property_definition.get("value") not in (False, [], None)
            ):
                _debug.logic(
                    "field.properties.value_rejected",
                    property=property_definition.get("name"),
                    property_type=property_type,
                    comodel=res_model or None,
                )
            property_definition["value"] = property_value

    @classmethod
    def _list_to_dict(
        cls, values_list: list[dict[str, typing.Any]]
    ) -> dict[str, typing.Any]:
        if not is_list_of(values_list, dict):
            raise ValueError(f"Wrong properties value {values_list!r}")

        cls._add_missing_names(values_list)

        dict_value = {}
        for property_definition in values_list:
            property_value = property_definition.get("value")
            property_type = property_definition.get("type")
            property_model = property_definition.get("comodel")
            if property_value is None:
                continue

            if is_recordset(property_value):
                property_value = (
                    property_value.id
                    if property_type == "many2one"
                    else property_value.ids
                )
            if property_type not in ("integer", "float") or property_value != 0:
                property_value = property_value or False
            if (
                property_type in RELATIONAL_PROPERTY_TYPES
                and property_model
                and property_value
            ):
                if (
                    property_type == "many2many"
                    and property_value
                    and not is_list_of(property_value, int)
                ):
                    raise ValueError(f"Wrong many2many value {property_value!r}")

                if property_type == "many2one" and not isinstance(property_value, int):
                    raise ValueError(f"Wrong many2one value {property_value!r}")

            dict_value[property_definition["name"]] = property_value

        return dict_value

    @classmethod
    def _dict_to_list(
        cls,
        values_dict: dict[str, typing.Any],
        properties_definition: list[dict[str, typing.Any]],
    ) -> list[dict[str, typing.Any]]:
        if not is_list_of(properties_definition, dict):
            raise ValueError(f"Wrong properties value {properties_definition!r}")

        values_list = fast_clone(properties_definition)
        for property_definition in values_list:
            if property_definition["name"] in values_dict:
                property_definition["value"] = values_dict[property_definition["name"]]
            else:
                property_definition.pop("value", None)
        return values_list
