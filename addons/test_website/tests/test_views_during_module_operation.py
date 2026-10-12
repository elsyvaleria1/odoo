from odoo.tests import standalone

from odoo.addons.http_routing.tests.common import MockRequest


@standalone("cow_views", "website_standalone")
def test_01_cow_views_unlink_on_module_update(env):

    View = env["ir.ui.view"]
    Imd = env["ir.model.data"]

    update_module_base_view = env.ref("test_website.update_module_base_view")
    update_module_view_to_be_t_called = View.create(
        {
            "name": "View to be t-called",
            "type": "qweb",
            "arch": "<div>I will be t-called</div>",
            "key": "test_website.update_module_view_to_be_t_called",
        }
    )
    update_module_child_view = View.create(
        {
            "name": "Child View",
            "mode": "extension",
            "inherit_id": update_module_base_view.id,
            "arch": """
            <div position="inside">
                <t t-call="test_website.update_module_view_to_be_t_called"/>
            </div>
        """,
            "key": "test_website.update_module_child_view",
        }
    )

    Imd.create(
        {
            "module": "test_website",
            "name": "update_module_view_to_be_t_called",
            "model": "ir.ui.view",
            "res_id": update_module_view_to_be_t_called.id,
        }
    )
    Imd.create(
        {
            "module": "test_website",
            "name": "update_module_child_view",
            "model": "ir.ui.view",
            "res_id": update_module_child_view.id,
        }
    )

    update_module_child_view.with_context(website_id=1).write(
        {"name": "Child View (W1)"}
    )

    msg = "View '%s' does not exist!"
    assert (
        View.search_count(
            [("type", "=", "qweb"), ("key", "=", update_module_child_view.key)]
        )
        == 2
    ), msg % update_module_child_view.key
    assert bool(env.ref(update_module_view_to_be_t_called.key)), (
        msg % update_module_view_to_be_t_called.key
    )
    assert bool(env.ref(update_module_base_view.key)), msg % update_module_base_view.key

    test_website_module = env["ir.module.module"].search(
        [("name", "=", "test_website")]
    )
    test_website_module.button_immediate_upgrade()
    env.transaction.reset()

    view = env.ref(
        "test_website.update_module_view_to_be_t_called", raise_if_not_found=False
    )
    assert not view, "Generic view did not get removed!"

    assert not env["ir.ui.view"].search_count(
        [
            ("type", "=", "qweb"),
            ("key", "=", "test_website.update_module_child_view"),
        ]
    ), "Specific COW views did not get removed!"


@standalone("theme_views", "website_standalone")
def test_02_copy_ids_views_unlink_on_module_update(env):
    View = env["ir.ui.view"]
    ThemeView = env["theme.ir.ui.view"]
    Imd = env["ir.model.data"]

    website_1 = env["website"].browse(1)
    website_2 = env["website"].browse(2)
    theme_default = env.ref("base.module_theme_default")

    (website_1 + website_2).theme_id = theme_default
    env["ir.module.module"].with_context(load_all_views=True)._theme_load(website_1)
    env["ir.module.module"].with_context(load_all_views=True)._theme_load(website_2)

    key = "theme_default.theme_child_view"
    domain = [
        ("type", "=", "qweb"),
        ("key", "=", key),
    ]

    def _simulate_xml_view():
        base_view = env.ref("test_website.update_module_base_view")
        theme_child_view = ThemeView.create(
            {
                "name": "Theme Child View",
                "mode": "extension",
                "inherit_id": f"{base_view._name},{base_view.id}",
                "arch": """
                <div position="inside">
                    <p>, and I am inherited by a theme.ir.ui.view</p>
                </div>
            """,
                "key": key,
            }
        )
        Imd.create(
            {
                "module": "theme_default",
                "name": "theme_child_view",
                "model": "theme.ir.ui.view",
                "res_id": theme_child_view.id,
            }
        )
        View.create(
            [
                theme_child_view._convert_to_base_model(website_1),
                theme_child_view._convert_to_base_model(website_2),
            ]
        )

        view_website_1, view_website_2 = View.search(
            domain
            + [
                ("theme_template_id", "=", theme_child_view.id),
                ("website_id", "in", (website_1 + website_2).ids),
            ]
        )
        assert (
            set(view_website_1 + view_website_2).issubset(theme_child_view.copy_ids)
            and view_website_1.website_id == website_1
            and view_website_2.website_id == website_2
        ), "Theme View should have been copied to the website."

        return view_website_1, view_website_2, theme_child_view

    view_website_1, view_website_2, theme_child_view = _simulate_xml_view()

    old_registry = env.registry

    theme_default.button_immediate_upgrade()
    env.transaction.reset()

    assert env.registry is not old_registry
    View = env["ir.ui.view"]
    ThemeView = env["theme.ir.ui.view"]
    Imd = env["ir.model.data"]

    website_1 = env["website"].browse(1)
    website_2 = env["website"].browse(2)
    theme_default = env.ref("base.module_theme_default")

    view = env.ref("theme_default.theme_child_view", False)
    assert not view, "Theme view should have been removed during module update."
    assert not theme_child_view.exists(), (
        "Theme view should have been removed during module update. (2)"
    )

    assert not View.search(domain), "copy_ids views did not get removed!"
    assert not (view_website_1.exists() or view_website_2.exists()), (
        "copy_ids views did not get removed! (2)"
    )

    view_website_1, view_website_2, theme_child_view = _simulate_xml_view()

    with MockRequest(env, website=website_1):
        theme_default.button_immediate_upgrade()
    env.transaction.reset()

    view = env.ref("theme_default.theme_child_view", False)
    assert not view, "Theme view should have been removed during module update."
    assert not theme_child_view.exists(), (
        "Theme view should have been removed during module update. (2)"
    )

    assert not view_website_1.exists() and view_website_2.exists(), (
        "Only website_1 copy should be removed (2)"
    )
