from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

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
        return remote_exec

    def test_a_foreign_log_gets_its_spatial_index_built_concurrently_remotely(self):
        remote_exec = self._create()
        remote_exec.assert_called_once_with(
            self.env.cr,
            "gps_srv",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "device_data_log_gps_the_point_gist_index "
            "ON public.remote_gps USING gist (the_point)",
        )

    def test_an_existing_remote_index_is_left_alone(self):
        self._create(exists=True).assert_not_called()

    def test_a_local_table_or_a_missing_dblink_changes_nothing_remotely(self):
        self._create(foreign=False).assert_not_called()
        self._create(dblink=False).assert_not_called()
