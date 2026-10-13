from collections import Counter
from unittest.mock import patch

import odoo.tests
from odoo.exceptions import AccessError

from odoo.addons.base.models.ir_ui_view import IrUiView
from odoo.addons.http_routing.tests.common import MockRequest


class TestConfiguratorCommon(odoo.tests.HttpCase):
    def _theme_upgrade_upstream(self):
        pass

    def setUp(self):
        super().setUp()

        def iap_jsonrpc_mocked_configurator(*args, **kwargs):
            endpoint = args[0]
            params = kwargs.get("params", {})
            language = params.get("lang", "en_US")
            if endpoint.endswith("/api/website/1/configurator/industries"):
                if language in ("fr_FR", "pa_GB"):
                    return {
                        "industries": [
                            {"id": 1, "label": "abbey in fr"},
                            {
                                "id": 2,
                                "label": "aboriginal and torres strait islander organisation in fr",
                            },
                            {"id": 3, "label": "aboriginal art gallery in fr"},
                            {"id": 4, "label": "abortion clinic in fr"},
                            {"id": 5, "label": "abrasives supplier in fr"},
                            {"id": 6, "label": "abundant life church in fr"},
                        ]
                    }
                else:
                    return {
                        "industries": [
                            {"id": 1, "label": "abbey"},
                            {
                                "id": 2,
                                "label": "aboriginal and torres strait islander organisation",
                            },
                            {"id": 3, "label": "aboriginal art gallery"},
                            {"id": 4, "label": "abortion clinic"},
                            {"id": 5, "label": "abrasives supplier"},
                            {"id": 6, "label": "abundant life church"},
                        ]
                    }
            elif "api/olg/1/chat" in endpoint:
                return {
                    "status": "success",
                    "content": """
                    {
                    "categories": [
                        {
                        "name": "New Arrivals",
                        "description": "Fresh styles just dropped—grab them before they’re gone!"
                        },
                        {
                        "name": "Best Sellers",
                        "description": "Shop the crowd favorites everyone’s raving about."
                        },
                        {
                        "name": "Limited Editions",
                        "description": "Exclusive finds you won’t see again. Act fast!"
                        },
                        {
                        "name": "Eco-Friendly Picks",
                        "description": "Sustainable choices that look good and feel better."
                        },
                        {
                        "name": "Gifts & Bundles",
                        "description": "Perfectly curated sets for every occasion."
                        },
                        {
                        "name": "Under $50",
                        "description": "Amazing deals that won’t break the bank."
                        },
                        {
                        "name": "Seasonal Favorites",
                        "description": "Style your season with trending must-haves."
                        },
                        {
                        "name": "Final Sale",
                        "description": "Last chance to score these unbeatable deals!"
                        }
                    ]
                    }
                """,
                }
            elif "/api/website/2/configurator/recommended_themes" in endpoint:
                return []
            elif "/api/website/2/configurator/custom_resources/" in endpoint:
                return {"images": {}}
            elif "/api/olg/1/generate_placeholder" in endpoint:
                return {
                    "a non existing placeholder": "😠",
                    "Catchy Headline": "Welcome to XXXX - Your Super test",
                }
            return None

        iap_patch = patch(
            "odoo.tools.iap.jsonrpc",
            iap_jsonrpc_mocked_configurator,
        )
        self.startPatcher(iap_patch)

        patcher = patch(
            "odoo.addons.website.models.ir_module_module.IrModuleModule._theme_upgrade_upstream",
            wraps=self._theme_upgrade_upstream,
        )
        self.startPatcher(patcher)


@odoo.tests.common.tagged("post_install", "-at_install")
class TestConfigurator(TestConfiguratorCommon):
    def test_configurator_params_step(self):
        self.start_tour(
            "/website/configurator/3", "configurator_params_step", login="admin"
        )

    def test_configurator_page_creation(self):
        website = self.env["website"].create(
            {
                "name": "New website",
            }
        )
        self.start_tour(
            "/website/force/%s?path=%%2Fwebsite%%2Fconfigurator" % website.id,
            "configurator_page_creation",
            login="admin",
        )


@odoo.tests.common.tagged("post_install", "-at_install")
class TestConfiguratorApply(TestConfiguratorCommon):
    def test_apply_compiles_each_template_once(self):
        website = self.env["website"].create({"name": "Compiled once"})
        features = self.env["website.configurator.feature"].search(
            [("page_view_id", "!=", False)]
        )
        get_errors = IrUiView._get_qweb_compile_errors
        checked = Counter()

        def spy(views, **kwargs):
            checked.update(views.ids)
            return get_errors(views, **kwargs)

        with (
            patch.object(IrUiView, "_get_qweb_compile_errors", spy),
            MockRequest(self.env, website=website),
        ):
            website.configurator_apply(
                selected_features=features.ids,
                industry_id=1,
                industry_name="abbey",
                selected_palette="default-1",
                theme_name="theme_default",
                website_purpose="get_leads",
                website_type="business",
            )
        self.assertTrue(checked)
        self.assertEqual(
            {view: count for view, count in checked.items() if count > 1}, {}
        )


@odoo.tests.common.tagged("post_install", "-at_install")
class TestConfiguratorOffline(TestConfiguratorCommon):
    def _offline(self):
        def unreachable(*args, **kwargs):
            raise AccessError("The url that this service requested returned an error.")

        return patch("odoo.tools.iap.jsonrpc", unreachable)

    def test_an_unreachable_service_recommends_no_theme(self):
        website = self.env["website"].browse(1)
        with self._offline(), MockRequest(self.env, website=website):
            self.assertEqual(
                website.configurator_recommended_themes(1, "default-1"), []
            )
            website.configurator_missing_industry("lighthouse keeping")

    def test_an_unreachable_service_still_applies_the_configuration(self):
        website = self.env["website"].create({"name": "Offline configurator"})
        features = self.env["website.configurator.feature"].search(
            [("page_view_id", "!=", False)], limit=2
        )
        with self._offline(), MockRequest(self.env, website=website):
            website.configurator_apply(
                selected_features=features.ids,
                industry_id=1,
                industry_name="abbey",
                selected_palette="default-1",
                theme_name="theme_default",
                website_purpose="get_leads",
                website_type="business",
            )
        self.assertTrue(website.configurator_done)
        homepage = website.with_context(website_id=website.id).viewref(
            "website.homepage"
        )
        self.assertEqual(homepage.website_id, website)


@odoo.tests.common.tagged("post_install", "-at_install")
class TestConfiguratorTranslation(TestConfiguratorCommon):
    def test_01_configurator_translation(self):
        parseltongue = self.env["res.lang"].create(
            {
                "name": "Parseltongue",
                "code": "pa_GB",
                "iso_code": "pa_GB",
                "url_code": "pa_GB",
            }
        )
        self.env["wizard.res.lang.install"].create(
            {
                "overwrite": True,
                "lang_ids": [(6, 0, [parseltongue.id])],
            }
        ).action_install_lang()
        feature = self.env["website.configurator.feature"].search(
            [("name", "=", "Privacy Policy")]
        )
        feature.with_context(lang=parseltongue.code).write(
            {"name": "Parseltongue_privacy"}
        )
        self.env.ref("base.user_admin").write({"lang": parseltongue.code})
        website_fr = self.env["website"].create(
            {
                "name": "New website",
            }
        )
        active_todo = self.env["ir.actions.todo"].search(
            [("state", "=", "open")], limit=1
        )
        active_todo.update({"state": "done"})
        self.start_tour(
            "/website/force/%s?path=%%2Fwebsite%%2Fconfigurator" % website_fr.id,
            "configurator_translation",
            login="admin",
        )
