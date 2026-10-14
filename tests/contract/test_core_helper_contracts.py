import types
from collections import deque
from unittest.mock import Mock

import pytest

from odoo import exceptions, release
from odoo.modules import module
from odoo.service import db
from odoo.service.db import rpc
from odoo.tools import config, safe_eval
from odoo.tools.config import configmanager


@pytest.mark.parametrize(
    "version", ["1.0", "1.2.3", "19.0", "19.0.1", "19.0.1.2", "19.0.1.2.3"]
)
def test_current_series_and_legacy_versions_are_supported(version):
    assert module.is_module_version_supported(version) is True


@pytest.mark.parametrize(
    "version", ["", "1", "1..0", "1.0.0.0.0.0", "18.0.1.2", "20.0.1.2", "one.two"]
)
def test_invalid_or_incompatible_versions_are_not_supported(version):
    assert module.is_module_version_supported(version) is False


@pytest.mark.parametrize(
    "part",
    [
        "+1",
        "-1",
        " 1",
        "1 ",
        "١",
        "１",
        "²",
        "",
        "1_0",
        pytest.param("1" * 5000, id="excessive_digits"),
    ],
)
def test_manifest_version_components_must_be_ascii_decimal_numbers(part):
    version = f"1.{part}"
    with pytest.raises(ValueError, match="Invalid version"):
        module.adapt_version(version)
    manifest = {"version": version, "installable": True}
    module._normalize_version("invalid_version_probe", manifest)
    assert manifest == {"version": version, "installable": False}
    assert module.is_module_version_supported(version) is False


def test_legacy_version_normalization_still_prefixes_the_current_series():
    assert module.adapt_version("01.002") == f"{release.major_version}.01.002"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("none", False),
        ("False", False),
        ("true", True),
        ("0", False),
        ("1", True),
        ("starttls", "starttls"),
        ("ssl", "ssl"),
    ],
)
def test_smtp_ssl_option_parses_to_its_boolean_or_mode(value, expected):
    assert config.parse("smtp_ssl", value) == expected


def test_smtp_ssl_parser_rejects_an_unknown_mode():
    parser = configmanager().parser
    with pytest.raises(SystemExit) as error:
        parser.parse_args(["--smtp-ssl=unknown_mode"])
    assert error.value.code == 2


@pytest.mark.parametrize("values", [None, {}, {"value": [1, 2, 3]}])
def test_safe_eval_context_validation_returns_no_payload(values):
    assert safe_eval.check_no_modules_in_values(values) is None


@pytest.mark.parametrize(
    "container",
    [
        list,
        tuple,
        set,
        frozenset,
        deque,
        lambda value: {"nested": value[0]},
        lambda value: {value[0]: "nested"},
        lambda value: types.MappingProxyType({"nested": value[0]}),
    ],
)
def test_safe_eval_rejects_modules_nested_in_context_containers(container):
    value = container([types.ModuleType("unsafe_context_module")])
    with pytest.raises(TypeError, match="unsafe_context_module"):
        safe_eval.check_no_modules_in_values({"value": value})
    with pytest.raises(TypeError, match="unsafe_context_module"):
        safe_eval.safe_eval("1", {"value": value})


def test_safe_eval_validates_cyclic_values_without_mutating_them():
    values = {"items": []}
    values["items"].append(values)
    assert safe_eval.check_no_modules_in_values(values) is None
    assert values["items"][0] is values
    values["items"].append(types.ModuleType("unsafe_context_module"))
    with pytest.raises(TypeError, match="unsafe_context_module"):
        safe_eval.check_no_modules_in_values(values)


def test_admin_password_validation_returns_none_without_changing_rpc_results(
    monkeypatch,
):
    password_check = Mock(return_value=True)
    monkeypatch.setattr(config, "is_valid_admin_password", password_check)
    assert db.check_admin_password("supplied_password") is None
    result = object()
    operation = Mock(return_value=result)
    monkeypatch.setitem(rpc._DISPATCH, "drop", operation)
    assert rpc.dispatch("drop", ["supplied_password", "owned_test_database"]) is result
    operation.assert_called_once_with("owned_test_database")


@pytest.mark.parametrize("password", ["", "wrong_password"])
def test_rejected_admin_password_prevents_database_operations(monkeypatch, password):
    password_check = Mock(return_value=False)
    monkeypatch.setattr(config, "is_valid_admin_password", password_check)
    operation = Mock()
    monkeypatch.setitem(rpc._DISPATCH, "drop", operation)
    with pytest.raises(exceptions.AccessDenied):
        rpc.dispatch("drop", [password, "owned_test_database"])
    operation.assert_not_called()
    if password:
        password_check.assert_called_once_with(password)
    else:
        password_check.assert_not_called()
