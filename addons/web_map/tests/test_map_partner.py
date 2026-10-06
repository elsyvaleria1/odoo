from odoo.exceptions import AccessError
from odoo.tests import Form, TransactionCase


class TestMapPartnerAddress(TransactionCase):
    """Cover the flattened address the map panel displays."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env["res.country"].create({"name": "Testland", "code": "ZZ"})
        cls.state = cls.env["res.country.state"].create(
            {
                "name": "Teststate",
                "code": "TS",
                "country_id": cls.country.id,
            }
        )

    def test_complete_address_joins_every_part(self):
        """Check that every filled address part joins the flattened address."""
        partner = self.env["res.partner"].create(
            {
                "name": "Full Address",
                "street": "S1",
                "street2": "S2",
                "zip": "12345",
                "city": "Town",
                "state_id": self.state.id,
                "country_id": self.country.id,
            }
        )

        self.assertEqual(
            partner.contact_address_complete,
            "S1, S2, 12345 Town, Teststate, Testland",
        )

    def test_complete_address_skips_missing_parts(self):
        """Check that missing address parts are left out of the flattening."""
        partner = self.env["res.partner"].create(
            {"name": "Street Only", "street": "Solo"}
        )

        self.assertEqual(partner.contact_address_complete, "Solo")

    def test_complete_address_drops_the_trailing_separator(self):
        """Check that the flattened address does not end with a separator."""
        partner = self.env["res.partner"].create(
            {"name": "City Only", "city": "Ciudad"}
        )

        self.assertEqual(partner.contact_address_complete, "Ciudad")

    def test_complete_address_without_any_part_is_empty(self):
        """Check that a partner without address parts yields an empty string."""
        partner = self.env["res.partner"].create({"name": "No Address"})

        self.assertEqual(partner.contact_address_complete, "")

    def test_complete_address_follows_the_address(self):
        """Check that rewriting the city recomputes the flattened address."""
        partner = self.env["res.partner"].create({"name": "Moving", "city": "Before"})

        partner.city = "After"

        self.assertEqual(partner.contact_address_complete, "After")

    def test_complete_address_follows_the_state(self):
        """Check that rewriting only the state recomputes the flattened address.

        Regression test for a missing 'state_id' in @api.depends (tracked
        under task t24775): _compute_complete_address reads state_id.name but
        used to omit state_id from its depends, so a state-only edit left the
        stored search-filter field silently stale.
        """
        partner = self.env["res.partner"].create({"name": "Moving", "city": "Town"})

        partner.state_id = self.state.id

        self.assertEqual(partner.contact_address_complete, "Town, Teststate")

    def test_coordinates_are_address_fields(self):
        """Check that both coordinates are declared as address fields."""
        address_fields = self.env["res.partner"]._address_fields()

        self.assertIn("partner_latitude", address_fields)
        self.assertIn("partner_longitude", address_fields)

    def test_coordinates_are_not_formatting_fields(self):
        """Check that neither coordinate is declared as a formatting field."""
        formatting_fields = self.env["res.partner"]._formatting_address_fields()

        self.assertNotIn("partner_latitude", formatting_fields)
        self.assertNotIn("partner_longitude", formatting_fields)


class TestMapPartnerGeolocation(TransactionCase):
    """Cover what web_map adds on top of base's coordinate invariant.

    Whether a write invalidates the pair is base's, and tested there
    (TestPartnerGeolocationInvalidation). What is web_map's is that the pair
    travels with the address to child contacts, which its `_address_fields`
    override is what buys, and the form-level onchange.
    """

    def test_coordinates_follow_the_address_to_a_child_contact(self):
        """Check that clearing a parent's position clears its contacts' too."""
        parent = self.env["res.partner"].create(
            {"name": "Parent", "is_company": True, "street": "Old street"}
        )
        child = self.env["res.partner"].create(
            {"name": "Child", "parent_id": parent.id, "type": "contact"}
        )
        (parent + child).write({"partner_latitude": 5.0, "partner_longitude": 6.0})

        parent.write({"street": "New street"})

        self.assertEqual(child.street, "New street", "address fields must be synced")
        self.assertFalse(child.partner_latitude)
        self.assertFalse(child.partner_longitude)

    def test_update_latitude_longitude_writes_each_partner(self):
        """Check that update_latitude_longitude stores each partner's pair."""
        first = self.env["res.partner"].create({"name": "Geo One"})
        second = self.env["res.partner"].create({"name": "Geo Two"})

        result = self.env["res.partner"].update_latitude_longitude(
            [
                {"id": first.id, "partner_latitude": 1.5, "partner_longitude": 2.5},
                {"id": second.id, "partner_latitude": 3.5, "partner_longitude": 4.5},
            ]
        )

        self.assertEqual(result, {})
        self.assertEqual((first.partner_latitude, first.partner_longitude), (1.5, 2.5))
        self.assertEqual(
            (second.partner_latitude, second.partner_longitude), (3.5, 4.5)
        )

    def test_update_latitude_longitude_groups_shared_coordinates(self):
        """Check that partners sharing a point both receive the coordinates."""
        first = self.env["res.partner"].create({"name": "Same Spot One"})
        second = self.env["res.partner"].create({"name": "Same Spot Two"})

        self.env["res.partner"].update_latitude_longitude(
            [
                {"id": first.id, "partner_latitude": 9.0, "partner_longitude": 9.0},
                {"id": second.id, "partner_latitude": 9.0, "partner_longitude": 9.0},
            ]
        )

        self.assertEqual((first.partner_latitude, first.partner_longitude), (9.0, 9.0))
        self.assertEqual(
            (second.partner_latitude, second.partner_longitude), (9.0, 9.0)
        )

    def test_update_latitude_longitude_ignores_incomplete_entries(self):
        """Check that entries missing an id or a coordinate are skipped."""
        partner = self.env["res.partner"].create({"name": "Untouched"})

        result = self.env["res.partner"].update_latitude_longitude(
            [
                {"id": partner.id},
                {"partner_latitude": 9.9, "partner_longitude": 9.9},
                {"id": partner.id, "partner_latitude": 9.9},
            ]
        )

        self.assertEqual(result, {})
        self.assertEqual(
            (partner.partner_latitude, partner.partner_longitude), (0.0, 0.0)
        )

    def test_onchange_clears_coordinates_when_the_address_changes(self):
        """Check that editing a form address field clears the coordinates."""
        partner = self.env["res.partner"].create(
            {
                "name": "Form Edit",
                "partner_latitude": 5.0,
                "partner_longitude": 6.0,
            }
        )

        with Form(partner) as partner_form:
            partner_form.street = "New Pin Street 1"

        self.assertFalse(partner.partner_latitude)
        self.assertFalse(partner.partner_longitude)

    def test_onchange_clears_coordinates_when_street2_changes(self):
        """street2 feeds contact_address_complete, so editing it must also
        clear the coordinates, like the other address fields do."""
        partner = self.env["res.partner"].create(
            {
                "name": "Form Edit Street2",
                "partner_latitude": 5.0,
                "partner_longitude": 6.0,
            }
        )

        with Form(partner) as partner_form:
            partner_form.street2 = "New Pin Street 2"

        self.assertFalse(partner.partner_latitude)
        self.assertFalse(partner.partner_longitude)


