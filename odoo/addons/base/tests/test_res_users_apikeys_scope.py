import time
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.fields import Command
from odoo.service import api_scope
from odoo.service.model import call_kw
from odoo.tests import tagged
from odoo.tests.common import (
    TransactionCase,
    new_test_user,
    new_unbound_test_api_key,
)

from odoo.addons.base.tests.common import declare_api_scope


class ScopeCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="scope_probe", groups="base.group_user")
        partner_model = cls.env["ir.model"]._get("res.partner")
        fields_ = cls.env["ir.model.fields"].search(
            [("model_id", "=", partner_model.id), ("name", "in", ("vat", "email"))]
        )
        cls.scope = cls.env["res.users.apikeys.scope"].create(
            {
                "name": "Probe",
                "key": "probe",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "model_id": partner_model.id,
                            "allow_read": True,
                            "allow_create": True,
                            "allow_write": True,
                            "denied_field_ids": [(6, 0, fields_.ids)],
                        },
                    )
                ],
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Oracle Probe", "vat": "LEAKED-ORACLE-1", "email": "p@x.mx"}
        )
        cls.child = cls.env["res.partner"].create(
            {"name": "Oracle Child", "parent_id": cls.partner.id}
        )

    def _call(self, method, *args, model="res.partner", **kwargs):
        records = (
            self.env[model]
            .with_user(self.user)
            .with_context(api_scope_id=self.scope.id)
        )
        return call_kw(records, method, list(args), kwargs)


@tagged("post_install", "-at_install")
class TestScopeReach(ScopeCase):
    def test_a_model_the_scope_does_not_name_is_refused(self):
        with self.assertRaisesRegex(AccessError, "does not reach 'res.users'"):
            self._call("search_read", [], ["login"], model="res.users")

    def test_an_operation_the_scope_withholds_is_refused(self):
        with self.assertRaisesRegex(AccessError, "does not allow unlink"):
            self._call("unlink", [self.child.id])
        with self.assertRaisesRegex(AccessError, "does not allow call"):
            self._call("onchange", [self.child.id], {}, [], {})

    def test_a_scope_with_no_line_reaches_everything(self):
        everything = self.env["res.users.apikeys.scope"].create(
            {"name": "All", "key": "probe_all"}
        )
        records = (
            self.env["res.users"]
            .with_user(self.user)
            .with_context(api_scope_id=everything.id)
        )
        rows = call_kw(
            records, "search_read", [[("id", "=", self.user.id)]], {"fields": ["login"]}
        )
        self.assertEqual(rows[0]["login"], "scope_probe")

    def test_a_scope_closed_when_empty_reaches_nothing_until_a_line_names_a_model(
        self,
    ):
        closed = self.env["res.users.apikeys.scope"].create(
            {"name": "Closed", "key": "probe_closed", "closed_when_empty": True}
        )
        records = (
            self.env["res.users"]
            .with_user(self.user)
            .with_context(api_scope_id=closed.id)
        )
        self.assertEqual(closed._rules().models, {})
        with self.assertRaisesRegex(AccessError, "does not reach 'res.users'"):
            call_kw(records, "search_read", [[]], {"fields": ["login"]})

        closed.line_ids = [
            (0, 0, {"model_id": self.env["ir.model"]._get_id("res.users")})
        ]
        rows = call_kw(
            records, "search_read", [[("id", "=", self.user.id)]], {"fields": ["login"]}
        )
        self.assertEqual(rows[0]["login"], "scope_probe")

    def test_no_scope_leaves_call_kw_untouched(self):
        rows = call_kw(
            self.env["res.partner"].with_user(self.user),
            "read",
            [[self.partner.id]],
            {"fields": ["vat"]},
        )
        self.assertEqual(rows[0]["vat"], "LEAKED-ORACLE-1")


