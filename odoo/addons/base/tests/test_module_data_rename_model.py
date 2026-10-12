from odoo.db.schema import column_exists, table_exists
from odoo.tests.common import TransactionCase, tagged
from odoo.tools.module_data import rename_model


@tagged("post_install", "-at_install")
class TestRenameModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_thing (id serial PRIMARY KEY, name varchar);
            ALTER TABLE probe_thing ADD CONSTRAINT probe_thing_name_uniq UNIQUE (name);
            CREATE TABLE probe_thing_member (
                id serial PRIMARY KEY,
                probe_thing_id int REFERENCES probe_thing (id),
                ref varchar
            );
            CREATE TABLE probe_thing_res_users_rel (
                probe_thing_id int REFERENCES probe_thing (id),
                res_users_id int
            );
            CREATE TABLE probe_log (res_model varchar);
            INSERT INTO probe_log VALUES ('probe.thing'), ('probe.thing.member');
            INSERT INTO ir_filters (name, model_id, sort, domain, context, active)
                 VALUES ('probe', 'probe.thing', '[]', '[]', '{}', true);
            INSERT INTO probe_thing_member (ref)
                 VALUES ('probe.thing,5'), ('probe.thing.member,5');
        """)
        cls.thing_model_id = cls._insert_model("probe.thing")
        cls.member_model_id = cls._insert_model("probe.thing.member")
        cls._insert_field(cls.thing_model_id, "probe.thing", "name", "char")
        cls._insert_field(
            cls.thing_model_id,
            "probe.thing",
            "user_ids",
            "many2many",
            relation="res.users",
            relation_table="probe_thing_res_users_rel",
            column1="probe_thing_id",
            column2="res_users_id",
        )
        cls._insert_field(
            cls.member_model_id,
            "probe.thing.member",
            "probe_thing_id",
            "many2one",
            relation="probe.thing",
        )
        cls._insert_field(cls.member_model_id, "probe.thing.member", "ref", "reference")
        cr.execute("SELECT id FROM ir_module_module WHERE name = 'base'")
        base_id = cr.fetchone()[0]
        for name, model_id in (
            ("probe_thing_name_uniq", cls.thing_model_id),
            ("probe_thing_member_ref_uniq", cls.member_model_id),
        ):
            cr.execute(
                "INSERT INTO ir_model_constraint (name, type, model, module) "
                "VALUES (%s, 'u', %s, %s)",
                (name, model_id, base_id),
            )
        for name, model, res_id in (
            ("model_probe_thing", "ir.model", cls.thing_model_id),
            ("model_probe_thing_member", "ir.model", cls.member_model_id),
        ):
            cr.execute(
                "INSERT INTO ir_model_data (module, name, model, res_id) "
                "VALUES ('test_rename', %s, %s, %s)",
                (name, model, res_id),
            )
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id)
            SELECT 'test_rename', 'field_' || replace(model, '.', '_') || '__' || name,
                   'ir.model.fields', id
              FROM ir_model_fields WHERE model LIKE 'probe.thing%'
        """)
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "probe",
                "model": "res.partner",
                "type": "search",
                "arch": """<search>
                    <filter name="a" string="a" context="{'m': 'probe.thing'}"/>
                    <filter name="b" string="b" context="{'m': 'probe.thing.member'}"/>
                </search>""",
            }
        )
        cls.qweb = cls.env["ir.ui.view"].create(
            {
                "name": "probe",
                "type": "qweb",
                "arch": '<t t-name="probe.quoted"><div data-oe-model="probe.thing"/>'
                '<div data-oe-model="probe.thing.member"/></t>',
            }
        )
        cls.env.flush_all()
        cls.relations = rename_model(cr, "probe.thing", "team.probe")

    @classmethod
    def _insert_model(cls, model):
        cls.env.cr.execute(
            'INSERT INTO ir_model (model, name, "order", state) '
            "VALUES (%s, %s, 'id', 'base') RETURNING id",
            (model, '{"en_US": "probe"}'),
        )
        return cls.env.cr.fetchone()[0]

    @classmethod
    def _insert_field(cls, model_id, model, name, ttype, **values):
        columns = [
            "model_id",
            "model",
            "name",
            "ttype",
            "state",
            "field_description",
            "store",
        ]
        params = [model_id, model, name, ttype, "base", '{"en_US": "probe"}', True]
        for column, value in values.items():
            columns.append(column)
            params.append(value)
        cls.env.cr.execute(
            "INSERT INTO ir_model_fields (%s) VALUES (%s)"
            % (", ".join(columns), ", ".join(["%s"] * len(params))),
            params,
        )

    def _scalar(self, query, params=()):
        self.env.cr.execute(query, params)
        return [row[0] for row in self.env.cr.fetchall()]

    def test_the_table_sequence_and_constraints_follow_the_model(self):
        self.assertTrue(table_exists(self.env.cr, "team_probe"))
        self.assertFalse(table_exists(self.env.cr, "probe_thing"))
        self.assertEqual(
            self._scalar(
                "SELECT sequencename FROM pg_sequences WHERE sequencename = %s",
                ("team_probe_id_seq",),
            ),
            ["team_probe_id_seq"],
        )
        self.assertIn(
            "team_probe_name_uniq",
            self._scalar(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'team_probe'::regclass"
            ),
        )

    def test_a_model_whose_table_merely_starts_with_the_old_one_is_untouched(self):
        self.assertTrue(table_exists(self.env.cr, "probe_thing_member"))
        self.assertEqual(
            self._scalar(
                "SELECT model FROM ir_model WHERE id = %s", (self.member_model_id,)
            ),
            ["probe.thing.member"],
        )
        self.assertEqual(
            sorted(
                self._scalar(
                    "SELECT name FROM ir_model_constraint WHERE model = ANY(%s)",
                    ([self.thing_model_id, self.member_model_id],),
                )
            ),
            ["probe_thing_member_ref_uniq", "team_probe_name_uniq"],
        )
        self.assertEqual(
            sorted(
                self._scalar(
                    "SELECT name FROM ir_model_data WHERE module = 'test_rename'"
                )
            ),
            [
                "field_probe_thing_member__probe_thing_id",
                "field_probe_thing_member__ref",
                "field_team_probe__name",
                "field_team_probe__user_ids",
                "model_probe_thing_member",
                "model_team_probe",
            ],
        )

    def test_a_derived_join_table_is_renamed_in_the_orms_sort_order(self):
        self.assertEqual(
            self.relations, {"probe_thing_res_users_rel": "res_users_team_probe_rel"}
        )
        self.assertTrue(
            column_exists(self.env.cr, "res_users_team_probe_rel", "team_probe_id")
        )
        self.env.cr.execute(
            "SELECT relation_table, column1, column2 FROM ir_model_fields "
            "WHERE model = 'team.probe' AND name = 'user_ids'"
        )
        self.assertEqual(
            self.env.cr.fetchone(),
            ("res_users_team_probe_rel", "team_probe_id", "res_users_id"),
        )

    def test_relations_model_name_columns_and_references_are_repointed(self):
        self.assertEqual(
            self._scalar(
                "SELECT relation FROM ir_model_fields "
                "WHERE model = 'probe.thing.member' AND name = 'probe_thing_id'"
            ),
            ["team.probe"],
        )
        self.assertEqual(
            sorted(self._scalar("SELECT res_model FROM probe_log")),
            ["probe.thing.member", "team.probe"],
        )
        self.assertEqual(
            sorted(self._scalar("SELECT ref FROM probe_thing_member")),
            ["probe.thing.member,5", "team.probe,5"],
        )

    def test_a_saved_filter_follows_the_model(self):
        self.assertEqual(
            self._scalar("SELECT model_id FROM ir_filters WHERE name = 'probe'"),
            ["team.probe"],
        )

    def test_a_quoted_model_name_is_rewritten_in_a_view_but_not_its_extension(self):
        self.view.invalidate_recordset(["arch_db"])
        arch = self.view.arch_db
        self.assertIn("'team.probe'", arch)
        self.assertIn("'probe.thing.member'", arch)
        self.assertNotIn("'probe.thing'", arch)

    def test_a_double_quoted_model_name_in_an_arch_follows(self):
        self.qweb.invalidate_recordset(["arch_db"])
        arch = self.qweb.arch_db
        self.assertIn('data-oe-model="team.probe"', arch)
        self.assertIn('data-oe-model="probe.thing.member"', arch)
        self.assertNotIn('"probe.thing"', arch)

    def test_renaming_again_changes_nothing(self):
        self.assertEqual(rename_model(self.env.cr, "probe.thing", "team.probe"), {})
        self.assertTrue(table_exists(self.env.cr, "team_probe"))


