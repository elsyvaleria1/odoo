from __future__ import annotations

from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Literal, Protocol, Self, overload

if TYPE_CHECKING:
    from odoo.exceptions import AccessError
    from odoo.libs.collections import OrderedSet

    from ._typing import DomainType
    from .domain import Domain
    from .primitives import IdType


class RecordsetProtocol(Protocol):
    id: Any
    _fields: Any

    @property
    def ids(self) -> list[int]: ...

    def __bool__(self) -> bool: ...

    def __len__(self) -> int: ...

    def __iter__(self) -> Iterator[Self]: ...

    def __add__(self, other: Self) -> Self: ...

    @overload
    def __getitem__(self, key: int | slice) -> Self: ...

    @overload
    def __getitem__(self, key: str) -> Any: ...

    def browse(self, ids: Any = ()) -> Self: ...

    def create(self, vals_list: Any) -> Self: ...

    def filtered(self, func: str | Callable[..., Any] | Domain) -> Self: ...

    def invalidate_model(
        self, fnames: Collection[str] | None = None, flush: bool = True
    ) -> None: ...

    def invalidate_recordset(
        self, fnames: Collection[str] | None = None, flush: bool = True
    ) -> None: ...

    def mapped(self, func: str) -> list[Any]: ...

    def search(
        self,
        domain: Any,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> Self: ...

    def search_count(self, domain: Any, limit: int | None = None) -> int: ...

    def search_fetch(
        self,
        domain: Any,
        field_names: Sequence[str] | None = None,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> Self: ...

    def search_read(
        self,
        domain: Any = None,
        fields: Sequence[str] | None = None,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        **read_kwargs: Any,
    ) -> list[Any]: ...

    def sudo(self, flag: bool = True) -> Self: ...

    def unlink(self) -> bool: ...

    def with_company(self, company: Any) -> Self: ...

    def with_context(self, ctx: Any = None, /, **overrides: Any) -> Self: ...

    def with_env(self, env: Any) -> Self: ...

    def with_user(self, user: Any) -> Self: ...

    def write(self, vals: Any) -> Any: ...


class DecimalPrecisionProtocol(RecordsetProtocol, Protocol):
    def get_precision(self, application: str) -> int: ...


type XmlidRow = tuple[int, str, str, str, int, bool, int | None]


class IrModelDataProtocol(RecordsetProtocol, Protocol):
    def _get_xmlids(self, xml_ids: list[str], model: Any) -> list[XmlidRow]: ...

    def _load_xmlid(self, xml_id: str) -> Any: ...

    def _process_end(self, modules: list[str]) -> None: ...

    def _update_xmlids(
        self, data_list: list[dict[str, Any]], update: bool = False
    ) -> None: ...

    def _xmlid_to_res_model_res_id(
        self, xmlid: str, raise_if_not_found: bool = False
    ) -> tuple[Any, Any]: ...


class IrModelProtocol(RecordsetProtocol, Protocol):
    name: str | Literal[False]

    def _get(self, name: str) -> Self: ...

    def _get_manual_model_data(self) -> list[dict[str, Any]]: ...

    def _prepare_class_attrs(self, model_data: dict[str, Any]) -> dict[str, Any]: ...

    def _prepare_model_vals(self, model: Any) -> dict[str, Any]: ...

    def _reflect_models(self, model_names: list[str]) -> None: ...


class IrModelFieldsProtocol(RecordsetProtocol, Protocol):
    name: str
    model: str
    compute: str | Literal[False]

    def _get(self, model_name: str, name: str) -> Any: ...

    def _get_ids_by_name(self, model_name: str) -> dict[str, int]: ...

    def _get_reflected_stored_names(self, model_name: str) -> set[str]: ...

    def _get_manual_field_data(self, model_name: str) -> dict[str, Any]: ...

    def _is_field_ready(self, field_data: dict[str, Any]) -> bool: ...

    def _prepare_field_attrs(self, field_data: dict[str, Any]) -> dict[str, Any]: ...

    def _prepare_field_vals(self, field: Any, model_id: int) -> dict[str, Any]: ...

    def _reflect_fields(self, model_names: list[str]) -> None: ...

    def get_field_help(self, model_name: str) -> dict[str, str | None]: ...

    def get_field_selection(
        self, model_name: str, field_name: str
    ) -> list[tuple[str, str]]: ...

    def get_field_string(self, model_name: str) -> dict[str, str]: ...


class IrModelConstraintProtocol(RecordsetProtocol, Protocol):
    message: str | Literal[False]

    def _reflect_constraint(
        self,
        model: Any,
        conname: str,
        type: str,
        definition: str | None,
        module: str | None,
        message: str | None = None,
    ) -> Any: ...

    def _reflect_constraints(self, model_names: list[str]) -> None: ...


class IrAccessProtocol(RecordsetProtocol, Protocol):
    def _operation_letter(self, operation: str) -> str: ...

    def _get_all_access(self) -> Any: ...

    def _eval_context(self) -> dict[str, Any]: ...

    def _policy_signature(self) -> tuple[Any, ...]: ...

    def _policy_expiry(self) -> Any: ...

    def _load_legacy_access(self, module: str, mode: str) -> dict[str, bool]: ...

    def _get_access_context(self) -> Any: ...

    def _log_unresolved_domains(self) -> None: ...

    def _bound_access_rows(
        self, model_name: str, operation: str
    ) -> tuple[list[Domain], list[Domain]]: ...

    def _field_class_allowed(self, name: str, operation: str) -> bool | str: ...
    def _field_class_domain(
        self, name: str, operation: str, model_name: str
    ) -> Domain: ...
    def _label_classes(self) -> tuple[tuple[int, str], ...]: ...

    def _prepare_model_access_error(
        self, model_name: str, operation: str
    ) -> AccessError: ...

    def _prepare_record_access_error(
        self, records: Any, operation: str
    ) -> AccessError: ...


class IrDefaultProtocol(RecordsetProtocol, Protocol):
    field_id: IrModelFieldsProtocol
    json_value: str

    def discard_records(self, records: Any) -> bool: ...

    def _get_field_column_fallbacks(self, model_name: str, field_name: str) -> str: ...

    def _get_model_defaults(
        self, model_name: str, condition: str | bool = False
    ) -> dict[str, Any]: ...


class IrAttachmentProtocol(RecordsetProtocol, Protocol):
    datas: bytes | Literal[False]
    file_size: int
    raw: bytes | Literal[False]
    url: str | Literal[False]

    def _get_domain_generated_assets(
        self, url: str | None = None, url_pattern: str | None = None
    ) -> Domain: ...

    def _prepare_generated_asset_vals(
        self, *, name: str, mimetype: str, raw: bytes, url: str
    ) -> dict[str, Any]: ...

    def _gc_file_store_unsafe(
        self, checklist: dict[str, Any] | None = None, grace: float | None = None
    ) -> int: ...

    def _get_content_checksum(self, bin_data: bytes) -> str: ...

    def _get_filestore(self) -> str: ...

    def _with_bin_size_disabled(self) -> Any: ...


class IrUiViewProtocol(RecordsetProtocol, Protocol):
    arch_base: str | Literal[False]
    name: str

    def _render_template(
        self, template: int | str, values: dict[str, Any] | None = None
    ) -> Any: ...

    def _get_custom_views(self, models: Any = None) -> Any: ...

    def _get_view_refs(self, node: Any) -> dict[str, str]: ...

    def _check_module_views(self, module: str) -> None: ...

    def _check_loaded_qweb_templates(self) -> None: ...

    def _get_undeclared_view_ids(self, module: str) -> set[int]: ...


class IrConfigParameterProtocol(RecordsetProtocol, Protocol):
    def init(self, force: bool = False) -> None: ...

    def get_param(self, key: str, default: str | bool = False) -> str | bool: ...

    def get_param_bool(self, key: str, default: bool = False) -> bool: ...

    def get_param_float(self, key: str, default: float) -> float: ...

    def get_param_int(self, key: str, default: int) -> int: ...

    def set_param(self, key: str, value: Any) -> str | bool: ...


class IrHttpProtocol(RecordsetProtocol, Protocol):
    def _get_webclient_translation_modules(self) -> list[list[str]]: ...

    def _get_web_translations_hash(
        self, modules: list[str], lang: str | None
    ) -> str: ...


class IrQWebProtocol(RecordsetProtocol, Protocol):
    def _pregenerate_assets_bundles(self) -> list[str]: ...

    def _warm_page_assets(self) -> None: ...


class IrCronProtocol(RecordsetProtocol, Protocol):
    def _trigger(self, at: Any = None, *, coalesce: int = 0) -> Any: ...


class IrModelFieldsSelectionProtocol(RecordsetProtocol, Protocol):
    def _reflect_selections(self, model_names: list[str]) -> None: ...


class IrModelRelationProtocol(RecordsetProtocol, Protocol):
    def _reflect_relations(self, items: Any, *, model_tables: Any = ()) -> None: ...


class IrModelInheritProtocol(RecordsetProtocol, Protocol):
    def _reflect_inherits(self, model_names: list[str]) -> None: ...


class IrModuleModuleProtocol(RecordsetProtocol, Protocol):
    dependencies_id: Any
    name: str
    state: str

    def button_immediate_install(self) -> dict[str, Any]: ...

    def button_immediate_uninstall(self) -> dict[str, Any]: ...

    def button_install(self) -> dict[str, Any]: ...

    def button_upgrade(self) -> dict[str, Any] | None: ...

    def downstream_dependencies(
        self, known_deps: Self | None = None, exclude_states: tuple[str, ...] = ...
    ) -> Self: ...

    def module_uninstall(self) -> bool: ...

    def _check(self) -> None: ...

    def _extract_resource_attachment_translations(
        self, module: Any, lang: Any
    ) -> Any: ...

    def _get_domain_modules_to_load(self) -> DomainType: ...

    def _import_zipfile(
        self, module_file: Any, force: bool = False, with_demo: bool = False
    ) -> Any: ...

    def _update_translations(
        self, filter_lang: Any = None, overwrite: bool = False
    ) -> None: ...

    def get_values_from_terp(self, terp: Any) -> dict[str, Any]: ...

    def update_list(self) -> Any: ...


class IrFieldsConverterProtocol(RecordsetProtocol, Protocol):
    def _import_session(
        self, flush: Callable[..., bool]
    ) -> AbstractContextManager[Any]: ...

    def _get_converter_record(self, model: Any) -> Any: ...

    def _prefetch_name_references(self, model: Any, records: Any) -> None: ...


class ResCompanyProtocol(RecordsetProtocol, Protocol):
    root_id: Any
    currency_id: Any
    partner_id: Any

    def __int__(self) -> int: ...

    def _get_ancestor_ids(self, include_self: bool = False) -> OrderedSet[int]: ...

    def _seed_configurations(self, module: str) -> None: ...


class ResCountryProtocol(RecordsetProtocol, Protocol):
    code: Any
    currency_id: Any


class ResCurrencyProtocol(RecordsetProtocol, Protocol):
    def round(self, amount: float) -> float: ...


class ResLangProtocol(RecordsetProtocol, Protocol):
    def _get_data(self, **kwargs: Any) -> Any: ...

    def _get_lang_cached(self, code: str) -> Any: ...

    def get_installed(self) -> list[tuple[str, str]]: ...


class ResUsersApikeysScopeProtocol(RecordsetProtocol, Protocol):
    def _rules(self) -> Any: ...


class ResGroupsProtocol(RecordsetProtocol, Protocol):
    def _privilege_ids(self, names: tuple[str, ...]) -> frozenset[int]: ...

    def union(self, *args: Any) -> Any: ...


class IrAccessLogProtocol(RecordsetProtocol, Protocol):
    def _record_privileged(
        self, model_name: str, operation: str, ids: tuple[IdType, ...]
    ) -> None: ...


class IrAccessObligationProtocol(RecordsetProtocol, Protocol):
    def _at_door(self, records: Any, verb: str, call: Any) -> Any: ...
    def _at_checkpoint(self, records: Any, verb: str) -> None: ...
    def _after_move(self, records: Any, verb: str) -> None: ...


class AuthUserClientProtocol(RecordsetProtocol, Protocol):
    def _bind_session(self, session: Any, req: Any = None) -> tuple[Any, bool]: ...

    def _is_session_valid(self, session: Any, fresh_primary_cr: Any = None) -> bool: ...

    def _observe(self, request: Any) -> None: ...


class ResUsersProtocol(RecordsetProtocol, Protocol):
    company_id: ResCompanyProtocol
    company_ids: ResCompanyProtocol
    login: str | Literal[False]
    lang: Any
    tz: Any

    def _check_uid_passwd(self, uid: int, passwd: str) -> int | None: ...

    def _get_session_token(self, sid: str) -> str | None: ...

    def _get_company_ids(self) -> tuple[int, ...]: ...

    def _get_group_ids(self) -> tuple[int, ...]: ...

    def _has_group(self, group_ext_id: str) -> bool: ...

    def _is_admin(self) -> bool: ...

    def _is_public(self) -> bool: ...

    def _is_system(self) -> bool: ...

    def authenticate(
        self, credential: dict[str, Any], user_agent_env: dict[str, Any]
    ) -> dict[str, Any]: ...

    def context_get(self) -> Any: ...

    def has_group(self, group_ext_id: str) -> bool: ...

    def has_groups(self, group_spec: str) -> bool: ...


FRAMEWORK_MODEL_PROTOCOLS: dict[str, type] = {
    "auth.user.client": AuthUserClientProtocol,
    "decimal.precision": DecimalPrecisionProtocol,
    "ir.attachment": IrAttachmentProtocol,
    "ir.config_parameter": IrConfigParameterProtocol,
    "ir.cron": IrCronProtocol,
    "ir.http": IrHttpProtocol,
    "ir.default": IrDefaultProtocol,
    "ir.access": IrAccessProtocol,
    "ir.fields.converter": IrFieldsConverterProtocol,
    "ir.model": IrModelProtocol,
    "ir.model.constraint": IrModelConstraintProtocol,
    "ir.model.data": IrModelDataProtocol,
    "ir.model.fields": IrModelFieldsProtocol,
    "ir.model.fields.selection": IrModelFieldsSelectionProtocol,
    "ir.model.inherit": IrModelInheritProtocol,
    "ir.model.relation": IrModelRelationProtocol,
    "ir.module.module": IrModuleModuleProtocol,
    "ir.qweb": IrQWebProtocol,
    "ir.ui.view": IrUiViewProtocol,
    "res.company": ResCompanyProtocol,
    "res.country": ResCountryProtocol,
    "res.currency": ResCurrencyProtocol,
    "res.lang": ResLangProtocol,
    "res.users": ResUsersProtocol,
    "res.users.apikeys.scope": ResUsersApikeysScopeProtocol,
    "res.groups": ResGroupsProtocol,
    "ir.access.log": IrAccessLogProtocol,
    "ir.access.obligation": IrAccessObligationProtocol,
}