@tagged("post_install", "-at_install")
class TestHiddenColumns(ScopeCase):
    def test_a_named_hidden_field_is_refused(self):
        with self.assertRaisesRegex(
            UserError, "vat \\(on res.partner\\) is not available"
        ):
            self._call("read", [self.partner.id], fields=["name", "vat"])

    def test_read_without_a_field_list_strips_hidden_fields(self):
        rows = self._call("read", [self.partner.id])
        self.assertNotIn("vat", rows[0])
        self.assertNotIn("email", rows[0])
        self.assertEqual(rows[0]["name"], "Oracle Probe")

    def test_a_domain_a_sort_and_a_grouping_on_a_hidden_field_are_refused(self):
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("search_read", [("vat", "=", "LEAKED-ORACLE-1")])
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("search", [], order="vat")
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("read_group", [], ["id:count"], ["email"])

    def test_writing_a_hidden_field_is_refused(self):
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("write", [self.child.id], {"vat": "X"})
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("create", {"name": "N", "email": "n@x.mx"})

    def test_an_x2many_create_command_cannot_write_a_hidden_column(self):
        with self.assertRaisesRegex(UserError, "not available"):
            self._call(
                "write",
                [self.partner.id],
                {"child_ids": [[0, 0, {"name": "C", "vat": "X"}]]},
            )

    def test_a_dotted_domain_cannot_read_a_hidden_column(self):
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("search_count", [("parent_id.vat", "=", "LEAKED-ORACLE-1")])

    def test_an_any_domain_is_walked_to_the_bottom(self):
        with self.assertRaisesRegex(UserError, "not available"):
            self._call("search_count", [("child_ids", "any", [("email", "=", "x")])])

    def test_a_path_past_the_depth_cap_is_refused_not_truncated(self):
        self.scope.max_depth = 2
        with self.assertRaisesRegex(UserError, "may not cross more than 2"):
            self._call(
                "search_count", [("parent_id.parent_id.parent_id.name", "=", "x")]
            )

    def test_fields_get_does_not_describe_a_hidden_column(self):
        described = self._call("fields_get")
        self.assertIn("name", described)
        self.assertNotIn("vat", described)

    def test_a_visible_field_still_works(self):
        rows = self._call("search_read", [("id", "=", self.partner.id)], ["name"])
        self.assertEqual(rows, [{"id": self.partner.id, "name": "Oracle Probe"}])


@tagged("post_install", "-at_install")
class TestHiddenColumnOracles(ScopeCase):
    def test_name_search_no_longer_matches_the_hidden_column(self):
        self.assertEqual(self._call("name_search", "LEAKED-ORACLE"), [])

    def test_name_search_still_matches_the_visible_columns(self):
        found = self._call("name_search", "Oracle Probe")
        self.assertIn(self.partner.id, [row[0] for row in found])

    def test_a_display_name_condition_does_not_reach_the_hidden_column(self):
        self.assertEqual(
            self._call("search_count", [("display_name", "ilike", "LEAKED-ORACLE")]), 0
        )

    def test_a_many2one_string_operator_does_not_reach_the_hidden_column(self):
        self.assertEqual(
            self._call("search_count", [("parent_id", "ilike", "LEAKED-ORACLE")]), 0
        )
        self.assertEqual(
            self._call("search_count", [("parent_id", "ilike", "Oracle Probe")]), 1
        )

    def test_the_client_context_cannot_switch_the_enforcement_off(self):
        rows = self._call(
            "read",
            [self.partner.id],
            fields=["display_name"],
            context={"api_scope_id": False, "show_vat": True},
        )
        self.assertEqual(rows[0]["display_name"], "Oracle Probe")
        self.assertEqual(
            self._call(
                "search_count",
                [("display_name", "ilike", "LEAKED-ORACLE")],
                context={"show_vat": True},
            ),
            0,
        )

    def test_the_orm_is_untouched_outside_a_scoped_call(self):
        self.assertIsNone(api_scope.active_rules())
        found = self.env["res.partner"].name_search("LEAKED-ORACLE")
        self.assertIn(self.partner.id, [row[0] for row in found])


