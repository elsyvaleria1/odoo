from odoo.tests import tagged

from odoo.addons.web.tests.bundle_services import BundleServicesCase, addon_sources

PUBLIC_BUNDLES = ("sign.assets_public_sign", "web.assets_frontend")

BACKEND_ONLY_REQUIREMENTS = {
    "/sign/static/src/dialogs/next_direct_sign_dialog.js": {"action"},
}


@tagged("-at_install", "post_install")
class TestPublicBundleServices(BundleServicesCase):
    def test_sign_components_require_only_services_the_public_bundle_starts(self):
        for bundle in PUBLIC_BUNDLES:
            with self.subTest(bundle=bundle):
                self.assertBundleStartsRequiredServices(
                    bundle, addon_sources("sign"), BACKEND_ONLY_REQUIREMENTS
                )
