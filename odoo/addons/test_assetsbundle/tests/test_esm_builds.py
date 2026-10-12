import contextlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from psycopg.errors import SerializationFailure, UniqueViolation

from odoo import fields
from odoo.api import SUPERUSER_ID
from odoo.db import db_connect
from odoo.tests import tagged, transaction_case
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import mute_logger
from odoo.tools.assets import esm_index
from odoo.tools.assets.esbuild import EsbuildResult

from odoo.addons.base.models import ir_qweb_assets
from odoo.addons.base.models.assetsbundle import AssetsBundle


@tagged("post_install", "-at_install", "assets_bundle")
class TestEsmBuildLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Build = cls.env["ir.asset.build"].sudo()

    def _row(self, directory, name="b.esm.js"):
        IrAttachment = self.env["ir.attachment"].with_user(SUPERUSER_ID)
        return IrAttachment.create(
            IrAttachment._prepare_generated_asset_vals(
                name=name,
                mimetype="text/javascript",
                raw=b"export {};",
                url=f"{directory}{name}",
            )
        )

    def _publish(self, directory, variant="default", bundle="test.builds", **extra):
        return self.Build._publish(
            {
                "kind": "bundle",
                "bundle": bundle,
                "variant": variant,
                "directories": [directory],
                **extra,
            }
        )

    def _age(self, build, days):
        build.superseded_at = fields.Datetime.now() - timedelta(days=days)

    def test_a_variant_never_supersedes_another(self):
        plain = self._publish("/web/assets/esm/aaaa/")
        paged = self._publish("/web/assets/esm/bbbb/", variant="page=web.assets_web")
        self.assertEqual((plain | paged).mapped("state"), ["current", "current"])

    def test_a_rebuild_supersedes_and_keeps_the_previous_build_served(self):
        row = self._row("/web/assets/esm/aaaa/")
        first = self._publish("/web/assets/esm/aaaa/")
        second = self._publish("/web/assets/esm/bbbb/")
        self.assertEqual(first.state, "superseded")
        self.assertTrue(first.superseded_at)
        self.assertEqual(second.state, "current")
        self.assertTrue(row.exists(), "a page rendered a minute ago still asks for it")

    def test_reusing_an_older_build_extends_its_grace_without_recurrenting_it(self):
        first = self._publish("/web/assets/esm/aaaa/")
        second = self._publish("/web/assets/esm/bbbb/")
        self._age(first, 3)
        before = first.superseded_at
        again = self._publish("/web/assets/esm/aaaa/")
        self.assertEqual(again, first)
        self.assertEqual(first.state, "superseded")
        self.assertGreater(first.superseded_at, before)
        self.assertEqual(second.state, "current")

    def test_two_instances_on_different_code_do_not_flip_the_current_build(self):
        a = self._publish("/web/assets/esm/aaaa/")
        b = self._publish("/web/assets/esm/bbbb/")
        for _request in range(3):
            self._publish("/web/assets/esm/aaaa/")
            self._publish("/web/assets/esm/bbbb/")
        self.assertEqual((a.state, b.state), ("superseded", "current"))

    def test_the_sweep_waits_for_the_grace(self):
        kept_row = self._row("/web/assets/esm/aaaa/")
        old = self._publish("/web/assets/esm/aaaa/")
        self._publish("/web/assets/esm/bbbb/")
        self._age(old, 1)
        self.Build._sweep()
        self.assertTrue(old.exists())
        self.assertTrue(kept_row.exists())
        self._age(old, 30)
        self.Build._sweep()
        self.assertFalse(old.exists())
        self.assertFalse(kept_row.exists())

    def test_the_sweep_flushes_the_assets_caches_when_it_deletes_rows(self):
        self._row("/web/assets/esm/aaaa/")
        old = self._publish("/web/assets/esm/aaaa/")
        self._publish("/web/assets/esm/bbbb/")
        self._age(old, 400)
        with patch.object(type(self.env.registry), "clear_cache") as clear_cache:
            self.Build._sweep()
        self.assertIn("assets", [c.args[0] for c in clear_cache.call_args_list])

    def test_the_sweep_keeps_a_directory_another_build_still_owns(self):
        shared = self._row("/web/assets/esm/cccc/")
        old = self._publish("/web/assets/esm/cccc/")
        self._publish("/web/assets/esm/dddd/")
        self._publish("/web/assets/esm/cccc/", variant="page=web.assets_frontend")
        self._age(old, 30)
        self.Build._sweep()
        self.assertFalse(old.exists())
        self.assertTrue(shared.exists(), "the page variant compiled the same bytes")

    def test_one_current_build_per_variant_is_a_constraint(self):
        self._publish("/web/assets/esm/aaaa/")
        with (
            mute_logger("odoo.db.cursor"),
            self.assertRaises(UniqueViolation),
            self.env.cr.savepoint(),
        ):
            self.Build.create(
                {
                    "kind": "bundle",
                    "bundle": "test.builds",
                    "variant": "default",
                    "directories": ["/web/assets/esm/eeee/"],
                    "fingerprint": "eeee",
                }
            )

    def test_reuse_prefers_the_current_build_then_one_in_grace(self):
        old = self._publish("/web/assets/esm/aaaa/", source_key="k1")
        current = self._publish("/web/assets/esm/bbbb/", source_key="k2")
        self.assertEqual(
            self.Build._find_reusable("bundle", "test.builds", "default", "k2"),
            current,
        )
        self.assertEqual(
            self.Build._find_reusable("bundle", "test.builds", "default", "k1"), old
        )
        self.assertFalse(
            self.Build._find_reusable("bundle", "test.builds", "default", "k3")
        )

    def test_another_variant_built_from_the_same_sources_is_reused(self):
        first = self._publish(
            "/web/assets/esm/aaaa/", variant="website_id=1", source_key="k1"
        )
        self.assertEqual(
            self.Build._find_reusable("bundle", "test.builds", "website_id=2", "k1"),
            first,
        )
        self.assertFalse(
            self.Build._find_reusable("group", "test.builds", "website_id=2", "k1")
        )

    def test_the_variant_s_own_build_is_preferred_to_another_s(self):
        self._publish("/web/assets/esm/aaaa/", variant="website_id=1", source_key="k1")
        own = self._publish(
            "/web/assets/esm/aaaa/", variant="website_id=2", source_key="k1"
        )
        self._publish("/web/assets/esm/aaaa/", variant="website_id=3", source_key="k1")
        self.assertEqual(
            self.Build._find_reusable("bundle", "test.builds", "website_id=2", "k1"),
            own,
        )

    def test_the_same_rows_under_another_source_key_are_not_current(self):
        spec = {
            "kind": "bundle",
            "bundle": "test.builds",
            "variant": "default",
            "directories": ["/web/assets/esm/aaaa/"],
            "source_key": "k1",
        }
        self.Build._publish(spec)
        self.assertTrue(self.Build._is_current(spec))
        self.assertFalse(self.Build._is_current({**spec, "source_key": "k2"}))
        republished = self.Build._publish({**spec, "source_key": "k2"})
        self.assertEqual(republished.source_key, "k2")
        self.assertEqual(
            self.Build._find_reusable("bundle", "test.builds", "default", "k2"),
            republished,
        )

    def test_a_bundle_no_installed_addon_declares_is_retired(self):
        gone = self._publish(
            "/web/assets/esm/ffff/", bundle="test_builds_not_an_addon.assets"
        )
        kept = self._publish("/web/assets/esm/abab/", bundle="web.assets_web")
        self.Build._retire_uninstalled()
        self.assertEqual(gone.state, "superseded")
        self.assertEqual(kept.state, "current")

    def test_an_unchanged_publish_writes_nothing(self):
        build = self._publish("/web/assets/esm/aaaa/", source_key="k")
        Model = type(self.Build)
        refuse = AssertionError("an unchanged publish must not write")
        with (
            patch.object(Model, "write", side_effect=refuse),
            patch.object(Model, "create", side_effect=refuse),
        ):
            again = self._publish("/web/assets/esm/aaaa/", source_key="k")
        self.assertEqual(again, build)


