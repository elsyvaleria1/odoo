import json
import logging
import os
import unittest
from datetime import date
from pathlib import Path

import psycopg

from odoo.db.schema import ensure_extension
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger

_logger = logging.getLogger(__name__)

_BASELINE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tooling"
    / "scripts"
    / "bundle_size_inputs_baseline.json"
)

_DIAGNOSTIC_TOP_N = 10

_UPDATE_ENV_VAR = "ODOO_BUNDLE_SIZE_UPDATE_BASELINE"


@tagged(
    "post_install",
    "-at_install",
    "web_perf",
    "web_assets",
    "web_bundle_size",
)
class TestWebBundleSize(TransactionCase):
    CALIBRATION_ROOTS = frozenset({"hr_attendance", "test_lint"})

    BUDGETS = {
        "web.assets_web": 5_012_000,
        "web.assets_frontend": 1_700_000,
        "web.assets_frontend_lazy": 1_699_000,
        "web.assets_emoji": 515_000,
        "web.assets_frontend_minimal": 11_500,
        "web.assets_web_dark": 5_012_000,
        "web.assets_web_print": 5_010_000,
        "web.report_assets_common": 11_100,
        "web.report_assets_pdf": 1_000_000,
    }

    @classmethod
    def _calibration_modules(cls):
        modules = {
            module.name: module for module in cls.env["ir.module.module"].search([])
        }
        countries = cls.env["res.company"].search([]).country_id
        closure = set()

        def add(name):
            pending = [name]
            while pending:
                current = pending.pop()
                if current not in closure:
                    closure.add(current)
                    pending.extend(modules[current].dependencies_id.mapped("name"))

        def grow():
            grown = True
            while grown:
                grown = False
                for name, module in modules.items():
                    if name in closure or not module.auto_install:
                        continue
                    triggers = module.dependencies_id.filtered("auto_install_required")
                    if (
                        triggers
                        and set(triggers.mapped("name")) <= closure
                        and module._is_auto_install_satisfiable()
                        and not (
                            module.country_ids and not module.country_ids & countries
                        )
                    ):
                        add(name)
                        grown = True

        for root in cls.CALIBRATION_ROOTS:
            add(root)
        grow()
        if "ai_auto_install" in closure and "ai" in modules and cls._pgvector_offered():
            add("ai")
            grow()
        return closure

    @classmethod
    def _pgvector_offered(cls):
        try:
            ensure_extension(cls.env.cr, "vector")
        except psycopg.Error:
            return False
        return True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        installed = set(
            cls.env["ir.module.module"]
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        expected = cls._calibration_modules()
        if installed != expected:
            extra = sorted(installed - expected)
            missing = sorted(expected - installed)
            raise unittest.SkipTest(
                "bundle budgets are calibrated for the install of "
                f"{sorted(cls.CALIBRATION_ROOTS)} on the narrow addons path "
                "(addons/web/tests/bundle_size.sh builds it); this database "
                f"differs (extra: {extra or 'none'}, missing: {missing or 'none'})"
            )

    @staticmethod
    def _parse_metafile_inputs(metafile_raw):
        if not metafile_raw:
            return {}
        try:
            metafile = json_loads(metafile_raw)
        except ValueError, TypeError:
            return {}
        inputs = {}
        for out_path, out_info in metafile.get("outputs", {}).items():
            if not out_path.endswith(".js"):
                continue
            for in_path, contrib in out_info.get("inputs", {}).items():
                inputs[in_path] = inputs.get(in_path, 0) + int(
                    contrib.get("bytesInOutput", 0),
                )
        return inputs

    def _measure_esm_bundle_bytes(self, bundle_name):
        bundle = self.env["ir.qweb"]._get_asset_bundle(
            bundle_name,
            css=False,
            js=True,
        )
        if not bundle.native_modules:
            self.skipTest(
                f"Bundle {bundle_name!r} has no native modules in "
                f"this installation; nothing to measure."
            )
        with mute_logger("odoo.addons.base.models.assetsbundle"):
            result = bundle.esbuild_native_bundle()
        return (
            len(result.code.encode("utf-8")),
            self._parse_metafile_inputs(result.metafile),
        )

    def _load_baseline(self):
        if not _BASELINE_PATH.exists():
            return {}
        try:
            return json_loads(_BASELINE_PATH.read_text(encoding="utf-8"))
        except ValueError, OSError:
            return {}

    def _save_baseline_entry(self, bundle_name, total_bytes, inputs_map):
        baseline = self._load_baseline()
        baseline["_generated_at"] = date.today().isoformat()
        baseline["_generator"] = f"test_web_bundle_size.py with {_UPDATE_ENV_VAR}=1"
        bundles = baseline.setdefault("bundles", {})
        bundles[bundle_name] = {
            "_total_bytes": total_bytes,
            "inputs": dict(sorted(inputs_map.items())),
        }
        baseline["bundles"] = dict(sorted(bundles.items()))
        _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BASELINE_PATH.write_text(
            json.dumps(baseline, indent=2) + "\n",
            encoding="utf-8",
        )

    def _build_diagnostic(self, bundle_name, inputs_map):
        if not inputs_map:
            return "  (esbuild metafile unavailable — no per-input breakdown)"

        baseline = self._load_baseline()
        bundle_baseline = (
            baseline.get("bundles", {}).get(bundle_name, {}).get("inputs", {})
        )

        if bundle_baseline:
            deltas = []
            for path, cur in inputs_map.items():
                base = bundle_baseline.get(path, 0)
                if cur > base:
                    deltas.append((path, base, cur, cur - base))
            deltas.sort(key=lambda t: -t[3])
            if not deltas:
                new_inputs = [
                    (p, b) for p, b in inputs_map.items() if p not in bundle_baseline
                ]
                new_inputs.sort(key=lambda kv: -kv[1])
                if not new_inputs:
                    return (
                        "  (no per-input growth detected against baseline — "
                        "regression may be in entry-glue overhead, not file content)"
                    )
                lines = [
                    (
                        "  No grown inputs vs baseline — "
                        "regression appears to be NEW inputs:"
                    ),
                    *(
                        f"    {bytes_:>10,} b   {path} (new)"
                        for path, bytes_ in new_inputs[:_DIAGNOSTIC_TOP_N]
                    ),
                ]
                return "\n".join(lines)
            lines = [
                "  Top contributors to growth (vs baseline):",
                *(
                    f"    +{delta:>9,} b   {path}  ({base:,} → {cur:,})"
                    for path, base, cur, delta in deltas[:_DIAGNOSTIC_TOP_N]
                ),
            ]
            return "\n".join(lines)

        top = sorted(inputs_map.items(), key=lambda kv: -kv[1])[:_DIAGNOSTIC_TOP_N]
        lines = [
            "  Top contributors to bundle (no baseline available):",
            *(f"    {bytes_:>10,} b   {path}" for path, bytes_ in top),
            f"  Run with {_UPDATE_ENV_VAR}=1 to populate the baseline",
            "  so future failures show deltas instead of absolute sizes.",
        ]
        return "\n".join(lines)

    def _assert_bundle_under_budget(self, bundle_name):
        budget = self.BUDGETS.get(bundle_name)
        if budget is None:
            self.fail(
                f"No budget defined for {bundle_name!r}. Add an entry "
                f"to TestWebBundleSize.BUDGETS — see the module "
                f"docstring for the calibration workflow."
            )
        actual, inputs_map = self._measure_esm_bundle_bytes(bundle_name)

        foreign_inputs = sorted(
            {
                path
                for path in inputs_map
                if os.path.normpath(path).startswith(os.pardir + os.sep)
            }
        )
        if foreign_inputs:
            self.skipTest(
                f"{len(foreign_inputs)} input(s) come from outside this repo, so "
                f"the CI-scoped budget for {bundle_name!r} does not describe this "
                f"bundle (e.g. {foreign_inputs[0]}). Measure budgets with "
                f"--addons-path=odoo/addons,addons."
            )

        if os.environ.get(_UPDATE_ENV_VAR):
            self._save_baseline_entry(bundle_name, actual, inputs_map)
            _logger.info(
                "[BUNDLE_SIZE] baseline-update bundle=%s total=%d inputs=%d",
                bundle_name,
                actual,
                len(inputs_map),
            )
            return

        headroom = budget - actual
        headroom_pct = headroom * 100 / budget if budget else 0
        _logger.info(
            "[BUNDLE_SIZE] bundle=%s actual=%d budget=%d headroom=%d (%.1f%%)",
            bundle_name,
            actual,
            budget,
            headroom,
            headroom_pct,
        )

        if actual <= budget:
            return

        diagnostic = self._build_diagnostic(bundle_name, inputs_map)
        self.fail(
            f"Bundle {bundle_name!r} esbuild output is {actual:,} bytes, "
            f"exceeding budget of {budget:,} bytes "
            f"(+{actual - budget:,} = +{(actual - budget) * 100 / budget:.1f}%). "
            f"Either trim the regression that added bytes, or bump the "
            f"BUDGETS entry in this test with justification in the "
            f"commit message.\n"
            f"{diagnostic}"
        )

    def test_assets_web_under_budget(self):
        self._assert_bundle_under_budget("web.assets_web")

    def test_assets_frontend_under_budget(self):
        self._assert_bundle_under_budget("web.assets_frontend")

    def test_assets_frontend_lazy_under_budget(self):
        self._assert_bundle_under_budget("web.assets_frontend_lazy")

    def test_assets_emoji_under_budget(self):
        self._assert_bundle_under_budget("web.assets_emoji")

    def test_assets_frontend_minimal_under_budget(self):
        self._assert_bundle_under_budget("web.assets_frontend_minimal")

    def test_assets_web_dark_under_budget(self):
        self._assert_bundle_under_budget("web.assets_web_dark")

    def test_assets_web_print_under_budget(self):
        self._assert_bundle_under_budget("web.assets_web_print")

    def test_report_assets_common_under_budget(self):
        self._assert_bundle_under_budget("web.report_assets_common")

    def test_report_assets_pdf_under_budget(self):
        self._assert_bundle_under_budget("web.report_assets_pdf")


@tagged("web_unit", "web_assets", "web_bundle_size")
class TestParseMetafileInputs(TransactionCase):
    _parse = staticmethod(TestWebBundleSize._parse_metafile_inputs)

    def test_none_returns_empty(self):
        self.assertEqual(self._parse(None), {})

    def test_empty_string_returns_empty(self):
        self.assertEqual(self._parse(""), {})

    def test_malformed_json_returns_empty(self):
        self.assertEqual(self._parse("not-json"), {})
        self.assertEqual(self._parse("{partial"), {})

    def test_well_formed_metafile_extracts_inputs(self):
        meta = json_dumps(
            {
                "outputs": {
                    "/tmp/x.js": {
                        "inputs": {
                            "addons/web/static/src/a.js": {"bytesInOutput": 100},
                            "addons/web/static/src/b.js": {"bytesInOutput": 200},
                        },
                        "bytes": 5000,
                    },
                },
            }
        )
        self.assertEqual(
            self._parse(meta),
            {
                "addons/web/static/src/a.js": 100,
                "addons/web/static/src/b.js": 200,
            },
        )

    def test_sourcemap_output_is_skipped(self):
        meta = json_dumps(
            {
                "outputs": {
                    "/tmp/x.js": {
                        "inputs": {"a.js": {"bytesInOutput": 100}},
                    },
                    "/tmp/x.js.map": {
                        "inputs": {"a.js": {"bytesInOutput": 50}},
                    },
                },
            }
        )
        self.assertEqual(self._parse(meta), {"a.js": 100})

    def test_missing_outputs_key_returns_empty(self):
        self.assertEqual(self._parse(json_dumps({})), {})
        self.assertEqual(self._parse(json_dumps({"outputs": {}})), {})

    def test_missing_bytes_in_output_treated_as_zero(self):
        meta = json_dumps(
            {
                "outputs": {
                    "/tmp/x.js": {
                        "inputs": {
                            "a.js": {},
                            "b.js": {"bytesInOutput": 50},
                        },
                    },
                },
            }
        )
        self.assertEqual(self._parse(meta), {"a.js": 0, "b.js": 50})
