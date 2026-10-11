import collections
import datetime
import time
import xmlrpc.client

import odoo
from odoo.exceptions import AccessDenied, AccessError
from odoo.http import _request_stack
from odoo.libs.collections import FrozenList, frozendict
from odoo.service import common as auth
from odoo.service import model
from odoo.tests import common
from odoo.tools import DotDict, mute_logger
from odoo.tools.misc import ReadonlyDict

from odoo.addons.base.tests.common import SavepointCaseWithUserDemo, declare_api_scope
from odoo.addons.rpc.controllers.xmlrpc import OdooMarshaller


class ReadonlyDictSubclass(ReadonlyDict):
    pass


class TestExternalAPI(SavepointCaseWithUserDemo):
    def test_call_kw(self):
        partner = self.env["res.partner"].create({"name": "MyPartner1"})
        args = (partner.ids, ["name"])
        kwargs = {"context": {"test": True}}
        model.call_kw(self.env["res.partner"], "read", args, kwargs)
        self.assertEqual(kwargs, {"context": {"test": True}})


@common.tagged("post_install", "-at_install")
class TestXMLRPC(common.HttpCase):
    def setUp(self):
        super().setUp()
        self.admin_uid = self.env.ref("base.user_admin").id
        self.admin_key = common.new_test_api_key(self.env.ref("base.user_admin"))

        ml_xml = mute_logger("odoo.addons.rpc.controllers.xmlrpc")
        ml_xml.__enter__()
        self.addCleanup(ml_xml.__exit__)

    def xmlrpc(self, model, method, *args, **kwargs):
        return self.xmlrpc_object.execute_kw(
            common.get_db_name(),
            self.admin_uid,
            self.admin_key,
            model,
            method,
            args,
            kwargs,
        )

    def test_01_xmlrpc_login(self):
        db_name = common.get_db_name()
        uid = self.xmlrpc_common.login(db_name, "admin", self.admin_key)
        self.assertEqual(uid, self.admin_uid)

    def test_xmlrpc_ir_model_search(self):
        o = self.xmlrpc_object
        db_name = common.get_db_name()
        ids = o.execute(
            db_name, self.admin_uid, self.admin_key, "ir.model", "search", []
        )
        self.assertIsInstance(ids, list)
        ids = o.execute(
            db_name, self.admin_uid, self.admin_key, "ir.model", "search", [], {}
        )
        self.assertIsInstance(ids, list)

    def test_xmlrpc_datetime(self):
        m = self.env.ref("base.model_auth_user_client_address")
        self.env["ir.access"].create(
            {
                "name": "w/e",
                "model_id": m.id,
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "permission",
                "operation": "cr",
            }
        )

        client = self.env["auth.user.client"].create(
            {"recognition_key_hash": "xmlrpc_datetime_key", "user_id": self.env.uid}
        )
        now = datetime.datetime.now()
        ids = self.xmlrpc(
            "auth.user.client.address",
            "create",
            {"client_id": client.id, "first_activity": now},
        )
        [r] = self.xmlrpc(
            "auth.user.client.address",
            "read",
            ids,
            ["first_activity"],
        )
        self.assertEqual(r["first_activity"], now.isoformat(" ", "seconds"))

    def test_xmlrpc_read_group(self):
        self.xmlrpc_object.execute(
            common.get_db_name(),
            self.admin_uid,
            self.admin_key,
            "res.partner",
            "formatted_read_group",
            [],
            ["parent_id"],
            ["color:sum"],
        )

    def test_xmlrpc_name_search(self):
        self.xmlrpc_object.execute(
            common.get_db_name(),
            self.admin_uid,
            self.admin_key,
            "res.partner",
            "name_search",
            "admin",
        )

    def test_xmlrpc_html_field(self):
        sig = '<p>bork bork bork <span style="font-weight: bork">bork</span><br></p>'
        r = self.env["res.users"].create(
            {"name": "bob", "login": "bob", "signature": sig}
        )
        self.assertEqual(str(r.signature), sig)
        [x] = self.xmlrpc("res.users", "read", r.id, ["signature"])
        self.assertEqual(x["signature"], sig)

    def test_xmlrpc_frozendict_marshalling(self):
        self.env.ref("base.user_admin").tz = "Europe/Brussels"
        ctx = self.xmlrpc_object.execute(
            common.get_db_name(),
            self.admin_uid,
            self.admin_key,
            "res.users",
            "context_get",
        )
        self.assertEqual(ctx["lang"], "en_US")
        self.assertEqual(ctx["tz"], "Europe/Brussels")

    def test_xmlrpc_fields_get_marshalling(self):
        fields = self.xmlrpc(
            "res.partner", "fields_get", ["parent_id"], ["type", "context"]
        )
        self.assertEqual(fields["parent_id"]["type"], "many2one")
        self.assertEqual(fields["parent_id"]["context"], {})

    def test_xmlrpc_readonly_dict_subclass_marshalling(self):
        self.patch(
            self.registry["res.users"],
            "context_get",
            odoo.api.model(lambda *_: ReadonlyDictSubclass({"lang": "en_US"})),
        )
        self.assertEqual(self.xmlrpc("res.users", "context_get"), {"lang": "en_US"})

    def test_xmlrpc_defaultdict_marshalling(self):
        self.patch(
            self.registry["res.users"],
            "context_get",
            odoo.api.model(lambda *_: collections.defaultdict(int)),
        )
        self.assertEqual(self.xmlrpc("res.users", "context_get"), {})

    def test_xmlrpc_remove_control_characters(self):
        record = self.env["res.users"].create(
            {
                "name": "bob with a control character: \x03",
                "login": "bob",
            }
        )
        self.assertEqual(record.name, "bob with a control character: \x03")
        [record_data] = self.xmlrpc("res.users", "read", record.id, ["name"])
        self.assertEqual(record_data["name"], "bob with a control character: ")

    def test_xmlrpc_attachment_raw(self):
        ids = self.env["ir.attachment"].create({"name": "n", "raw": b"\x01\x09"}).ids
        [att] = self.xmlrpc_object.execute(
            common.get_db_name(),
            self.admin_uid,
            self.admin_key,
            "ir.attachment",
            "read",
            ids,
            ["raw"],
        )
        self.assertEqual(
            att["raw"],
            "\t",
            "on read, binary data should be decoded as a string and stripped from control character",
        )


