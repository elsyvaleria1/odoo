from odoo.modules.module import check_python_external_dependency, get_manifest
from odoo.tests import BaseCase, tagged


@tagged("post_install", "-at_install")
class TestManifest(BaseCase):
    def test_the_python_dependency_names_its_distribution(self):
        manifest = get_manifest("integration_websocket")
        for dependency in manifest["external_dependencies"]["python"]:
            with self.assertNoLogs("odoo.modules.module", "WARNING"):
                check_python_external_dependency(dependency)
