from odoo.tests import counting_statements
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import module_data
from odoo.tools.module_data import rename_field, selection_xmlid


@tagged("post_install", "-at_install")
class TestRenameFieldCarriesNamedObjects(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_asset (id serial PRIMARY KEY, lot_id int);
            CREATE INDEX probe_asset__lot_id_index ON probe_asset (lot_id);
            ALTER TABLE probe_asset
              ADD CONSTRAINT probe_asset_lot_id_fkey
              FOREIGN KEY (lot_id) REFERENCES res_users (id);
            CREATE TABLE probe_asset_room () INHERITS (probe_asset);
            CREATE INDEX probe_asset_room__lot_id_index ON probe_asset_room (lot_id);
            ALTER TABLE probe_asset_room
              ADD CONSTRAINT probe_asset_room_lot_id_fkey
              FOREIGN KEY (lot_id) REFERENCES res_users (id);
        """)
        cr.execute("SELECT id FROM ir_module_module WHERE name = 'base'")
        base_id = cr.fetchone()[0]
        for model in ("probe.asset", "probe.asset.room"):
            cr.execute(
                'INSERT INTO ir_model (model, name, "order", state) '
                "VALUES (%s, %s, 'id', 'base') RETURNING id",
                (model, '{"en_US": "probe"}'),
            )
            model_id = cr.fetchone()[0]
            cr.execute(
                "INSERT INTO ir_model_fields"
                " (model_id, model, name, ttype, relation, state, field_description, store)"
                " VALUES (%s, %s, 'lot_id', 'many2one', 'res.users', 'base', %s, true)",
                (model_id, model, '{"en_US": "probe"}'),
            )
            cr.execute(
                "INSERT INTO ir_model_constraint (name, type, model, module)"
                " VALUES (%s, 'f', %s, %s)",
                (f"{model.replace('.', '_')}_lot_id_fkey", model_id, base_id),
            )
        rename_field(cr, "probe.asset", "lot_id", "trace_id")
        rename_field(cr, "probe.asset.room", "lot_id", "trace_id")

    def _names(self, query, params):
        self.env.cr.execute(query, params)
        return sorted(row[0] for row in self.env.cr.fetchall())

    def _indexes(self, table):
        return self._names(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s", (table,)
        )

    def _foreign_keys(self, table):
        return self._names(
            "SELECT conname FROM pg_constraint"
            " WHERE conrelid = %s::regclass AND contype = 'f'",
            (table,),
        )

    def test_the_index_and_foreign_key_follow_the_column(self):
        self.assertIn("probe_asset__trace_id_index", self._indexes("probe_asset"))
        self.assertNotIn("probe_asset__lot_id_index", self._indexes("probe_asset"))
        self.assertEqual(
            self._foreign_keys("probe_asset"), ["probe_asset_trace_id_fkey"]
        )

    def test_a_table_inheriting_the_column_renames_its_own_objects(self):
        indexes = self._indexes("probe_asset_room")
        self.assertIn("probe_asset_room__trace_id_index", indexes)
        self.assertNotIn("probe_asset_room__lot_id_index", indexes)
        self.assertEqual(
            self._foreign_keys("probe_asset_room"), ["probe_asset_room_trace_id_fkey"]
        )

    def test_the_foreign_key_reflection_rows_follow(self):
        self.assertEqual(
            self._names(
                "SELECT name FROM ir_model_constraint WHERE name LIKE %s",
                ("probe_asset%",),
            ),
            ["probe_asset_room_trace_id_fkey", "probe_asset_trace_id_fkey"],
        )


@tagged("post_install", "-at_install")
class TestRenameFieldIntoAColumnAlreadyThere(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_plan (
                id serial PRIMARY KEY,
                interval_type varchar NOT NULL,
                repeat_unit varchar NOT NULL DEFAULT 'week'
            );
            INSERT INTO probe_plan (interval_type) VALUES ('month'), ('year');
        """)
        cr.execute(
            'INSERT INTO ir_model (model, name, "order", state) '
            "VALUES ('probe.plan', '{\"en_US\": \"probe\"}', 'id', 'base') RETURNING id"
        )
        model_id = cr.fetchone()[0]
        field_ids = {}
        for name in ("interval_type", "repeat_unit"):
            cr.execute(
                "INSERT INTO ir_model_fields"
                " (model_id, model, name, ttype, state, field_description, store)"
                " VALUES (%s, 'probe.plan', %s, 'char', 'base', %s, true) RETURNING id",
                (model_id, name, '{"en_US": "probe"}'),
            )
            field_ids[name] = cr.fetchone()[0]
        cls.old_field_id, cls.new_field_id = (
            field_ids["interval_type"],
            field_ids["repeat_unit"],
        )
        cr.execute("""
            CREATE TABLE probe_tracking (
                id serial PRIMARY KEY,
                field_id int REFERENCES ir_model_fields (id) ON DELETE CASCADE
            )
        """)
        cr.execute(
            "INSERT INTO probe_tracking (field_id) VALUES (%s)", (cls.old_field_id,)
        )
        rename_field(cr, "probe.plan", "interval_type", "repeat_unit")

    def test_the_records_keep_their_values_in_the_new_column(self):
        self.env.cr.execute("SELECT repeat_unit FROM probe_plan ORDER BY id")
        self.assertEqual([row[0] for row in self.env.cr.fetchall()], ["month", "year"])
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.columns"
            " WHERE table_name = 'probe_plan' AND column_name = 'interval_type'"
        )
        self.assertFalse(self.env.cr.fetchone())

    def test_the_history_follows_to_the_new_field_row(self):
        self.env.cr.execute("SELECT field_id FROM probe_tracking")
        self.assertEqual(self.env.cr.fetchone()[0], self.new_field_id)
        self.env.cr.execute(
            "SELECT 1 FROM ir_model_fields WHERE id = %s", (self.old_field_id,)
        )
        self.assertFalse(self.env.cr.fetchone())