@tagged("post_install", "-at_install")
class TestComputedDerivationsAreHidden(ScopeCase):
    def _hidden(self, model):
        return api_scope.hidden_field_names(self.env, self.scope._rules(), model)

    def test_a_computed_field_that_prints_the_column_is_hidden_with_it(self):
        self.assertIn("email_formatted", self._hidden("res.partner"))

    def test_a_computed_field_that_answers_about_the_column_is_hidden_with_it(self):
        self.assertIn("same_vat_partner_id", self._hidden("res.partner"))

    def test_the_label_is_never_hidden(self):
        hidden = self._hidden("res.partner")
        self.assertNotIn("display_name", hidden)
        self.assertNotIn("name", hidden)

    def test_the_closure_crosses_a_relation_into_a_model_the_scope_names_not(self):
        self.assertIn("email", self._hidden("res.users"))
        self.assertIn("email_formatted", self._hidden("res.users"))

    def test_the_closure_is_one_pass_over_the_registry(self):
        rules = self.scope._rules()
        started = time.monotonic()
        self._hidden("res.partner")
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertIn("res.users", rules._hidden, "every model, in the one pass")
        started = time.monotonic()
        self._hidden("res.company")
        self.assertLess(
            time.monotonic() - started, 0.01, "the second model is a lookup"
        )

    def test_the_rules_follow_a_write(self):
        before = self.scope._rules()
        self.scope.line_ids.write({"denied_field_ids": [(5, 0, 0)]})
        after = self.scope._rules()
        self.assertNotEqual(before, after)
        self.assertEqual(after.denied("res.partner"), frozenset())


@tagged("post_install", "-at_install")
class TestHiddenClasses(TransactionCase):
    def setUp(self):
        super().setUp()
        self.patch(
            self.env["res.users"]._fields["login"], "groups", "base.group_system"
        )
        self.self_fields = {
            name
            for name, field in self.env["res.users"]._fields.items()
            if field.access_classes is not None
            and "base.user_self" in field.access_classes.read_alternative
        }
        self.user_self = self.env.ref("base.access_class_user_self")

    def _hidden(self, scope, model):
        return api_scope.hidden_field_names(self.env, scope._rules(), model)

    def test_the_rows_say_there_are_fields_to_hide(self):
        self.assertIn("login", self.self_fields)

    def test_a_scope_hides_a_class_on_every_model_it_reaches(self):
        scope = self.env["res.users.apikeys.scope"].create(
            {
                "name": "No self fields",
                "key": "no_self_fields",
                "denied_class_ids": [Command.link(self.user_self.id)],
            }
        )
        self.assertLessEqual(self.self_fields, self._hidden(scope, "res.users"))
        self.assertFalse(self._hidden(scope, "res.partner") & {"name", "email"})

    def test_a_line_hides_a_class_on_its_model(self):
        users = self.env["ir.model"]._get("res.users")
        scope = self.env["res.users.apikeys.scope"].create(
            {
                "name": "Users without self fields",
                "key": "users_no_self_fields",
                "line_ids": [
                    Command.create(
                        {
                            "model_id": users.id,
                            "denied_class_ids": [Command.link(self.user_self.id)],
                        }
                    )
                ],
            }
        )
        self.assertLessEqual(self.self_fields, self._hidden(scope, "res.users"))

    def test_a_scope_that_hides_no_class_hides_nothing(self):
        scope = self.env["res.users.apikeys.scope"].create(
            {"name": "Open", "key": "open_classes"}
        )
        self.assertFalse(self._hidden(scope, "res.users"))


