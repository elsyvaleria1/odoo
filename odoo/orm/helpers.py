import typing
from operator import itemgetter

from odoo.libs.debug_log import DebugLog

from ._recordset import is_recordset
from .domain import Domain

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from ._protocols import ResCompanyProtocol
    from ._typing import ModelLike
    from .fields.base import Field
    from .models.base import BaseModel
    from .runtime.environment import Environment

_debug = DebugLog(__name__)


def invalid_field_message(model: ModelLike, fname: str) -> str:
    message = f"Invalid field {fname!r} on model {model._name!r}"
    renamed = getattr(model, "_legacy_field_names", None) or {}
    if fname in renamed:
        message += f"; it is named {renamed[fname]!r} here"
    return message


def get_fields_by_name(
    model: ModelLike, fnames: Iterable[str]
) -> list[Field[typing.Any]]:
    fields = []
    _fields = model._fields
    for fname in fnames:
        try:
            fields.append(_fields[fname])
        except KeyError:
            raise ValueError(invalid_field_message(model, fname)) from None
    return fields


def get_class_memos(cls: type) -> dict[str, typing.Any]:
    memos: dict[str, typing.Any] | None = cls.__dict__.get("_class_memos__")
    if memos is None:
        memos = {}
        setattr(cls, "_class_memos__", memos)  # noqa: B010 - attach storage to an arbitrary class
    return memos


def get_or_create_class_memo[T](
    cls: type, key: str, factory: typing.Callable[[], T]
) -> T:
    memos = get_class_memos(cls)
    try:
        memo: T = memos[key]
        return memo
    except KeyError:
        value = memos[key] = factory()
        return value


def get_tuple_itemgetter(
    items: Sequence[int],
) -> typing.Callable[[typing.Any], tuple[typing.Any, ...]]:
    if len(items) == 0:
        return lambda a: ()
    if len(items) == 1:
        return lambda gettable: (gettable[items[0]],)
    return itemgetter(*items)


def to_record_ids(arg: typing.Any) -> list[int]:
    if is_recordset(arg):
        return arg.ids
    elif isinstance(arg, bool):
        return []
    elif isinstance(arg, int):
        return [arg] if arg else []
    else:
        return [id_ for id_ in arg if id_]


def _companies(env: Environment) -> ResCompanyProtocol:
    return env["res.company"].sudo()


def get_all_company_ids(env: Environment) -> list[int]:
    companies = _companies(env).with_context(active_test=False)
    return companies.search([], order="id").ids


def _get_ancestor_company_ids(self: BaseModel, company_ids: list[int]) -> list[int]:
    companies = _companies(self.env).browse(company_ids)
    ancestor_ids = list(companies._get_ancestor_ids(include_self=True))
    _debug.logic(
        "helpers.company_ancestors",
        model=self._name,
        companies=len(company_ids),
        ancestors=len(ancestor_ids),
    )
    return ancestor_ids


def check_company_domain_parent_of(
    self: BaseModel,
    companies: BaseModel | list[int] | int | str,
) -> Domain:
    if isinstance(companies, str):
        _debug.logic(
            "helpers.check_company_domain",
            model=self._name,
            field="company_id",
            shape="unquoted_expression",
        )
        return Domain.OR(
            [
                Domain("company_id", "=", False),
                Domain("company_id", "parent_of", companies),
            ]
        )

    companies = to_record_ids(companies)
    if not companies:
        _debug.logic(
            "helpers.check_company_domain",
            model=self._name,
            field="company_id",
            shape="no_company",
        )
        return Domain("company_id", "=", False)

    return Domain(
        "company_id", "in", _get_ancestor_company_ids(self, companies) + [False]
    )


def check_companies_domain_parent_of(
    self: BaseModel,
    companies: BaseModel | list[int] | int | str,
) -> Domain:
    if isinstance(companies, str):
        return Domain("company_ids", "parent_of", companies)

    companies = to_record_ids(companies)
    if not companies:
        return Domain.TRUE

    return Domain("company_ids", "in", _get_ancestor_company_ids(self, companies))
