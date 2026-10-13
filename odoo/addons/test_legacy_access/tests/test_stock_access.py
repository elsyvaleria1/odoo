from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.fields import Command, Domain
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.convert import convert_csv_import
from odoo.tools.safe_eval import safe_eval

from odoo.addons.base.models import ir_access_legacy

MODEL = "test_legacy_access.note"
MODULE = "test_legacy_access"
OPERATIONS = ("read", "write", "create", "unlink")

LINES = {
    "base.group_user": {"read"},
    "test_legacy_access.group_note_user": {"read", "write", "create"},
    "test_legacy_access.group_note_manager": {"read", "write", "create", "unlink"},
    "test_legacy_access.group_note_auditor": {"read"},
    "test_legacy_access.group_note_reader": {"read"},
}
GROUP_RULES = [
    (
        {"test_legacy_access.group_note_user", "test_legacy_access.group_note_auditor"},
        set(OPERATIONS),
        "[('user_id', '=', user.id)]",
    ),
    ({"test_legacy_access.group_note_manager"}, set(OPERATIONS), "[(1, '=', 1)]"),
    ({"base.group_user"}, {"read"}, "[('public', '=', True)]"),
]
GLOBAL_RULES = [(set(OPERATIONS), "[('state', '!=', 'cancel')]")]