@tagged("post_install", "-at_install", "assets_bundle")
class TestEsmBuildVariantsAreServedSideBySide(TransactionCase):
    def test_two_variants_of_one_bundle_both_stay_served(self):
        qweb = self.env["ir.qweb"]
        with patch.object(ir_qweb_assets._module, "current_test", None):
            plain = qweb._save_esm_attachment("test.builds.side", "export const a=1;")
            paged = qweb._save_esm_attachment(
                "test.builds.side",
                "export const a=2;",
                variant="page=web.assets_frontend",
            )
            plain_again = qweb._save_esm_attachment(
                "test.builds.side", "export const a=1;"
            )
        self.assertEqual(plain_again, plain)
        IrAttachment = self.env["ir.attachment"].sudo()
        for url in (plain, paged):
            with self.subTest(url=url):
                self.assertTrue(
                    IrAttachment.search_count(
                        IrAttachment._get_domain_generated_assets(url)
                    )
                )
        builds = (
            self.env["ir.asset.build"]
            .sudo()
            .search([("bundle", "=", "test.builds.side")])
        )
        self.assertEqual(builds.mapped("state"), ["current", "current"])


@tagged("post_install", "-at_install", "assets_bundle")
class TestEsmBuildRobustness(TransactionCase):
    def test_the_publication_lock_works_on_a_cursor_already_in_a_transaction(self):
        self.env.cr.execute("SELECT 1")
        self.env["ir.qweb"]._lock_esm_publication(self.env.cr)

    def test_a_group_is_named_by_its_code_not_its_metafile(self):
        qweb = self.env["ir.qweb"]
        code = {"g6.child.esm.js": b"export const x = 1;"}
        with patch.object(ir_qweb_assets._module, "current_test", None):
            first = qweb._save_esm_group(
                "runtime:g6.parent",
                {**code, "group.meta.json": b'{"tmp": "/tmp/odoo-esbuild-aaaa"}'},
                ["g6.child"],
                variant="default",
                source_key="g6",
            )
            second = qweb._save_esm_group(
                "runtime:g6.parent",
                {**code, "group.meta.json": b'{"tmp": "/tmp/odoo-esbuild-bbbb"}'},
                ["g6.child"],
                variant="default",
                source_key="g6",
            )
        self.assertEqual(first, second)

    def test_a_publication_race_that_cannot_settle_does_not_raise(self):
        Build = self.env["ir.asset.build"].sudo()
        with patch.object(
            type(Build), "_publish_once", side_effect=SerializationFailure("raced")
        ):
            published = Build._publish(
                {
                    "kind": "bundle",
                    "bundle": "test.builds.race",
                    "variant": "default",
                    "directories": ["/web/assets/esm/rrrr/"],
                }
            )
        self.assertFalse(published)

    def test_a_readonly_cursor_defers_a_build_whose_rows_are_served(self):
        qweb = self.env["ir.qweb"]
        build = {
            "kind": "bundle",
            "bundle": "test.builds.readonly",
            "variant": "default",
            "directories": ["/web/assets/esm/ssss/"],
        }
        with (
            patch.object(ir_qweb_assets._module, "current_test", None),
            patch.object(self.env.cr, "_readonly", True),
        ):
            qweb._save_esm_attachment_rows(
                [], bundle="test.builds.readonly", build=build
            )

    def test_a_supersession_flushes_no_worker_s_assets_cache(self):
        Build = self.env["ir.asset.build"].sudo()
        spec = {"kind": "bundle", "bundle": "test.builds.inval", "variant": "default"}
        Build._publish({**spec, "directories": ["/web/assets/esm/tttt/"]})
        with patch.object(type(self.env.registry), "clear_cache") as clear_cache:
            Build._publish({**spec, "directories": ["/web/assets/esm/uuuu/"]})
        self.assertNotIn("assets", [c.args[0] for c in clear_cache.call_args_list])


