from __future__ import annotations

import typing
from collections import deque
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from odoo.models import BaseModel

_debug = DebugLog(__name__)


@dataclass(slots=True)
class InitModelsPhase:
    install: bool
    model_tables: frozenset[str] = frozenset()

    post_init_queue: deque[Callable[[], None]] = field(default_factory=deque)

    foreign_keys: dict[tuple[str, str], tuple[str, str, str, BaseModel, str | None]] = (
        field(default_factory=dict)
    )

    relation_reflections: OrderedSet[tuple[str, str, str | None]] = field(
        default_factory=OrderedSet
    )

    def post_init(self, func: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        self.post_init_queue.append(partial(func, *args, **kwargs))

    def drain_post_init(self) -> None:
        _debug.pipeline("registry.init_phase.drain", queued=len(self.post_init_queue))
        while self.post_init_queue:
            self.post_init_queue.popleft()()
