from odoo.models import ACTING_PARTNER_KEY
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.authority_keys import strip_authority_keys


@tagged("post_install", "-at_install")
class TestActingPartner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.privilege = cls.env["res.groups"].create(
            {"name": "Probe: read the contact acted for", "is_privilege": True}
        )
        cls.env["ir.model.data"].create(
            {
                "module": "base",
                "name": "probe_privilege_acting_partner",
                "model": "res.groups",
                "res_id": cls.privilege.id,
            }
        )
        predicate = cls.env["ir.access.predicate"].create(
            {
                "name": "base.probe_acted_for",
                "description": "it is the contact acted for",
                "template": "[(args.at + 'id', '=', P.partner)]",
            }
        )
        cls.env["ir.access"].create(
            {
                "name": "Probe privilege: read the contact acted for",
                "model_id": cls.env["ir.model"]._get_id("res.partner"),
                "group_id": cls.privilege.id,
                "kind": "permission",
                "operation": "r",
                "reach": "predicate",
                "predicate_id": predicate.id,
                "predicate_args": {"at": ""},
            }
        )
        cls.user = new_test_user(
            cls.env, login="acting_probe", groups="base.group_portal"
        )
        cls.contact_a, cls.contact_b = cls.env["res.partner"].create(
            [
                {"name": "Acted for A", "parent_id": cls.env.company.partner_id.id},
                {"name": "Acted for B"},
            ]
        )
        cls.name = "base.probe_privilege_acting_partner"

    def _reader(self, partner=None):
        Partner = self.env["res.partner"].with_user(self.user)
        if partner:
            Partner = Partner.with_acting_partner(partner)
        return Partner.with_privilege(self.name)

    def _reads(self, reader, partner):
        return bool(reader.search([("id", "=", partner.id)]))

    def test_the_rows_read_the_contact_acted_for_as_the_principal_s_partner(self):
        for _round in range(2):
            self.assertTrue(self._reads(self._reader(self.contact_a), self.contact_a))
            self.assertFalse(self._reads(self._reader(self.contact_a), self.contact_b))
            self.assertTrue(self._reads(self._reader(self.contact_b), self.contact_b))
            self.assertFalse(self._reads(self._reader(self.contact_b), self.contact_a))
        self.assertFalse(self._reads(self._reader(), self.contact_a))
        self.assertTrue(self._reads(self._reader(), self.user.partner_id))

    def test_the_user_stays_the_user_and_binds_follow_the_contact(self):
        Access = self.env["ir.access"].with_user(self.user)
        acting = Access.with_acting_partner(self.contact_a)
        self.assertEqual(acting.env.uid, self.user.id)
        self.assertEqual(acting._access_bind_partner(), self.contact_a.id)
        self.assertEqual(
            acting._access_bind_commercial_partner(),
            self.contact_a.commercial_partner_id.id,
        )
        self.assertEqual(Access._access_bind_partner(), self.user.partner_id.id)

    def test_two_contacts_never_share_a_verdict_or_a_cache_scope(self):
        a = self._reader(self.contact_a).env
        b = self._reader(self.contact_b).env
        self.assertNotEqual(a._access_scope(), b._access_scope())
        self.assertNotEqual(a._read_access_key, b._read_access_key)
        self.assertIsNot(a._principal_verdicts, b._principal_verdicts)

    def test_another_user_acts_for_no_one(self):
        acting = self.env["res.partner"].with_acting_partner(self.contact_a)
        self.assertNotIn(ACTING_PARTNER_KEY, acting.with_user(self.user).env.context)

    def test_a_client_cannot_name_the_contact(self):
        self.assertEqual(
            strip_authority_keys(
                {ACTING_PARTNER_KEY: self.contact_a.id, "lang": "en_US"}
            ),
            {"lang": "en_US"},
        )