class TestMapPartnerStoredAddress(TransactionCase):
    """Cover the stored address the map searches on."""

    def test_complete_address_follows_a_renamed_country(self):
        """Check that renaming a country recomputes the stored address.

        `contact_address_complete` is stored and searched on, and it reads
        `country_id.name`, so a rename that the depends did not name left every
        partner in that country carrying its old name.
        """
        country = self.env["res.country"].create({"name": "Oldland", "code": "ZY"})
        partner = self.env["res.partner"].create(
            {"name": "Local", "city": "Town", "country_id": country.id}
        )
        self.assertEqual(partner.contact_address_complete, "Town, Oldland")

        country.name = "Newland"

        self.assertEqual(partner.contact_address_complete, "Town, Newland")


class TestMapPartnerCoordinatesRpc(TransactionCase):
    """Cover `update_latitude_longitude`, which the map view calls over RPC."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Target"})

    def test_a_malformed_payload_writes_nothing(self):
        """Check that entries that are not a well-formed position are dropped."""
        self.env["res.partner"].update_latitude_longitude(
            [
                "not a dict",
                {
                    "id": self.partner.id,
                    "partner_latitude": "10",
                    "partner_longitude": 10,
                },
                {
                    "id": self.partner.id,
                    "partner_latitude": True,
                    "partner_longitude": 1,
                },
                {
                    "id": str(self.partner.id),
                    "partner_latitude": 1,
                    "partner_longitude": 1,
                },
            ]
        )

        self.assertEqual(self.partner.partner_latitude, 0.0)
        self.assertEqual(self.partner.partner_longitude, 0.0)

    def test_an_out_of_range_position_writes_nothing(self):
        """Check that a position off the globe is refused.

        The payload is client-supplied, so a geocoder answering nonsense — or a
        caller inventing it — must not reach the column.
        """
        self.env["res.partner"].update_latitude_longitude(
            [
                {
                    "id": self.partner.id,
                    "partner_latitude": 91.0,
                    "partner_longitude": 0.0,
                }
            ]
        )

        self.assertEqual(self.partner.partner_latitude, 0.0)

    def test_a_missing_partner_is_skipped_rather_than_raising(self):
        """Check that an id that no longer exists does not abort the call."""
        missing_id = self.partner.id
        self.partner.unlink()

        result = self.env["res.partner"].update_latitude_longitude(
            [{"id": missing_id, "partner_latitude": 1.0, "partner_longitude": 2.0}]
        )

        self.assertEqual(result, {})

    def test_a_partner_the_caller_cannot_read_is_refused(self):
        """Check that read access gates the write the map performs in sudo.

        The write runs in sudo so an internal user can cache a position on a
        partner they may not edit; without this check that sudo would let any
        internal user set coordinates on any partner in the database.
        """
        restricted = self.env["res.partner"].create({"name": "Restricted"})
        self.env["ir.access"].create(
            {
                "name": "hide the restricted partner",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "group_id": self.env.ref("base.group_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "crud",
                "domain": f"[('id', '!=', {restricted.id})]",
            }
        )
        user = self.env["res.users"].create(
            {
                "name": "Internal",
                "login": "map_internal_user",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )

        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(user).update_latitude_longitude(
                [
                    {
                        "id": restricted.id,
                        "partner_latitude": 1.0,
                        "partner_longitude": 2.0,
                    }
                ]
            )

        self.assertEqual(restricted.partner_latitude, 0.0)

    def test_an_internal_user_caches_a_position_they_cannot_write(self):
        """Check that a readable but unwritable partner still gets its position."""
        self.env["ir.access"].create(
            {
                "name": "read-only partners",
                "model_id": self.env["ir.model"]._get("res.partner").id,
                "group_id": self.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
            }
        )
        user = self.env["res.users"].create(
            {
                "name": "Internal",
                "login": "map_readonly_user",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )

        self.env["res.partner"].with_user(user).update_latitude_longitude(
            [{"id": self.partner.id, "partner_latitude": 1.5, "partner_longitude": 2.5}]
        )

        self.assertEqual(
            (self.partner.partner_latitude, self.partner.partner_longitude), (1.5, 2.5)
        )
