import typing
from collections.abc import Callable, Iterable
from collections.abc import Set as AbstractSet

from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog

from ...primitives import Command

if typing.TYPE_CHECKING:
    from ...primitives import IdType, ValuesType

_debug = DebugLog(__name__)


def is_id_list(value: typing.Any) -> bool:
    return bool(value) and not any(
        isinstance(item, (tuple, list, dict)) for item in value
    )


def as_commands(value: list[typing.Any]) -> list[typing.Any]:
    if is_id_list(value):
        return [Command.set(tuple(value))]
    return [
        Command.create(item)
        if isinstance(item, dict)
        else item
        if isinstance(item, (tuple, list))
        else Command.link(item)
        for item in value
    ]


class CommandDelta:
    __slots__ = (
        "created",
        "deleted",
        "linked",
        "linked_by_update",
        "replaced",
        "set_ids",
        "superseding",
        "unlinked",
        "unlinked_since_replace",
        "updated",
    )

    def __init__(self) -> None:
        self.created: list[tuple[typing.Any, ValuesType]] = []
        self.updated: list[tuple[IdType, ValuesType]] = []
        self.deleted: OrderedSet[IdType] = OrderedSet()
        self.linked: OrderedSet[IdType] = OrderedSet()
        self.linked_by_update: OrderedSet[IdType] = OrderedSet()
        self.unlinked: OrderedSet[IdType] = OrderedSet()
        self.unlinked_since_replace: OrderedSet[IdType] = OrderedSet()
        self.replaced: bool = False
        self.set_ids: tuple[IdType, ...] = ()
        self.superseding: bool = True

    @classmethod
    def fold(
        cls,
        commands: Iterable[typing.Any] | None,
        normalize: Callable[[typing.Any], IdType] = lambda id_: id_,
        *,
        superseding: bool = True,
    ) -> typing.Self:
        delta = cls()
        delta.superseding = superseding
        commands = list(commands or ())
        if is_id_list(commands):
            delta._replace(tuple(normalize(id_) for id_ in commands))
            return delta
        for command in commands:
            if isinstance(command, dict):
                delta.created.append((None, command))
                continue
            if not isinstance(command, (tuple, list)):
                delta._link(normalize(command))
                continue
            if not command:
                continue
            match command[0]:
                case Command.CREATE:
                    delta.created.append((command[1], command[2]))
                case Command.UPDATE:
                    id_ = normalize(command[1])
                    delta.updated.append((id_, command[2]))
                    delta.linked_by_update.add(id_)
                case Command.DELETE:
                    id_ = normalize(command[1])
                    delta.deleted.add(id_)
                    delta.linked.discard(id_)
                    delta.linked_by_update.discard(id_)
                case Command.UNLINK:
                    id_ = normalize(command[1])
                    delta.unlinked.add(id_)
                    delta.unlinked_since_replace.add(id_)
                    delta.linked.discard(id_)
                    delta.linked_by_update.discard(id_)
                case Command.LINK:
                    delta._link(normalize(command[1]))
                case Command.CLEAR:
                    delta._replace(())
                case Command.SET:
                    ids = command[2]
                    if ids.__class__ is int:
                        ids = (ids,)
                    delta._replace(tuple(normalize(id_) for id_ in ids or ()))
                case _:
                    raise ValueError(f"Unknown x2many command {command!r}")
        return delta

    def _link(self, id_: IdType) -> None:
        self.linked.add(id_)
        self.unlinked.discard(id_)
        self.unlinked_since_replace.discard(id_)
        self.deleted.discard(id_)

    def _replace(self, ids: tuple[IdType, ...]) -> None:
        self.replaced = True
        self.set_ids = ids
        self.unlinked_since_replace.clear()
        if self.superseding:
            if _debug.logic.enabled and (self.created or self.linked or self.unlinked):
                _debug.logic(
                    "field.x2many.commands_superseded",
                    set_ids=len(ids),
                    created=len(self.created),
                    linked=len(self.linked),
                    unlinked=len(self.unlinked),
                )
            self.created.clear()
            self.linked.clear()
            self.linked_by_update.clear()
            self.unlinked.clear()

    @property
    def removed(self) -> AbstractSet[IdType]:
        return self.unlinked | self.deleted

    @property
    def removed_from_set(self) -> AbstractSet[IdType]:
        return self.unlinked_since_replace | self.deleted

    def get_final_ids(
        self, current: Iterable[IdType], created_ids: Iterable[IdType] = ()
    ) -> OrderedSet[IdType]:
        ids = OrderedSet(self.set_ids if self.replaced else current)
        ids -= self.removed
        ids.update(self.linked)
        ids.update(created_ids)
        return ids