@tagged("post_install", "-at_install")
class TestRenameModelOverAForerunner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_gadget (id serial PRIMARY KEY, state varchar);
            INSERT INTO probe_gadget (state) VALUES ('kept');
            CREATE TABLE probe_widget (id serial PRIMARY KEY, state varchar);
        """)
        cls.old_id = TestRenameModel._insert_model.__func__(cls, "probe.gadget")
        cls.new_id = TestRenameModel._insert_model.__func__(cls, "probe.widget")
        insert_field = TestRenameModel._insert_field.__func__
        insert_field(cls, cls.old_id, "probe.gadget", "state", "selection")
        insert_field(cls, cls.new_id, "probe.widget", "state", "selection")
        insert_field(cls, cls.new_id, "probe.widget", "note", "char")
        cr.execute(
            "SELECT model, name, id FROM ir_model_fields "
            "WHERE model IN ('probe.gadget', 'probe.widget')"
        )
        cls.field_ids = {(model, name): id_ for model, name, id_ in cr.fetchall()}
        for field_id in (
            cls.field_ids["probe.gadget", "state"],
            cls.field_ids["probe.widget", "state"],
        ):
            cr.execute(
                "INSERT INTO ir_model_fields_selection "
                "(field_id, value, name, sequence) VALUES (%s, 'kept', %s, 1)",
                (field_id, '{"en_US": "Kept"}'),
            )
        cr.execute(
            "INSERT INTO ir_model_constraint (name, type, model, module) "
            "SELECT 'probe_widget_state_uniq', 'u', %s, id "
            "FROM ir_module_module WHERE name = 'base'",
            (cls.new_id,),
        )
        for module, name, model, res_id in (
            ("test_rename", "model_probe_gadget", "ir.model", cls.old_id),
            ("test_rename", "model_probe_widget", "ir.model", cls.new_id),
            ("test_rename_ext", "model_probe_widget", "ir.model", cls.new_id),
            (
                "test_rename",
                "field_probe_gadget__state",
                "ir.model.fields",
                cls.field_ids["probe.gadget", "state"],
            ),
            (
                "test_rename",
                "field_probe_widget__state",
                "ir.model.fields",
                cls.field_ids["probe.widget", "state"],
            ),
            (
                "test_rename",
                "field_probe_widget__note",
                "ir.model.fields",
                cls.field_ids["probe.widget", "note"],
            ),
        ):
            cr.execute(
                "INSERT INTO ir_model_data (module, name, model, res_id) "
                "VALUES (%s, %s, %s, %s)",
                (module, name, model, res_id),
            )
        cls.access = cls.env["ir.access"].create(
            {
                "name": "probe gadget",
                "model_id": cls.old_id,
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
            }
        )
        cls.env.flush_all()
        rename_model(cr, "probe.gadget", "probe.widget")

    def _one(self, query, params=()):
        self.env.cr.execute(query, params)
        return self.env.cr.fetchall()

    def test_the_old_model_keeps_its_id_its_data_and_what_references_it(self):
        self.assertEqual(
            self._one(
                "SELECT id FROM ir_model WHERE model IN ('probe.gadget', 'probe.widget')"
            ),
            [(self.old_id,)],
        )
        self.assertEqual(self._one("SELECT state FROM probe_widget"), [("kept",)])
        self.assertEqual(
            self._one(
                "SELECT model_id FROM ir_access WHERE id = %s", (self.access.id,)
            ),
            [(self.old_id,)],
        )

    def test_each_xmlid_ends_on_the_old_record_once(self):
        rows = self._one(
            "SELECT module, name, res_id FROM ir_model_data "
            "WHERE module LIKE 'test\\_rename%%' ORDER BY module, name"
        )
        state_id = self.field_ids["probe.gadget", "state"]
        note_id = self.field_ids["probe.widget", "note"]
        self.assertEqual(
            rows,
            [
                ("test_rename", "field_probe_widget__note", note_id),
                ("test_rename", "field_probe_widget__state", state_id),
                ("test_rename", "model_probe_widget", self.old_id),
                ("test_rename_ext", "model_probe_widget", self.old_id),
            ],
        )

    def test_a_field_only_the_forerunner_had_moves_onto_the_model(self):
        self.assertEqual(
            self._one(
                "SELECT name, model_id, model FROM ir_model_fields "
                "WHERE model = 'probe.widget' ORDER BY name"
            ),
            [
                ("note", self.old_id, "probe.widget"),
                ("state", self.old_id, "probe.widget"),
            ],
        )
        self.assertEqual(
            self._one(
                "SELECT field_id FROM ir_model_fields_selection WHERE value = 'kept' "
                "AND field_id IN (SELECT id FROM ir_model_fields WHERE model = 'probe.widget')"
            ),
            [(self.field_ids["probe.gadget", "state"],)],
        )

    def test_the_forerunner_s_constraint_on_its_dropped_table_goes(self):
        self.assertFalse(
            self._one(
                "SELECT 1 FROM ir_model_constraint WHERE name = 'probe_widget_state_uniq'"
            )
        )

    def test_a_forerunner_table_holding_rows_is_refused(self):
        cr = self.env.cr
        cr.execute("""
            CREATE TABLE probe_thing2 (id serial PRIMARY KEY);
            CREATE TABLE probe_gizmo (id serial PRIMARY KEY);
            INSERT INTO probe_gizmo DEFAULT VALUES;
        """)
        TestRenameModel._insert_model.__func__(type(self), "probe.thing2")
        TestRenameModel._insert_model.__func__(type(self), "probe.gizmo")
        with self.assertRaisesRegex(ValueError, "holds rows"):
            rename_model(cr, "probe.thing2", "probe.gizmo")


@tagged("post_install", "-at_install")
class TestRenameModelOverlongRelation(TransactionCase):
    LONG = "probe.short.renamed.with.a.name.long.enough.to.overflow"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_short (id serial PRIMARY KEY);
            CREATE TABLE probe_short_res_users_rel (
                probe_short_id int REFERENCES probe_short (id),
                res_users_id int
            );
        """)
        cr.execute(
            'INSERT INTO ir_model (model, name, "order", state) '
            "VALUES ('probe.short', '{\"en_US\": \"probe\"}', 'id', 'base') RETURNING id"
        )
        model_id = cr.fetchone()[0]
        cr.execute(
            "INSERT INTO ir_model_fields (model_id, model, name, ttype, state, "
            "field_description, store, relation, relation_table, column1, column2) "
            "VALUES (%s, 'probe.short', 'user_ids', 'many2many', 'base', "
            "'{\"en_US\": \"probe\"}', true, 'res.users', "
            "'probe_short_res_users_rel', 'probe_short_id', 'res_users_id')",
            (model_id,),
        )
        cls.relations = rename_model(cr, "probe.short", cls.LONG)

    def test_the_join_table_keeps_its_name_and_its_column_follows(self):
        new_table = self.LONG.replace(".", "_")
        self.assertGreater(len(f"{new_table}_res_users_rel"), 63)
        self.assertEqual(self.relations, {})
        self.assertTrue(table_exists(self.env.cr, "probe_short_res_users_rel"))
        self.assertTrue(
            column_exists(self.env.cr, "probe_short_res_users_rel", f"{new_table}_id")
        )
        self.env.cr.execute(
            "SELECT relation_table, column1 FROM ir_model_fields "
            "WHERE model = %s AND name = 'user_ids'",
            (self.LONG,),
        )
        self.assertEqual(
            self.env.cr.fetchone(), ("probe_short_res_users_rel", f"{new_table}_id")
        )

    def test_constraints_that_would_outgrow_the_limit_keep_their_columns(self):
        cr = self.env.cr
        cr.execute("""
            CREATE TABLE probe_cons (
                id serial PRIMARY KEY,
                a_rather_long_column_name_one int NOT NULL,
                a_rather_long_column_name_two int NOT NULL
            )
        """)
        new = "probe.cons.renamed.to.a.name.long.enough.to.overflow.limit"
        rename_model(cr, "probe.cons", new)
        table = new.replace(".", "_")
        cr.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass "
            "AND contype = 'n' ORDER BY conname",
            (table,),
        )
        names = [row[0] for row in cr.fetchall() if "rather_long" in row[0]]
        self.assertEqual(len(names), 2)
        self.assertTrue(all(len(name) <= 63 for name in names), names)
        self.assertTrue(names[0].endswith("_a_rather_long_column_name_one_not_null"))
        self.assertTrue(names[1].endswith("_a_rather_long_column_name_two_not_null"))
        cr.execute(
            "SELECT sequencename FROM pg_sequences WHERE sequencename LIKE 'probe_cons%'"
        )
        (sequence,) = cr.fetchone()
        self.assertTrue(sequence.endswith("_id_seq") and len(sequence) <= 63, sequence)

    def test_a_shortened_name_never_takes_the_name_another_one_fits_in(self):
        cr = self.env.cr
        cr.execute("""
            CREATE TABLE probe_col (
                id serial PRIMARY KEY,
                automation_id int NOT NULL
            )
        """)
        new = "probe.collide." + "x" * 26 + ".automation"
        table = new.replace(".", "_")
        self.assertEqual(len(table), 51)
        rename_model(cr, "probe.col", new)
        cr.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass "
            "AND contype = 'n'",
            (table,),
        )
        names = {row[0] for row in cr.fetchall()}
        self.assertIn(f"{table}_id_not_null", names)
        self.assertEqual(len(names), 2, names)


