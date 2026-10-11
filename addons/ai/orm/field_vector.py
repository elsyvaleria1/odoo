from odoo import fields
from odoo.libs.json import loads as json_loads


def pg_vector(size) -> str:
    if not isinstance(size, int):
        raise TypeError(f"vector size should be an int, got {size!r}")
    if size > 0:
        return "vector(%d)" % size
    return "vector"


class Vector(fields.Field):
    type = "vector"
    size = None

    def _setup_attrs__(self, model_class, name: str) -> None:
        super()._setup_attrs__(model_class, name)
        assert self.size is None or isinstance(self.size, int), (
            "Vector field %s with non-integer size %r" % (self, self.size)
        )

    @property
    def _column_type(self):
        return ("vector", pg_vector(self.size))

    def convert_to_cache(self, value, record, validate=True):
        if value is None or value is False:
            return None
        return str(value)

    def convert_to_column(self, value, record, values=None, validate=True):
        if isinstance(value, (list, tuple)):
            return str(list(value))
        return super().convert_to_column(value, record, values, validate)

    def convert_to_record(self, value, record):
        return False if value is None else json_loads(value)
