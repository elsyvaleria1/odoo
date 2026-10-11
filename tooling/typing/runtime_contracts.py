from collections.abc import Buffer, Hashable, Iterator, MutableSet
from collections.abc import Set as AbstractSet
from types import ModuleType
from typing import Any, assert_type

from odoo.libs.guarded_http import GuardedXmlRpcTransport
from odoo.libs.secret import Secret
from odoo.modules.loading import _ModuleLoader, _PackageLoader
from odoo.modules.migration import MigrationManager
from odoo.modules.module_graph import ModuleGraph
from odoo.orm._protocols import IrModuleModuleProtocol
from odoo.orm.fields.base import Field
from odoo.orm.fields.relational.one2many import One2many
from odoo.orm.models import BaseModel
from odoo.orm.runtime.environment import Environment
from odoo.orm.runtime.transaction import _EnvironmentSet


def model_name_contracts(model: BaseModel) -> None:
    assert_type(BaseModel._name, str | None)
    assert_type(model._name, str | None)
    assert_type(model._get_model_name(), str)


def field_contracts(field: Field[object], inverse: One2many) -> None:
    assert_type(field.comodel_name, str | None)
    assert_type(field._get_comodel_name(), str)
    assert_type(field._column_type, tuple[str, str] | None)
    assert_type(inverse.inverse_name, str | None)
    assert_type(inverse.comodel_name, str | None)
    assert_type(inverse._get_inverse_name(), str)
    field._column_type = None  # type: ignore[misc]  # Computed field types have no setter.


def loading_contracts(loader: _ModuleLoader, package: _PackageLoader) -> None:
    assert_type(loader.graph, ModuleGraph | None)
    assert_type(loader.env, Environment | None)
    assert_type(loader.migrations, MigrationManager | None)
    assert_type(loader._get_graph(), ModuleGraph)
    assert_type(loader._get_env(), Environment)
    assert_type(loader._get_migrations(), MigrationManager)
    assert_type(package.module, IrModuleModuleProtocol | None)
    assert_type(package.py_module, ModuleType | None)
    assert_type(package._get_module(), IrModuleModuleProtocol)
    assert_type(package._get_py_module(), ModuleType)


def environment_set_contracts(envs: _EnvironmentSet, env: Environment) -> None:
    values: MutableSet[Environment] = envs
    assert_type(iter(envs), Iterator[Environment])
    assert_type(envs.pop(), Environment)
    assert_type(
        envs.get_environment(envs.key(env.uid, env.su, env.context)), Environment | None
    )
    envs |= {env}
    envs &= {env}
    envs -= {env}
    envs ^= {env}
    assert_type(envs, _EnvironmentSet)
    values.add(env)
    envs.add("env")  # type: ignore[arg-type]  # The environment index needs real environments.
    envs.key(env.uid, env.su, {})  # type: ignore[arg-type]  # Index keys require an immutable context.
    assert_type(envs | {"extra"}, AbstractSet[Environment | str])


def http_contracts(transport: GuardedXmlRpcTransport, body: Buffer) -> None:
    assert_type(transport.request("example.test", "/RPC2", body), tuple[Any, ...])
    assert_type(transport.request(("example.test", {}), "/RPC2", body), tuple[Any, ...])
    transport.request(["example.test"], "/RPC2", body)  # type: ignore[arg-type]  # Hosts follow Transport's contract.
    transport.request("example.test", "/RPC2", "body")  # type: ignore[arg-type]  # XML-RPC writes binary bodies.


def require_hashable(value: Hashable) -> None:
    del value


def secret_contracts(secret: Secret) -> None:
    assert_type(secret.__hash__, None)
    require_hashable(secret)  # type: ignore[arg-type]  # Value equality disables hashing.
