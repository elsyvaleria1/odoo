from __future__ import annotations

import pytest

from ._bench import StatementCounter, measure


@pytest.fixture(scope="module")
def env(document_db):
    import odoo
    from odoo.modules.registry import Registry

    registry = Registry(document_db)
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        cr.transaction.default_env = env
        yield env
        cr.rollback()


@pytest.fixture(scope="module")
def counter():
    with StatementCounter().on() as counter:
        yield counter


@pytest.fixture(scope="module")
def graph(env):
    from odoo.tests.common import new_test_user

    user = new_test_user(env, login="perf_documents", groups="base.group_user")
    other = new_test_user(env, login="perf_documents_other", groups="base.group_user")
    Document = env["document.document"]
    roots = Document.create(
        [
            {"name": f"root {index}", "type": "folder", "owner_id": other.id}
            for index in range(10)
        ]
    )
    folders = Document.create(
        [
            {
                "name": f"folder {index}",
                "type": "folder",
                "folder_id": roots[index % 10].id,
                "owner_id": other.id,
                "is_access_restricted": index < 5,
            }
            for index in range(100)
        ]
    )
    Document.create(
        [
            {
                "name": f"file {index}",
                "folder_id": folders[index % 100].id,
                "owner_id": other.id,
            }
            for index in range(2000)
        ]
    )
    env["document.access"].create(
        [
            {"document_id": folder.id, "partner_id": user.partner_id.id, "role": "view"}
            for folder in folders[:50]
        ]
    )
    env.flush_all()
    return user, folders


def test_document_list_under_folder_grants(env, graph, counter, check):
    user, _folders = graph
    Document = env["document.document"].with_user(user)

    def page():
        Document.search([], limit=80, order="name, id desc")
        env.invalidate_all()

    readings = measure(page, counter, repeat=10)
    check("document_list_50_folder_grants", readings)


def test_document_count_under_folder_grants(env, graph, counter, check):
    user, _folders = graph
    Document = env["document.document"].with_user(user)

    readings = measure(lambda: Document.search_count([]), counter, repeat=10)
    check("document_count_50_folder_grants", readings)


def test_document_folder_grant_write(env, graph, counter, check):
    _user, folders = graph
    partner = env["res.partner"].create({"name": "perf grantee"})
    roles = iter(["edit", "view"] * 100)

    def grant():
        folders[60].action_update_access_rights(
            partners={partner.id: (next(roles), False)}
        )
        env.flush_all()

    readings = measure(grant, counter, repeat=10)
    check("document_folder_grant_write", readings)


def test_document_folder_move(env, graph, counter, check):
    _user, folders = graph
    moved = folders[70]
    targets = iter([folders[71], folders[72]] * 100)

    def move():
        moved.folder_id = next(targets)
        env.flush_all()

    readings = measure(move, counter, repeat=10)
    check("document_folder_move", readings)