@tagged("post_install", "-at_install")
class TestStockAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = {
            "plain": "base.group_user",
            "user": "base.group_user,test_legacy_access.group_note_user",
            "manager": "base.group_user,test_legacy_access.group_note_manager",
            "auditor": "base.group_user,test_legacy_access.group_note_auditor",
            "auditing_user": "base.group_user,test_legacy_access.group_note_user,"
            "test_legacy_access.group_note_auditor",
            "reader": "base.group_user,test_legacy_access.group_note_reader",
            "reading_user": "base.group_user,test_legacy_access.group_note_user,"
            "test_legacy_access.group_note_reader",
        }
        cls.users = {
            name: new_test_user(cls.env, login=f"stock_access_{name}", groups=spec)
            for name, spec in groups.items()
        }
        Note = cls.env[MODEL]
        cls.notes = Note
        for owner in (*cls.users.values(), cls.env.user):
            for public in (False, True):
                for state in ("draft", "cancel"):
                    cls.notes |= Note.create(
                        {
                            "name": f"{owner.login} {public} {state}",
                            "user_id": owner.id,
                            "public": public,
                            "state": state,
                        }
                    )

    def stock(self, user, operation):
        held = {
            xmlid
            for xmlid in (*LINES, *{g for gs, _o, _d in GROUP_RULES for g in gs})
            if self.env.ref(xmlid) in user.all_group_ids
        }
        if not any(operation in LINES[group] for group in held if group in LINES):
            return self.notes.browse()
        context = {"user": user.sudo(), "company_ids": user.company_ids.ids}
        grants = [
            Domain(safe_eval(domain, context))
            for groups, operations, domain in GROUP_RULES
            if operation in operations and groups & held
        ]
        domain = Domain.OR(grants) if grants else Domain.TRUE
        for operations, guard in GLOBAL_RULES:
            if operation in operations:
                domain &= Domain(safe_eval(guard, context))
        return self.notes.filtered_domain(domain)

    def reached(self, user, operation):
        notes = self.notes.with_user(user)
        if operation == "read":
            try:
                return notes.search([("id", "in", self.notes.ids)]).sudo()
            except AccessError:
                return self.notes.browse()
        return notes._filtered_access(operation).sudo()

    def test_every_user_reaches_what_stock_odoo_would_give(self):
        for name, user in self.users.items():
            for operation in OPERATIONS:
                with self.subTest(user=name, operation=operation):
                    self.assertEqual(
                        self.reached(user, operation), self.stock(user, operation)
                    )

    def test_a_rule_binds_its_members_whichever_line_opens_the_model(self):
        not_cancelled = self.notes.filtered(lambda n: n.state != "cancel")
        self.assertEqual(self.reached(self.users["manager"], "read"), not_cancelled)
        reached = self.reached(self.users["reading_user"], "read")
        self.assertTrue(reached)
        self.assertLess(reached, not_cancelled)

    def test_the_rows_carry_the_module_s_ids_and_its_noupdate(self):
        Data = self.env["ir.model.data"]
        own = self.env.ref(f"{MODULE}.rule_note_own_group_note_user")
        self.assertEqual(own._name, "ir.access")
        self.assertEqual(own.kind, "permission")
        guard = self.env.ref(f"{MODULE}.rule_note_not_cancelled")
        self.assertEqual((guard.kind, guard.guard_scope), ("guard", "everyone"))
        public = Data.search(
            [("module", "=", MODULE), ("name", "=", "rule_note_public")]
        )
        self.assertTrue(public.noupdate)
        self.assertFalse(
            Data.search(
                [
                    ("module", "=", MODULE),
                    ("name", "=", "rule_note_own_group_note_user"),
                ]
            ).noupdate
        )

    def test_an_update_keeps_the_noupdate_rows_and_restores_the_others(self):
        public = self.env.ref(f"{MODULE}.rule_note_public")
        own = self.env.ref(f"{MODULE}.rule_note_own_group_note_user")
        public.domain = "[('name', '=', 'kept by the administrator')]"
        own.domain = "[('name', '=', 'lost at the next update')]"
        self.env["ir.access"]._load_legacy_access(MODULE, "update")
        self.assertEqual(public.domain, "[('name', '=', 'kept by the administrator')]")
        self.assertEqual(own.domain, "[('user_id', '=', user.id)]")

    def test_the_drift_report_reads_the_stock_files_as_the_rows_desired_state(self):
        own = self.env.ref(f"{MODULE}.rule_note_own_group_note_user")
        public = self.env.ref(f"{MODULE}.rule_note_public")
        own.domain = "[('name', '=', 'edited')]"
        public.domain = "[('name', '=', 'kept by the administrator')]"

        found = self.env["ir.access.drift"]._get_findings_by_identity()

        states = {
            values["xmlid"]: values["state"]
            for values in found.values()
            if (values.get("xmlid") or "").startswith(f"{MODULE}.")
        }
        self.assertEqual(states, {f"{MODULE}.rule_note_own_group_note_user": "differs"})
        self.assertEqual(
            own.domain, "[('name', '=', 'edited')]", "the scan changes nothing"
        )

    def test_a_renamed_group_or_model_is_followed_and_a_removed_one_refused(self):
        Access = self.env["ir.access"]
        keys = Access._legacy_group_keys()
        source = {"file": "security/ir.model.access.csv", "id": "access_x"}
        with patch.dict(
            ir_access_legacy.LEGACY_GROUP_RENAMES, {"gone.group_x": "base.group_user"}
        ):
            self.assertEqual(
                Access._legacy_group(MODULE, "gone.group_x", source, keys),
                "base.group_user",
            )
        with patch.dict(ir_access_legacy.LEGACY_MODEL_RENAMES, {"gone.note": MODEL}):
            self.assertEqual(
                Access._legacy_model(
                    MODULE, {**source, "model_ref": "gone.model_gone_note"}
                ),
                MODEL,
            )
        with self.assertRaisesRegex(ValueError, "which this fork removed"):
            Access._legacy_group(
                MODULE, "purchase_requisition.group_purchase_alternatives", source, keys
            )
        with self.assertRaisesRegex(ValueError, "which this fork does not have"):
            Access._legacy_group(MODULE, "nowhere.group_x", source, keys)
        with self.assertRaisesRegex(ValueError, "which this fork does not have"):
            Access._legacy_model(MODULE, {**source, "model_ref": "nowhere.model_x"})

    def test_an_access_row_that_names_only_its_group_is_a_permission(self):
        convert_csv_import(
            self.env,
            MODULE,
            f"{MODULE}/security/ir.access.csv",
            b"id,name,model_id/id,group_id/id,operation\n"
            b"row_without_kind,no kind,model_test_legacy_access_note,base.group_user,r\n",
        )
        row = self.env.ref(f"{MODULE}.row_without_kind")
        self.assertEqual(row.kind, "permission")

    def test_the_sources_are_read_as_stock_odoo_reads_them(self):
        sources = ir_access_legacy.legacy_access_sources(MODULE)
        self.assertEqual(len(sources.lines), 5)
        rules = {rule["id"]: rule for rule in sources.rules}
        self.assertEqual(
            rules["rule_note_own"]["group_refs"],
            ["group_note_user", "group_note_auditor"],
        )
        self.assertTrue(rules["rule_note_not_cancelled"]["global"])
        self.assertTrue(rules["rule_note_public"]["noupdate"])
        self.assertEqual(
            [rules["rule_note_public"][perm] for perm in ir_access_legacy._PERMS],
            [True, False, False, False],
        )
        self.assertEqual(
            ir_access_legacy._group_refs(
                [Command.set(["a", "b"]), Command.unlink("a")]
            ),
            ["b"],
        )