def _insert_probe_model(cr, model, fields, ttype="char"):
    cr.execute(
        'INSERT INTO ir_model (model, name, "order", state) '
        "VALUES (%s, '{\"en_US\": \"probe\"}', 'id', 'base') RETURNING id",
        (model,),
    )
    model_id = cr.fetchone()[0]
    field_ids = []
    for name in fields:
        cr.execute(
            "INSERT INTO ir_model_fields"
            " (model_id, model, name, ttype, state, field_description, store)"
            " VALUES (%s, %s, %s, %s, 'base', %s, true) RETURNING id",
            (model_id, model, name, ttype, '{"en_US": "probe"}'),
        )
        field_ids.append(cr.fetchone()[0])
    return field_ids


@tagged("post_install", "-at_install")
class TestRenameFieldMergeKeepsWhatOnlyTheOldFieldHad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_merge (
                id serial PRIMARY KEY, old_name varchar, new_name varchar
            );
            CREATE TABLE probe_merge_link (
                owner int,
                field_id int REFERENCES ir_model_fields (id) ON DELETE CASCADE,
                PRIMARY KEY (owner, field_id)
            );
        """)
        cls.old, cls.new = _insert_probe_model(
            cr, "probe.merge", ("old_name", "new_name")
        )
        cls.admin_id = cls.env.ref("base.user_admin").id
        cr.execute(
            "INSERT INTO probe_merge_link VALUES (1, %s), (1, %s), (2, %s)",
            (cls.old, cls.new, cls.old),
        )
        cr.execute(
            "INSERT INTO ir_default (field_id, user_id, json_value) VALUES "
            "(%s, NULL, '\"g_old\"'), (%s, %s, '\"u_old\"'), (%s, NULL, '\"g_new\"')",
            (cls.old, cls.old, cls.admin_id, cls.new),
        )
        rename_field(cr, "probe.merge", "old_name", "new_name")

    def _rows(self, query, params=()):
        self.env.cr.execute(query, params)
        return self.env.cr.fetchall()

    def test_a_link_only_the_old_field_had_moves_to_the_new_one(self):
        self.assertEqual(
            self._rows("SELECT owner, field_id FROM probe_merge_link ORDER BY 1"),
            [(1, self.new), (2, self.new)],
        )

    def test_a_default_of_another_scope_follows_past_an_expression_index(self):
        self.assertEqual(
            self._rows(
                "SELECT user_id, json_value FROM ir_default WHERE field_id = %s "
                "ORDER BY user_id NULLS FIRST",
                (self.new,),
            ),
            [(None, '"g_new"'), (self.admin_id, '"u_old"')],
        )


@tagged("post_install", "-at_install")
class TestRepointReferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("""
            CREATE TABLE probe_repoint_link (
                owner int,
                field_id int REFERENCES ir_model_fields (id) ON DELETE CASCADE,
                PRIMARY KEY (owner, field_id)
            )
        """)
        cls.field_ids = _insert_probe_model(
            cr, "probe.repoint", [f"f{i}" for i in range(6)]
        )

    def _links(self):
        self.env.cr.execute("SELECT owner, field_id FROM probe_repoint_link ORDER BY 1")
        return self.env.cr.fetchall()

    def test_two_fields_folding_into_one_keep_every_owner(self):
        a, b, kept = self.field_ids[:3]
        self.env.cr.execute(
            "INSERT INTO probe_repoint_link VALUES (1, %s), (1, %s), (2, %s)",
            (a, b, b),
        )
        module_data._repoint_references(
            self.env.cr, "ir_model_fields", {a: kept, b: kept}
        )
        self.assertEqual(self._links(), [(1, kept), (2, kept)])

    def test_the_statements_do_not_grow_with_the_moves(self):
        cr, ids = self.env.cr, self.field_ids

        def spent(moves):
            with counting_statements(cr) as statements:
                module_data._repoint_references(cr, "ir_model_fields", moves)
                return statements.count

        self.assertEqual(
            spent({ids[0]: ids[1]}),
            spent({ids[2]: ids[3], ids[4]: ids[5], ids[1]: ids[0]}),
        )


@tagged("post_install", "-at_install")
class TestRenameFieldRenamesSelectionXmlids(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.cr
        cr.execute("CREATE TABLE probe_pick (id serial PRIMARY KEY, kind varchar)")
        [cls.field_id] = _insert_probe_model(cr, "probe.pick", ("kind",), "selection")
        for value in ("Draft.One", "x"):
            cr.execute(
                "INSERT INTO ir_model_fields_selection (field_id, value, name, sequence)"
                ' VALUES (%s, %s, \'{"en_US": "probe"}\', 1) RETURNING id',
                (cls.field_id, value),
            )
            cr.execute(
                "INSERT INTO ir_model_data (module, name, model, res_id)"
                " VALUES ('base', %s, 'ir.model.fields.selection', %s)",
                (
                    selection_xmlid("base", "probe.pick", "kind", value).partition(".")[
                        2
                    ],
                    cr.fetchone()[0],
                ),
            )

    def _names(self):
        self.env.cr.execute(
            "SELECT name FROM ir_model_data WHERE model = 'ir.model.fields.selection'"
            " AND name LIKE 'selection\\_\\_probe\\_pick\\_\\_%%' ORDER BY name"
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def test_a_renamed_field_renames_its_value_xmlids(self):
        rename_field(self.env.cr, "probe.pick", "kind", "sort")
        self.assertEqual(
            self._names(),
            [
                "selection__probe_pick__sort__draft_one",
                "selection__probe_pick__sort__x",
            ],
        )

    def test_a_renamed_value_is_named_as_reflection_slugs_it(self):
        rename_field(self.env.cr, "probe.pick", "kind", "sort", values={"x": "Ñandú"})
        self.assertEqual(
            self._names(),
            [
                "selection__probe_pick__sort__draft_one",
                "selection__probe_pick__sort__ñandú",
            ],
        )