@tagged("post_install", "-at_install")
class TestUnknownFieldsAreTheCallersMistake(ScopeCase):
    def test_a_close_match_is_suggested(self):
        with self.assertRaisesRegex(UserError, "did you mean 'name'"):
            self._call("search_read", [], ["nmae"])

    def test_a_reordered_name_is_suggested_first(self):
        with self.assertRaisesRegex(UserError, "did you mean 'email_formatted'"):
            self._call("search_read", [("formatted_email", "=", "x")])

    def test_sorting_across_a_relation_is_a_caller_error(self):
        with self.assertRaisesRegex(UserError, "sorting across a relation"):
            self._call("search", [], order="parent_id.name")

    def test_a_malformed_domain_is_a_caller_error(self):
        with self.assertRaisesRegex(UserError, "Malformed domain"):
            self._call("search_count", [["name"]])


@tagged("post_install", "-at_install")
class TestKeysAndScopes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rpc = cls.env.ref("base.apikeys_scope_rpc")
        cls.other_door = declare_api_scope(
            cls.env, "base.test_scope_other_door", "other_door"
        )
        cls.user = new_test_user(
            cls.env, login="scope_key_user", groups="base.group_user"
        )
        cls.keys = cls.env["res.users.apikeys"].with_user(cls.user)
        cls.env["ir.config_parameter"].sudo().set_param("base.rpc_api_key_only", "0")

    def _generate(self, scope):
        return self.keys._generate(
            scope, "k", fields.Datetime.now() + timedelta(hours=1)
        )

    def test_a_key_bound_to_a_scope_opens_that_door_alone(self):
        bound = self._generate("rpc")
        other = self._generate("other_door")
        check = self.keys._check_credentials
        self.assertEqual(check(scope="rpc", key=bound), self.user.id)
        self.assertIsNone(check(scope="other_door", key=bound))
        self.assertEqual(check(scope="other_door", key=other), self.user.id)
        self.assertIsNone(check(scope="rpc", key=other))

    def test_an_unbound_key_opens_the_rpc_door_alone(self):
        unbound = new_unbound_test_api_key(self.user)
        check = self.keys._check_credentials
        self.assertIsNone(check(scope="other_door", key=unbound))
        self.assertEqual(check(scope="rpc", key=unbound), self.user.id)

    def test_every_key_is_minted_for_a_door(self):
        with self.assertRaises(UserError):
            self._generate(None)
        with self.assertRaises(UserError):
            self._generate("")

    def test_a_key_bound_to_an_archived_scope_opens_nothing(self):
        key = self._generate("other_door")
        self.assertEqual(
            self.keys._check_credentials(scope="other_door", key=key), self.user.id
        )
        self.other_door.action_archive()
        self.assertIsNone(self.keys._check_credentials(scope="other_door", key=key))

    def test_an_archived_rpc_scope_closes_the_rpc_door_to_every_key(self):
        bound = self._generate("rpc")
        unbound = new_unbound_test_api_key(self.user)
        self.rpc.action_archive()
        Users = self.env["res.users"]
        for key in (bound, unbound):
            with self.assertRaises(AccessDenied):
                Users._check_uid_passwd(self.user.id, key)
        self.assertIsNone(Users._check_uid_passwd(self.user.id, "scope_key_user"))

    def test_a_key_bound_to_another_door_is_refused_at_the_rpc_door(self):
        key = self._generate("other_door")
        with self.assertRaises(AccessDenied):
            self.env["res.users"]._check_uid_passwd(self.user.id, key)
        with self.assertRaises(AccessDenied):
            self.env["res.users"]._login(
                {"login": "scope_key_user", "password": key, "type": "password"},
                {"interactive": False},
            )

    def test_an_unbound_key_enters_the_rpc_door_under_rpc(self):
        key = new_unbound_test_api_key(self.user)
        self.assertEqual(
            self.env["res.users"]._check_uid_passwd(self.user.id, key), self.rpc.id
        )
        auth = self.env["res.users"]._login(
            {"login": "scope_key_user", "password": key, "type": "password"},
            {"interactive": False},
        )
        self.assertEqual(
            (auth["uid"], auth["api_scope_id"]), (self.user.id, self.rpc.id)
        )

    def test_a_scope_name_no_module_declares_mints_nothing(self):
        Scope = self.env["res.users.apikeys.scope"]
        with self.assertRaisesRegex(UserError, "never_seen"):
            self._generate("never_seen")
        with self.assertRaisesRegex(UserError, "never_seen"):
            self.keys._check_credentials(scope="never_seen", key="0" * 40)
        with self.assertRaisesRegex(UserError, "never_seen"):
            Scope._get_declared("never_seen")
        self.assertFalse(
            Scope.with_context(active_test=False).search([("key", "=", "never_seen")])
        )

    def test_a_row_no_module_declares_opens_no_door(self):
        key = self._generate("other_door")
        self.env["ir.model.data"].search(
            [("module", "=", "base"), ("name", "=", "test_scope_other_door")]
        ).unlink()
        self.env.registry.clear_cache()
        with self.assertRaisesRegex(UserError, "other_door"):
            self.keys._check_credentials(scope="other_door", key=key)
        with self.assertRaisesRegex(UserError, "other_door"):
            self._generate("other_door")
        with self.assertRaises(AccessDenied):
            self.env["res.users"]._check_uid_passwd(self.user.id, key)

    def test_a_scope_keeps_its_key(self):
        with self.assertRaisesRegex(UserError, "key"):
            self.other_door.key = "renamed_door"
        self.other_door.write({"key": "other_door", "name": "Same door"})

    def test_no_key_is_issued_for_an_archived_scope(self):
        self.other_door.action_archive()
        with self.assertRaisesRegex(UserError, "other_door"):
            self._generate("other_door")

    def test_the_rpc_password_check_names_the_rpc_scope_for_a_key(self):
        key = self._generate("rpc")
        Users = self.env["res.users"]
        self.assertEqual(Users._check_uid_passwd(self.user.id, key), self.rpc.id)
        self.assertIsNone(Users._check_uid_passwd(self.user.id, "scope_key_user"))

    def test_a_user_without_a_password_still_enters_rpc_with_a_key(self):
        key = self._generate("rpc")
        self.user._clear_password()
        self.env.flush_all()
        Users = self.env["res.users"]
        self.assertEqual(Users._check_uid_passwd(self.user.id, key), self.rpc.id)
        with self.assertRaises(AccessDenied):
            Users._check_uid_passwd(self.user.id, "anything")


