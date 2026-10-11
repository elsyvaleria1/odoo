from typing import SupportsIndex, assert_type

from odoo.db import Cursor
from odoo.libs._vendor.embedded_sass_pb2 import COMPRESSED, InboundMessage, OutputStyle
from odoo.orm.models import BaseModel
from odoo.orm.runtime.environment import Environment
from odoo.orm.runtime.registry import Registry
from odoo.tests.form import M2MProxy
from odoo.tests.transaction_case import BaseCase, TransactionCase
from odoo.tools.config import _CountingDict
from odoo.tools.safe_eval import _guard_format_tree


def test_state_contracts(case: BaseCase, active: TransactionCase) -> None:
    assert_type(case.env, Environment | None)
    assert_type(case.registry, Registry | None)
    assert_type(case.cr, Cursor | None)
    assert_type(case._get_env(), Environment)
    assert_type(case._get_registry(), Registry)
    assert_type(case._get_cr(), Cursor)
    assert_type(active.env, Environment)
    assert_type(active.registry, Registry)
    assert_type(active.cr, Cursor)
    with case.assertRaises(ValueError) as caught:
        assert_type(caught.exception, ValueError)
    assert_type(case.assertRaises(ValueError, int, "bad"), None)
    assert_type(case.assertRaises(ValueError, func=int, x="bad"), None)
    case.assertRaises("ValueError")  # type: ignore[call-overload]  # Exceptions must be classes.
    case.assertRaises(ValueError, func="int")  # type: ignore[call-overload]  # The callable form requires a function.


def proxy_contracts(proxy: M2MProxy, record: BaseModel, index: SupportsIndex) -> None:
    assert_type(proxy[0], BaseModel)
    assert_type(proxy[index], BaseModel)
    assert_type(proxy[:], BaseModel)
    assert_type(proxy.index(record), int)
    assert_type(proxy.count(object()), int)
    proxy["id"]  # type: ignore[index]  # Sequence indices are integers or slices.


def configuration_contracts(options: _CountingDict) -> None:
    options |= {"workers": 4}
    assert_type(options, _CountingDict)
    options |= {1: "workers"}  # type: ignore[dict-item]  # Configuration keys are strings.


def generated_message_contracts(message: InboundMessage) -> None:
    assert_type(message.compile_request, InboundMessage.CompileRequest)
    assert_type(message.compile_request.string.source, str)
    assert_type(message.compile_request.id, int)
    assert_type(message.compile_request.style, OutputStyle)
    assert_type(COMPRESSED, OutputStyle)
    message.compile_request.id = "id"  # type: ignore[assignment]  # Protobuf scalar fields retain their types.


def ast_root_contracts() -> None:
    import ast

    assert_type(_guard_format_tree(ast.parse("1", mode="eval")), ast.Expression)
    assert_type(_guard_format_tree(ast.parse("pass", mode="exec")), ast.Module)
