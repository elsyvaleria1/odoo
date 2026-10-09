import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.tests.common import BaseCase
from odoo.tools.assets.esbuild import EsbuildCompiler

import odoo.addons


class TestEsbuildAddonAliases(BaseCase):
    def _aliases(self, odoo_root, addon_paths):
        with (
            patch.object(odoo.addons, "__path__", [str(path) for path in addon_paths]),
            patch.object(EsbuildCompiler, "_esbuild_addon_scan_cache", None),
        ):
            aliases, _externals = EsbuildCompiler._get_esbuild_addon_flags(odoo_root)
        return aliases

    def test_a_bytecode_leftover_does_not_shadow_the_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            moved_from = root / "odoo" / "addons"
            moved_to = root / "l10n"
            (moved_from / "l10n_moved" / "__pycache__").mkdir(parents=True)
            (moved_from / "l10n_moved" / "static" / "src").mkdir(parents=True)
            real = moved_to / "l10n_moved"
            (real / "static" / "src").mkdir(parents=True)
            (real / "__manifest__.py").write_text("{}")

            aliases = self._aliases(root / "odoo", [moved_from, moved_to])

        self.assertIn("--alias:@l10n_moved=./../l10n/l10n_moved/static/src", aliases)
        self.assertEqual(
            len(
                [alias for alias in aliases if alias.startswith("--alias:@l10n_moved=")]
            ),
            1,
        )

    def test_an_unreadable_manifest_does_not_shadow_the_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "odoo" / "addons", root / "l10n"
            for path, manifest in ((first, "{oops"), (second, "{}")):
                module = path / "l10n_broken"
                (module / "static" / "src").mkdir(parents=True)
                (module / "__manifest__.py").write_text(manifest)

            aliases = self._aliases(root / "odoo", [first, second])

        self.assertEqual(
            [alias for alias in aliases if alias.startswith("--alias:@l10n_broken=")],
            ["--alias:@l10n_broken=./../l10n/l10n_broken/static/src"],
        )