@common.tagged("post_install", "-at_install")
class TestAPIKeys(common.HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "0")
        cls._user = cls.env["res.users"].create(
            {
                "name": "Bylan",
                "login": "byl",
                "password": "ananananan",
                "tz": "Australia/Eucla",
            }
        )

    def setUp(self):
        super().setUp()

        def get_json_data():
            raise ValueError("There is no json here")

        self.http_request_key = self.canonical_tag
        fake_req = common.request_stand_in(
            httprequest=DotDict(
                {
                    "environ": {"REMOTE_ADDR": "localhost"},
                    "remote_addr": "localhost",
                    "cookies": {common.TEST_CURSOR_COOKIE_NAME: self.canonical_tag},
                    "args": {},
                }
            ),
            cookies={common.TEST_CURSOR_COOKIE_NAME: self.canonical_tag},
            session={"identity-check-last": time.time()},
            geoip={},
            get_json_data=get_json_data,
            call_after_release=lambda func: None,
        )
        _request_stack.push(fake_req)
        self.addCleanup(_request_stack.pop)

    def test_trivial(self):
        uid = auth.dispatch(
            "authenticate", [self.env.cr.dbname, "byl", "ananananan", {}]
        )
        self.assertEqual(uid, self._user.id)

        ctx = model.dispatch(
            "execute_kw",
            [self.env.cr.dbname, uid, "ananananan", "res.users", "context_get", []],
        )
        self.assertEqual(ctx["tz"], "Australia/Eucla")

    def test_wrongpw(self):
        uid = auth.dispatch("authenticate", [self.env.cr.dbname, "byl", "aws", {}])
        self.assertFalse(uid)
        with self.assertRaises(AccessDenied):
            model.dispatch(
                "execute_kw",
                [
                    self.env.cr.dbname,
                    self._user.id,
                    "aws",
                    "res.users",
                    "context_get",
                    [],
                ],
            )

    def test_key(self):
        env = self.env(user=self._user)
        r = (
            env["wizard.res.users.apikeys.create"]
            .create(
                {
                    "name": "a",
                }
            )
            .action_generate_key()
        )
        k = r["context"]["default_key"]

        uid = auth.dispatch(
            "authenticate", [self.env.cr.dbname, "byl", "ananananan", {}]
        )
        self.assertEqual(uid, self._user.id)

        uid = auth.dispatch("authenticate", [self.env.cr.dbname, "byl", k, {}])
        self.assertEqual(uid, self._user.id)

        ctx = model.dispatch(
            "execute_kw", [self.env.cr.dbname, uid, k, "res.users", "context_get", []]
        )
        self.assertEqual(ctx["tz"], "Australia/Eucla")

        api_key = model.call_kw(
            model=self.env["wizard.res.users.apikeys.create"],
            name="create",
            args=[{"name": "Name of the key"}],
            kwargs={},
        )
        self.assertTrue(isinstance(api_key, int))

    def test_delete(self):
        env = self.env(user=self._user)
        env["wizard.res.users.apikeys.create"].create(
            {
                "name": "b",
            }
        ).action_generate_key()
        env["wizard.res.users.apikeys.create"].create(
            {
                "name": "b",
            }
        ).action_generate_key()
        env["wizard.res.users.apikeys.create"].create(
            {
                "name": "b",
            }
        ).action_generate_key()
        k0, k1, k2 = env["res.users.apikeys"].search([])

        k0.remove()
        self.assertFalse(k0.exists())

        k1.with_user(self.env.ref("base.user_admin")).remove()
        self.assertFalse(k1.exists())

        u = self.env["res.users"].create(
            {
                "name": "a",
                "login": "a",
                "group_ids": self.env.ref("base.group_user").ids,
            }
        )
        with self.assertRaises(AccessError):
            k2.with_user(u).remove()

    def test_disabled(self):
        env = self.env(user=self._user)
        k = (
            env["wizard.res.users.apikeys.create"]
            .create(
                {
                    "name": "b",
                }
            )
            .action_generate_key()["context"]["default_key"]
        )

        self._user.active = False

        with self.assertRaises(AccessDenied):
            model.dispatch(
                "execute_kw",
                [
                    self.env.cr.dbname,
                    self._user.id,
                    "ananananan",
                    "res.users",
                    "context_get",
                    [],
                ],
            )

        with self.assertRaises(AccessDenied):
            model.dispatch(
                "execute_kw",
                [self.env.cr.dbname, self._user.id, k, "res.users", "context_get", []],
            )