@tagged("post_install", "-at_install", "assets_bundle")
class TestEsbuildLockSerializesCompiles(TransactionCase):
    registry_test_mode = False
    BUNDLE = "test.builds.lock"

    def setUp(self):
        super().setUp()
        self.key = f"lock-{uuid.uuid4().hex}"
        self.variant = esm_index.variant_key({})
        self.compiles = []
        self.qweb = self.env["ir.qweb"]
        circuit = self.qweb._esbuild_circuit
        self.addCleanup(circuit.restore, circuit.snapshot())
        circuit.clear()
        self.env.cr.execute("SELECT 1")
        self.addCleanup(self._forget_committed_build)

    def _forget_committed_build(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute(
                "DELETE FROM ir_asset_build WHERE source_key = %s RETURNING directories",
                (self.key,),
            )
            directories = [d for (dirs,) in cr.fetchall() for d in dirs]
            if directories:
                cr.execute(
                    "DELETE FROM ir_attachment WHERE url LIKE ANY(%s)",
                    ([f"{d}%" for d in directories],),
                )

    def _committed_build(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute(
                "SELECT count(*) FROM ir_asset_build WHERE source_key = %s",
                (self.key,),
            )
            return cr.fetchone()[0]

    @contextlib.contextmanager
    def _own_lock_cursor(self, _bundle, on_release=None):
        with db_connect(self.env.cr.dbname).cursor() as lock_cr:
            try:
                yield lock_cr
                if on_release:
                    on_release()
            finally:
                lock_cr.rollback()

    def _compile(self, on_release=None):
        def compile_bundle(*_args, **_kwargs):
            self.compiles.append(1)
            return EsbuildResult(f"export const k = {self.key!r};", None, None)

        Qweb = type(self.qweb)
        with (
            patch.object(
                Qweb,
                "_get_esbuild_lock_cursor",
                lambda _self, bundle: self._own_lock_cursor(bundle, on_release),
            ),
            patch.object(Qweb, "_get_dynamic_child_bundles", lambda *_a, **_k: []),
            patch.object(
                Qweb, "_get_esbuild_child_externals", lambda *_a, **_k: (None, {})
            ),
            patch.object(Qweb, "_get_exported_specs", lambda *_a, **_k: frozenset()),
            patch.object(Qweb, "_esm_source_key", lambda *_a, **_k: self.key),
            patch.object(AssetsBundle, "esbuild_native_bundle", compile_bundle),
            patch.object(ir_qweb_assets._module, "current_test", None),
            patch.object(ir_qweb_assets, "request", object()),
        ):
            return self.qweb._compile_with_esbuild_locked(
                self.BUNDLE, AssetsBundle(self.BUNDLE, [], env=self.env), {}
            )

    def test_the_waiter_reuses_a_build_committed_after_its_snapshot(self):
        self.qweb._save_esm_attachment(
            self.BUNDLE,
            "export const k = 'other';",
            source_key=self.key,
            variant=self.variant,
        )
        self.assertFalse(
            self.env["ir.asset.build"]
            .sudo()
            ._find_reusable("bundle", self.BUNDLE, self.variant, self.key),
            "the test transaction cannot see the committed build",
        )
        result, _children = self._compile()
        self.assertEqual(self.compiles, [], "the lock holder's build is reused")
        self.assertTrue(result.prebuilt)
        self.assertIn("'other'", result.code)

    def test_a_committed_build_is_served_without_taking_the_lock(self):
        self.qweb._save_esm_attachment(
            self.BUNDLE,
            "export const k = 'other';",
            source_key=self.key,
            variant=self.variant,
        )
        locked = []
        opened = []
        Registry = type(self.env.registry)
        real_cursor = Registry.cursor

        def spy_cursor(registry, *args, **kwargs):
            opened.append(kwargs.get("readonly"))
            return real_cursor(registry, *args, **kwargs)

        with (
            patch.object(
                type(self.qweb),
                "_acquire_esbuild_lock",
                lambda _self, bundle, cr=None, timeout_s=None: locked.append(bundle),
            ),
            patch.object(Registry, "cursor", spy_cursor),
        ):
            result, _children = self._compile()
        self.assertEqual(locked, [], "a published build needs no lock")
        self.assertIn(True, opened)
        self.assertEqual(self.compiles, [])
        self.assertIn("'other'", result.code)

    def test_two_cold_requests_for_one_bundle_compile_it_once(self):
        first, _children = self._compile()
        second, _children = self._compile()
        self.assertEqual(len(self.compiles), 1)
        self.assertEqual(first.source_key, self.key)
        self.assertTrue(second.prebuilt)

    def test_a_lock_timeout_declines_instead_of_queuing(self):
        from psycopg.errors import LockNotAvailable

        def timed_out(_self, bundle, cr=None, timeout_s=None):
            self.assertTrue(timeout_s, "the lock is taken with a timeout")
            raise LockNotAvailable("lock timeout")

        with patch.object(type(self.qweb), "_acquire_esbuild_lock", timed_out):
            with self.assertLogs("odoo.assets.fallback", level="WARNING"):
                result, children = self._compile()
        self.assertEqual(self.compiles, [])
        self.assertEqual(result.code, "")
        self.assertEqual(children, [])

    def test_the_holder_publishes_before_it_releases_the_lock(self):
        seen_at_release = []
        result, _children = self._compile(
            on_release=lambda: seen_at_release.append(self._committed_build())
        )
        self.assertEqual(len(self.compiles), 1)
        self.assertEqual(result.source_key, self.key)
        self.assertEqual(seen_at_release, [1])


@tagged("post_install", "-at_install", "assets_bundle")
class TestEsmRowsWrittenOnTheCallersTransaction(TransactionCase):
    def test_the_nodes_naming_them_do_not_outlive_a_rollback(self):
        qweb = self.env["ir.qweb"]
        IrAttachment = self.env["ir.attachment"]
        vals = IrAttachment._prepare_generated_asset_vals(
            name="test.builds.rollback.esm.js",
            mimetype="text/javascript",
            raw=b"export {};",
            url=f"/web/assets/esm/{uuid.uuid4().hex[:16]}/test.builds.rollback.esm.js",
        )
        computed = []
        original = AssetsBundle.get_native_module_data

        def counted(bundle):
            computed.append(bundle.name)
            return original(bundle)

        self.env.registry.clear_cache("assets")
        with (
            patch.object(ir_qweb_assets._module, "current_test", None),
            patch.object(AssetsBundle, "get_native_module_data", counted),
        ):
            savepoint = self.env.cr.savepoint()
            qweb._save_esm_attachment_rows([vals], bundle="test.builds.rollback")
            qweb._get_native_module_data_cached("test_assetsbundle.native_esm", {})
            savepoint.close(rollback=True)
            self.assertFalse(IrAttachment.search_count([("url", "=", vals["url"])]))
            qweb._get_native_module_data_cached("test_assetsbundle.native_esm", {})
        self.assertEqual(len(computed), 2, "what was cached over the rows is dropped")

    def test_a_test_keeps_its_copy_of_committed_rows_to_itself(self):
        qweb = self.env["ir.qweb"]
        IrAttachment = self.env["ir.attachment"]
        vals = IrAttachment._prepare_generated_asset_vals(
            name="test.builds.test_copy.esm.js",
            mimetype="text/javascript",
            raw=b"export {};",
            url=f"/web/assets/esm/{uuid.uuid4().hex[:16]}/test.builds.test_copy.esm.js",
        )
        scope = transaction_case._TestCacheScope(self.registry)
        self.assertIn("assets", scope.trusted)
        with (
            patch.object(
                type(qweb),
                "_save_esm_attachment_rows_autonomously",
                lambda *_a, **_k: True,
            ),
            patch.object(transaction_case, "_cache_scope", [scope]),
        ):
            qweb._save_esm_attachment_rows([vals], bundle="test.builds.test_copy")
        self.assertTrue(IrAttachment.search_count([("url", "=", vals["url"])]))
        self.assertFalse(
            {"assets", "assets.links", "assets.files"} & scope.trusted,
            "what the test caches over its copy would reach the next test",
        )


@tagged("post_install", "-at_install", "assets_bundle")
class TestEsmPublicationIgnoresForeignRows(TransactionCase):
    def test_a_foreign_row_on_the_url_does_not_suppress_the_generated_row(self):
        IrAttachment = self.env["ir.attachment"]
        url = f"/web/assets/esm/{uuid.uuid4().hex[:16]}/test.builds.foreign.esm.js"
        squatter = new_test_user(
            self.env, login="esm_squatter", groups="base.group_user"
        )
        IrAttachment.with_user(squatter).create(
            {"name": "squat.esm.js", "type": "url", "url": url}
        )
        vals = IrAttachment._prepare_generated_asset_vals(
            name="test.builds.foreign.esm.js",
            mimetype="text/javascript",
            raw=b"export {};",
            url=url,
        )
        written = type(self.env["ir.qweb"])._publish_esm_rows(self.env, [vals], None)
        self.assertEqual(written, 1)
        self.assertTrue(IrAttachment._search_generated_assets(url=url))
