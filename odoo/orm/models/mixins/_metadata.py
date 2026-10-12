import typing

from odoo.libs.collections import OrderedSet, frozendict
from odoo.libs.sql import SQL

from ._model_stubs import _ModelStubs

if typing.TYPE_CHECKING:
    from collections.abc import Iterable
    from types import MappingProxyType

    from ..._typing import BaseModel
    from ...fields.base import Field
    from ...runtime import Registry
    from ..anchors import Anchor
    from ..table_objects import TableObject


class _ModelMetadataMixin(_ModelStubs):
    __slots__ = ()

    pool: Registry

    _fields__: dict[str, Field[typing.Any]]
    _fields: MappingProxyType[str, Field[typing.Any]]

    _auto: bool = False
    _abstract: bool = True
    _transient: bool = False
    _is_registry_metadata: bool = False

    # Framework base classes are unnamed; registered classes supply a name.
    _name: str | None = None  # type: ignore[assignment]  # Lifecycle stubs describe initialized registry models, not unnamed prototypes.
    _description: str | None = None
    _module: str | None = None
    _custom: bool = False

    @classmethod
    @typing.override
    def _get_model_name(cls) -> str:
        if cls._name is None:
            raise TypeError(f"{cls.__name__} is not a named registry model")
        return cls._name

    _inherit: str | list[str] | tuple[str, ...] = ()
    _inherits: dict[str, str] = frozendict()
    _table: str = ""
    _table_query: SQL | str | None = None
    _table_objects: dict[str, TableObject] = frozendict()
    _table_inheritance_root: str = ""
    _inherit_children: OrderedSet[str]
    _inherit_module: dict[str, str | None]

    _base_classes__: tuple[type[BaseModel], ...]
    _model_classes__: tuple[type, ...]
    _setup_done__: bool

    _rec_name: str | None = None
    _rec_names_search: list[str] | None = None
    _name_create_on_import: bool = False
    _order: str = "id"
    _parent_name: str = "parent_id"
    _parent_store: bool = False
    _active_name: str | None = None
    _display_name_column: str | tuple[str, ...] | None = None
    _display_name_column_guard: str | None = None
    _display_name_context_keys: tuple[str, ...] = ()
    _display_name_search_default: bool = False
    _display_name_search_exact: tuple[str, ...] = ()
    _inherits_sudo_fields: tuple[str, ...] = ()
    _inherits_shared_id: str = ""
    _inherits_rules: bool = True
    _access_anchors: frozendict[str, str | Anchor] = frozendict()
    _access_audit: bool = False
    _access_residual_class: str | None = None
    _access_label_field: str | None = None
    _fold_name: str = "fold"

    _translate: bool = True
    _check_company_auto: bool = False
    _search_visibility_fields: tuple[str, ...] | None = None

    _allow_sudo_commands: bool = True

    _depends: frozendict[str, Iterable[str]] = frozendict()
    _legacy_field_names: frozendict[str, str] = frozendict()
    _access_verbs: typing.ClassVar[dict[str, typing.Any]] = {}

    @property
    @typing.override
    def _table_sql(self) -> SQL:
        table_query = self._table_query
        if table_query and isinstance(table_query, SQL):
            table_sql = SQL("(%s)", table_query)
        elif table_query:
            table_sql = SQL(f"({table_query})")
        else:
            table_sql = SQL.identifier(self._table)
        if not self._depends:
            return table_sql

        return SQL.EMPTY.join(
            [
                table_sql,
                *(
                    SQL(to_flush=field)
                    for field in self.pool.depends_flush_fields(
                        typing.cast("BaseModel", self)
                    )
                ),
            ]
        )

    def _get_depends_closure(self) -> tuple[set[str], OrderedSet[Field[typing.Any]]]:
        fields_to_flush: OrderedSet[Field[typing.Any]] = OrderedSet()
        seen: set[str] = {self._get_model_name()}
        models = [self]
        while models:
            current_model = models.pop()
            for model_name, field_names in current_model._depends.items():
                model = self.env[model_name]
                if model_name not in seen:
                    seen.add(model_name)
                    models.append(model)
                fields_to_flush.update(model._fields[fname] for fname in field_names)
        return seen, fields_to_flush

    @typing.override
    def _is_an_ordinary_table(self) -> bool:
        return self.pool.is_an_ordinary_table(self)

    @typing.override
    def _is_table_inheritance_root(self) -> bool:
        return bool(self._table) and self._table == self._table_inheritance_root

    @typing.override
    def _get_root_model_name(self) -> str:
        root_table = self._table_inheritance_root
        for name in self.pool.model_names_by_inheritance_root.get(root_table, ()):
            if self.pool[name]._table == root_table:
                return name
        return self._get_model_name()

    def _get_reference_model_name(self) -> str:
        if parent := self._get_inherits_shared_parent():
            return self.env[parent]._get_reference_model_name()
        return self._get_model_name()

    @typing.override
    def _get_inherits_shared_parent(self) -> str:
        for parent, field_name in self._inherits.items():
            if field_name == self._inherits_shared_id:
                return parent
        return ""