class TestXmlrpcMarshalsFrozenList(common.BaseCase):
    def test_a_with_company_context_marshals_as_an_array(self):
        context = frozendict({"allowed_company_ids": FrozenList([1, 2])})
        dumped = OdooMarshaller(allow_none=True).dumps(({"context": context},))
        self.assertIn("<array><data>", dumped)
        self.assertIn("<int>2</int>", dumped)


@common.tagged("post_install", "-at_install")
class TestXmlrpcAuthentication(common.HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = common.new_test_user(
            cls.env, login="xmlrpc_target", password="xmlrpc-target-pw"
        )
        cls.key = common.new_test_api_key(cls.user)

    def setUp(self):
        super().setUp()
        for name in (
            "odoo.addons.rpc.controllers.xmlrpc",
            "odoo.addons.base.models.res_users",
            "odoo.http",
        ):
            muted = mute_logger(name)
            muted.__enter__()
            self.addCleanup(muted.__exit__)

    def _call(self, secret):
        return self.xmlrpc_object.execute_kw(
            common.get_db_name(), self.user.id, secret, "res.users", "context_get", []
        )

    def _authenticate(self, secret):
        return self.xmlrpc_common.authenticate(
            common.get_db_name(), "xmlrpc_target", secret, {}
        )

    def test_a_new_database_refuses_passwords_and_takes_keys(self):
        self.assertFalse(self._authenticate("xmlrpc-target-pw"))
        with self.assertRaises(xmlrpc.client.Fault):
            self._call("xmlrpc-target-pw")
        self.assertEqual(self._authenticate(self.key), self.user.id)
        self.assertEqual(self._call(self.key)["uid"], self.user.id)

    def test_wrong_passwords_cool_the_client_down(self):
        self.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "0")
        for _ in range(25):
            with self.assertRaisesRegex(xmlrpc.client.Fault, "Access Denied|Too many"):
                self._call("wrong-password")
        with self.assertRaisesRegex(xmlrpc.client.Fault, "Too many login failures"):
            self._call("xmlrpc-target-pw")
        self.assertFalse(self._authenticate("xmlrpc-target-pw"))

    def test_a_key_enters_from_a_cooled_address_and_a_wrong_one_is_counted(self):
        self.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "0")
        for _ in range(10):
            with self.assertRaisesRegex(xmlrpc.client.Fault, "Access Denied"):
                self._call("wrong-password")
        with self.assertRaisesRegex(xmlrpc.client.Fault, "Too many login failures"):
            self._call("xmlrpc-target-pw")
        self.assertEqual(self._call(self.key)["uid"], self.user.id)
        self.assertEqual(self._authenticate(self.key), self.user.id)
        self.assertEqual(self._failures(common.HOST), 11, "a key clears nothing")
        with self.assertRaisesRegex(xmlrpc.client.Fault, "Too many login failures"):
            self._call("0" * 40)
        self.assertEqual(self._failures(common.HOST), 12)
        self.assertEqual(self._failures(f"account:{self.user.id}"), 12)

    def _failures(self, source):
        self.env.cr.execute(
            "SELECT failures FROM res_users_login_cooldown WHERE source = %s",
            [source],
        )
        return self.env.cr.fetchone()[0]

    def test_an_unbound_key_still_opens_the_rpc_doors(self):
        unbound = common.new_unbound_test_api_key(self.user)
        self.assertEqual(self._authenticate(unbound), self.user.id)
        self.assertEqual(self._call(unbound)["uid"], self.user.id)
        response = self.url_open(
            "/json/2/res.users/context_get",
            json={},
            method="POST",
            headers={"Authorization": f"Bearer {unbound}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uid"], self.user.id)

    def test_a_key_bound_to_another_door_is_refused(self):
        declare_api_scope(self.env, "rpc.test_scope_other_door", "test_other_door")
        foreign = (
            self.env["res.users.apikeys"]
            .with_user(self.user)
            ._generate(
                "test_other_door",
                "k",
                datetime.datetime.now() + datetime.timedelta(hours=1),
            )
        )
        self.assertFalse(self._authenticate(foreign))
        with self.assertRaises(xmlrpc.client.Fault):
            self._call(foreign)