@tagged("post_install", "-at_install")
class TestScopeRecords(TransactionCase):
    def test_a_data_record_adopts_the_row_a_migration_made_for_its_key(self):
        Scope = self.env["res.users.apikeys.scope"]
        made = Scope.create(
            {"name": "door.described.later", "key": "door.described.later"}
        )
        with self.assertRaises(UserError):
            Scope._get_declared("door.described.later")

        described, other = Scope._load_records(
            [
                {
                    "xml_id": "base.test_scope_described",
                    "values": {
                        "name": "Described",
                        "key": "door.described.later",
                        "max_depth": 3,
                    },
                },
                {
                    "xml_id": "base.test_scope_other",
                    "values": {"name": "Other", "key": "door.other"},
                },
            ]
        )

        self.assertEqual(described, made, "the same row, in the caller's order")
        self.assertEqual((described.name, described.max_depth), ("Described", 3))
        self.assertEqual(other.key, "door.other")
        self.assertEqual(Scope.search_count([("key", "=", "door.described.later")]), 1)
        self.assertEqual(Scope._get_declared("door.described.later"), described)

    def test_a_door_only_scope_reaches_no_model_at_the_universal_door(self):
        Scope = self.env["res.users.apikeys.scope"]
        door = Scope.create({"name": "Door", "key": "door.only", "door_only": True})
        self.assertIsNone(door._rules().rule("res.partner"))
        with self.assertRaises(AccessError):
            call_kw(
                self.env["res.partner"].with_context(api_scope_id=door.id),
                "search_count",
                [[]],
                {},
            )
        door.door_only = False
        self.assertIsNotNone(door._rules().rule("res.partner"), "every model again")