@tagged("post_install", "-at_install")
class TestRenameModelLongJoinTable(TransactionCase):
    OLD = "probe.join.table.with.a.rather.long.name.xy"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cls.old_table = cls.OLD.replace(".", "_")
        cls.old_join = f"{cls.old_table}_res_users_rel"
        cr.execute(f"""
            CREATE TABLE {cls.old_table} (id serial PRIMARY KEY);
            CREATE TABLE {cls.old_join} (
                {cls.old_table}_id int REFERENCES {cls.old_table} (id),
                res_users_id int
            );
        """)
        cr.execute(
            'INSERT INTO ir_model (model, name, "order", state) '
            "VALUES (%s, '{\"en_US\": \"probe\"}', 'id', 'base') RETURNING id",
            (cls.OLD,),
        )
        model_id = cr.fetchone()[0]
        cr.execute(
            "INSERT INTO ir_model_fields (model_id, model, name, ttype, state, "
            "field_description, store, relation, relation_table, column1, column2) "
            "VALUES (%s, %s, 'user_ids', 'many2many', 'base', "
            "'{\"en_US\": \"probe\"}', true, 'res.users', %s, %s, 'res_users_id')",
            (model_id, cls.OLD, cls.old_join, f"{cls.old_table}_id"),
        )
        cls.relations = rename_model(cr, cls.OLD, "probe.join")

    def test_the_join_table_moves_and_owns_no_sequence(self):
        self.assertGreater(len(f"{self.old_join}_id_seq"), 63)
        self.assertLessEqual(len(self.old_join), 63)
        self.assertEqual(self.relations, {self.old_join: "probe_join_res_users_rel"})
        self.assertTrue(table_exists(self.env.cr, "probe_join_res_users_rel"))
        self.assertFalse(table_exists(self.env.cr, self.old_join))

    def test_the_model_table_takes_its_sequence_along(self):
        self.env.cr.execute("SELECT pg_get_serial_sequence('probe_join', 'id')")
        self.assertEqual(self.env.cr.fetchone()[0], "public.probe_join_id_seq")


@tagged("post_install", "-at_install")
class TestRenameModelJoinTableWithAnActionComodel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_doohickey (id serial PRIMARY KEY);
            CREATE TABLE ir_act_server_probe_doohickey_rel (
                probe_doohickey_id int REFERENCES probe_doohickey (id),
                ir_act_server_id int
            );
        """)
        model_id = TestRenameModel._insert_model.__func__(cls, "probe.doohickey")
        TestRenameModel._insert_field.__func__(
            cls,
            model_id,
            "probe.doohickey",
            "action_ids",
            "many2many",
            relation="ir.actions.server",
            relation_table="ir_act_server_probe_doohickey_rel",
            column1="probe_doohickey_id",
            column2="ir_act_server_id",
        )
        cls.relations = rename_model(cr, "probe.doohickey", "probe.gadget2")

    def test_the_join_table_moves_where_the_orm_looks_for_it(self):
        self.assertEqual(
            self.relations,
            {"ir_act_server_probe_doohickey_rel": "ir_act_server_probe_gadget2_rel"},
        )
        self.assertTrue(
            column_exists(
                self.env.cr, "ir_act_server_probe_gadget2_rel", "probe_gadget2_id"
            )
        )
