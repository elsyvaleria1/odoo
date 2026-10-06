from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestClientAreaCompute(TransactionCase):
    def _polygon(self, latitude, longitude):
        return json_dumps(
            [
                [latitude - 0.01, longitude - 0.01],
                [latitude + 0.01, longitude - 0.01],
                [latitude + 0.01, longitude + 0.01],
                [latitude - 0.01, longitude + 0.01],
            ]
        )

    def _client_with_parcel(self, name, latitude=19.40, longitude=-99.10):
        partner = self.env["res.partner"].create({"name": name})
        parcel = self.env["device.geo.fence"].create(
            {
                "name": f"{name} Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": partner.id,
                "polygon_points": self._polygon(latitude, longitude),
            }
        )
        self.env.flush_all()
        self.env.invalidate_all()
        return partner, parcel

    def _stored_centroid(self, partner):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT ST_Y(ST_Centroid(client_the_area)),"
            " ST_X(ST_Centroid(client_the_area))"
            " FROM res_partner WHERE id = %s",
            (partner.id,),
        )
        latitude, longitude = self.env.cr.fetchone()
        return None if latitude is None else (latitude, longitude)

    def _assert_centroid(self, partner, latitude, longitude):
        centroid = self._stored_centroid(partner)
        self.assertIsNotNone(centroid)
        self.assertAlmostEqual(centroid[0], latitude, places=6)
        self.assertAlmostEqual(centroid[1], longitude, places=6)

    def test_archiving_the_only_parcel_clears_the_area(self):
        partner, parcel = self._client_with_parcel("Archive")
        self.assertIsNotNone(self._stored_centroid(partner))

        parcel.active = False

        self.assertIsNone(
            self._stored_centroid(partner),
            "the compute reads device_geo_fence with raw SQL, so without a "
            "flush it saw active still true and kept the archived parcel",
        )

    def test_retyping_the_parcel_clears_the_area(self):
        partner, parcel = self._client_with_parcel("Retype")
        self.assertIsNotNone(self._stored_centroid(partner))

        parcel.area_type = "structure"

        self.assertIsNone(
            self._stored_centroid(partner),
            "the query filters on area_type, so the compute has to depend on it",
        )

    def test_moving_the_parcel_moves_the_area(self):
        partner, parcel = self._client_with_parcel("Move")

        parcel.polygon_points = self._polygon(20.50, -98.00)

        self._assert_centroid(partner, 20.50, -98.00)

    def test_archiving_a_batch_clears_every_partner(self):
        first, first_parcel = self._client_with_parcel("Batch One")
        second, second_parcel = self._client_with_parcel("Batch Two", 21.0, -97.0)

        (first_parcel + second_parcel).write({"active": False})

        self.assertIsNone(self._stored_centroid(first))
        self.assertIsNone(self._stored_centroid(second))

    def test_an_unrelated_write_leaves_the_area_alone(self):
        partner, parcel = self._client_with_parcel("Unrelated")

        parcel.name = "Renamed"

        self._assert_centroid(partner, 19.40, -99.10)

    def test_a_client_mapped_but_never_geocoded_has_an_area_to_draw(self):
        partner, _parcel = self._client_with_parcel("Never Geocoded")

        self.assertFalse(partner.partner_latitude)
        self.assertFalse(partner.partner_longitude)
        self.assertTrue(
            self.env["res.partner"].search(
                [("id", "=", partner.id), ("client_the_area", "!=", False)]
            ),
            "the fallback circle is for clients without a parcel; this one "
            "has a parcel, so the overlay has a polygon to draw",
        )

    def test_the_overlay_selects_on_the_field_it_draws(self):
        layer = self.env.ref(
            "device_gps_geoengine.vector_layer_device_device_client_locations"
        )

        self.assertEqual(layer.geo_field_id.name, "client_the_area")
        self.assertIn("client_the_area", layer.model_domain)
        self.assertNotIn(
            "partner_latitude",
            layer.model_domain,
            "selecting on the coordinates hid every client whose parcel is "
            "mapped but who was never geocoded, which is the exact case the "
            "polygon fallback exists to cover",
        )
