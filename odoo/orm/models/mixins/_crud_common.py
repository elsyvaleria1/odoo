import logging
import typing

from ...primitives import LOG_ACCESS_COLUMNS, SUPERUSER_ID, ValuesType

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ..._typing import BaseModel, ModelLike
    from ...fields import Field

type InverseHook = str | Callable[[BaseModel], None]


class CreateRecordData(typing.TypedDict):
    stored: ValuesType
    inversed: ValuesType
    cached_only: ValuesType
    inherited: dict[str, ValuesType]
    protected: set[Field[typing.Any]]
    recompute_after_create: Iterable[Field[typing.Any]]
    record: typing.NotRequired[ModelLike]


_BAD_NAMES = frozenset({"id", "parent_path"})
_BAD_NAMES_LOG = _BAD_NAMES | frozenset(LOG_ACCESS_COLUMNS)


def get_forbidden_field_names(model: typing.Any) -> frozenset[str]:
    if model._log_access and not (
        model.env.uid == SUPERUSER_ID and not model.pool.ready
    ):
        return _BAD_NAMES_LOG
    return _BAD_NAMES


_unlink = logging.getLogger("odoo.models.unlink")
_orm_crud = logging.getLogger("odoo.orm.crud")
