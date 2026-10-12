from __future__ import annotations

import atexit
import typing

from odoo.libs.debug_log import DebugLog
from odoo.orm.model_test_env import (
    load_module_data,
    model_test_env,
    module_model_classes,
)

from .transaction_case import TransactionCase

_debug = DebugLog(__name__)

LOADER_OWNED_DATA = ("data/ir_module_module.xml",)

_HOSTS: dict[tuple[str, ...], typing.Any] = {}


def _close_hosts() -> None:
    while _HOSTS:
        modules, context = _HOSTS.popitem()
        _ENVS.pop(modules, None)
        context.__exit__(None, None, None)


atexit.register(_close_hosts)


_ENVS: dict[tuple[str, ...], typing.Any] = {}


def _restricting_group_ids(views: typing.Any) -> frozenset[int]:
    restricted = (
        views.sudo()
        .with_context(active_test=False)
        .search([("type", "!=", "qweb"), ("group_ids", "!=", False)])
    )
    return frozenset(restricted.group_ids.ids)


_MEMORY_ANSWERS = (
    ("ir.ui.view", "_get_restricting_group_ids", _restricting_group_ids),
)


def _host_environment(modules: tuple[str, ...]) -> typing.Any:
    env = _ENVS.get(modules)
    if env is None:
        classes: list[typing.Any] = []
        for module in modules:
            classes.extend(module_model_classes(module))
        context = model_test_env(*classes, check_cache=False)
        env = context.__enter__()
        for module in modules:
            load_module_data(env, module, skip=InMemoryCase.skip_data_files)
        for model, method, answer in _MEMORY_ANSWERS:
            if model in env.registry:
                setattr(env.registry[model], method, answer)
        env.flush_all()
        env.invalidate_all()
        _HOSTS[modules] = context
        _ENVS[modules] = env
        _debug.lifecycle(
            "test.in_memory.host_built",
            modules=len(modules),
            models=len(env.registry.models),
        )
    return env


class InMemoryCase(TransactionCase):
    allow_inherited_tests_method = True
    registry_test_mode = False

    hosts_modules: typing.ClassVar[tuple[str, ...]] = ("base",)
    skip_data_files: typing.ClassVar[tuple[str, ...]] = LOADER_OWNED_DATA

    @classmethod
    @typing.override
    def _open_class_transaction(cls) -> None:
        cls.env = typing.cast("typing.Any", _host_environment(cls.hosts_modules))
        cls.cr = typing.cast("typing.Any", cls.env.cr)
        cls.registry = typing.cast("typing.Any", cls.env.registry)
        cls.env.transaction.default_env = cls.env
        cls.env.flush_all()
        savepoint = cls.cr.savepoint(flush=False)
        cls.addClassCleanup(savepoint.close)
        cls.addClassCleanup(cls.env.transaction.clear)
        cls.addClassCleanup(cls.registry.clear_all_caches)
        _debug.lifecycle(
            "test.in_memory.class_hosted",
            cls=cls.__qualname__,
            modules=len(cls.hosts_modules),
            models=len(cls.registry.models),
        )
