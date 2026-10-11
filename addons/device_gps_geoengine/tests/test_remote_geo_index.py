from unittest.mock import ANY, call, patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import get_index_name

from odoo.addons.device.tools import fdw
from odoo.addons.geoengine.models.fields import geo_index_name

MODULE = "odoo.addons.device_gps_geoengine.models.device_data_log_gps.fdw"


@tagged("post_install", "-at_install")
class TestRemoteGeoIndex(TransactionCase):
    def _create(self, *, foreign=True, dblink=True, exists=False):
        with (
            patch(f"{MODULE}.is_foreign", return_value=foreign),
            patch(f"{MODULE}.dblink_available", return_value=dblink),
            patch(f"{MODULE}.foreign_server", return_value="gps_srv"),
            patch(f"{MODULE}.remote_table", return_value="public.remote_gps"),
            patch(f"{MODULE}.remote_index_exists", return_value=exists),
            patch(f"{MODULE}.remote_exec") as remote_exec,
        ):
            self.env["device.data.log.gps"]._create_remote_geo_indexes()
            remote_exec.assert_not_called()
            self.env.cr.postcommit.run()
        return remote_exec

    def test_a_foreign_log_gets_its_spatial_index_built_concurrently_remotely(self):
        # an invalid index left by a failed concurrent build goes first
        remote_exec = self._create()
        self.assertEqual(
            remote_exec.call_args_list,
            [
                call(
                    ANY,
                    "gps_srv",
                    "DROP INDEX CONCURRENTLY IF EXISTS "
                    "public.device_data_log_gps_the_point_gist_index",
                ),
                call(
                    ANY,
                    "gps_srv",
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                    "device_data_log_gps_the_point_gist_index "
                    "ON public.remote_gps USING gist (the_point)",
                ),
            ],
        )

    def test_an_existing_remote_index_is_left_alone(self):
        self._create(exists=True).assert_not_called()

    def test_a_local_table_or_a_missing_dblink_changes_nothing_remotely(self):
        self._create(foreign=False).assert_not_called()
        self._create(dblink=False).assert_not_called()


@tagged("post_install", "-at_install")
class TestRemoteIndexesMirrorTheLocalOnes(TransactionCase):
    def test_every_index_the_orm_builds_locally_is_built_remotely(self):
        model = self.env["device.data.log.gps"]
        ddl = dict(fdw.remote_index_ddl(model, "public.remote_gps"))
        self.env.cr.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s"
            " AND indexname NOT IN (%s, %s)",
            [
                model._table,
                f"{model._table}_pkey",
                geo_index_name(model._table, "the_point"),
            ],
        )
        self.assertCountEqual(ddl, [name for (name,) in self.env.cr.fetchall()])
        for create in ddl.values():
            self.assertRegex(create, r"^CREATE (UNIQUE )?INDEX CONCURRENTLY ")
        channel = get_index_name(model._table, "channel_id")
        self.assertEqual(
            ddl[channel],
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {channel} ON public.remote_gps "
            'USING btree ("channel_id") WHERE "channel_id" IS NOT NULL',
        )
