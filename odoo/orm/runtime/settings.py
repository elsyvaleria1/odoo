from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from .environment import Environment


class SystemSettings:
    """Read-only settings port for trusted server code.

    Returns scalar values, never an elevated recordset. The owning model keeps
    parameter caching and secret unsealing; writes still require its normal ACL.
    Do not expose arbitrary client-selected keys through an RPC method.
    """

    __slots__ = ()

    @typing.overload
    def get(self, env: Environment, key: str) -> str | None: ...

    @typing.overload
    def get[T](self, env: Environment, key: str, default: T) -> str | T: ...

    def get(self, env: Environment, key: str, default: typing.Any = None) -> typing.Any:
        return env["ir.config_parameter"].sudo().get_param(key, default)

    def get_int(self, env: Environment, key: str, default: int) -> int:
        return env["ir.config_parameter"].sudo().get_param_int(key, default)

    def get_float(self, env: Environment, key: str, default: float) -> float:
        return env["ir.config_parameter"].sudo().get_param_float(key, default)

    def get_bool(self, env: Environment, key: str, default: bool = False) -> bool:
        return env["ir.config_parameter"].sudo().get_param_bool(key, default)


SYSTEM_SETTINGS = SystemSettings()
