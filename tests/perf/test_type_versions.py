from __future__ import annotations

import pytest

_testcapi = pytest.importorskip(
    "_testcapi", reason="type version tags are read through CPython's _testcapi"
)


def _unversioned(registry) -> list[str]:
    names = []
    for name, model_cls in registry.models.items():
        model_cls._name
        if _testcapi.type_get_version(model_cls) == 0:
            names.append(name)
    return sorted(names)


def _run_flows(registry) -> None:
    import odoo

    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        cr.transaction.default_env = env
        user = env["res.users"].create(
            {
                "name": "type version reader",
                "login": "type_version_reader",
                "group_ids": [(6, 0, [env.ref("base.group_user").id])],
            }
        )
        partners = env["res.partner"].create([{"name": f"tv {i}"} for i in range(20)])
        for partner in partners:
            partner.ref = "tv"
        env.flush_all()
        partners.with_user(user).has_access("read")
        env["res.partner"].with_user(user).search_fetch([], ["name"], limit=10)
        cr.rollback()


@pytest.mark.parametrize("database", ["base_db", "sale_db"])
def test_no_model_class_runs_out_of_version_tags(database, request):
    from odoo.modules.registry import Registry

    registry = Registry(request.getfixturevalue(database))
    assert _unversioned(registry) == [], "after the registry load"
    _run_flows(registry)
    assert _unversioned(registry) == [], "after creating and writing partners"
