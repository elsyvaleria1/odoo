import logging

from odoo.tools import view_validation

_logger = logging.getLogger(__name__)

_SINGLETON_FIELD_TYPES = frozenset({"col", "measure", "readonly"})


@view_validation.register_validator("grid")
def valid_field_types(arch, **kwargs) -> bool:
    seen = set()
    for f in arch.iterdescendants("field"):
        field_type = f.get("type", "row")
        if field_type == "row":
            continue

        if field_type not in _SINGLETON_FIELD_TYPES:
            _logger.error(
                "grid view: <field name=%r> has unknown type %r, expected one of %s",
                f.get("name"),
                field_type,
                ", ".join(sorted(_SINGLETON_FIELD_TYPES | {"row"})),
            )
            return False
        if field_type in seen:
            _logger.error(
                "grid view: a second <field name=%r type=%r>; it may appear only once",
                f.get("name"),
                field_type,
            )
            return False
        seen.add(field_type)

    return True
