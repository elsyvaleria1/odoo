from odoo.tests.common import TransactionCase, tagged
from odoo.tools.module_data import (
    UNDECLARED_REFERENCES,
    _model_column_of,
    lift_columns,
    rehome_references,
    rekey_records,
)


@tagged("post_install", "-at_install")
class TestRekeyRecords(TransactionCase):
    """A box and the crate built on its table take new ids, and every stored
    reference to them follows, through the fields; a foreign key into the
    crate's own table is set aside meanwhile and comes back as it was."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.cr.execute("""
            CREATE TABLE probe_box (id serial PRIMARY KEY, name varchar);
            CREATE TABLE probe_crate (label varchar) INHERITS (probe_box);
            ALTER TABLE probe_crate ADD PRIMARY KEY (id);
            CREATE TABLE probe_slot (id serial PRIMARY KEY, box_id int UNIQUE);
            CREATE TABLE probe_box_slot_rel (probe_box_id int, probe_slot_id int);
            CREATE TABLE probe_log (id serial PRIMARY KEY, res_model varchar, res_id int);
            CREATE TABLE probe_note (id serial PRIMARY KEY, ref varchar);
            CREATE TABLE probe_crate_slot_rel (
                probe_crate_id int REFERENCES probe_crate (id) ON DELETE CASCADE,
                probe_slot_id int
            );
            INSERT INTO probe_box (id, name) VALUES (1, 'one'), (2, 'two');
            INSERT INTO probe_crate (id, name, label) VALUES (3, 'three', 'crate');
            INSERT INTO probe_slot (id, box_id) VALUES (1, 1), (2, 2), (3, 3);
            INSERT INTO probe_box_slot_rel VALUES (1, 1), (3, 3);
            INSERT INTO probe_log (res_model, res_id) VALUES
                ('probe.box', 1), ('probe.crate', 3), ('res.partner', 1);
            INSERT INTO probe_note (ref) VALUES ('probe.box,2'), ('res.partner,2');
            INSERT INTO probe_crate_slot_rel VALUES (3, 2);
        """)
        box_id = cls._insert_model("probe.box")
        crate_id = cls._insert_model("probe.crate")
        slot_id = cls._insert_model("probe.slot")
        log_id = cls._insert_model("probe.log")
        note_id = cls._insert_model("probe.note")
        cls._insert_field(
            slot_id, "probe.slot", "box_id", "many2one", relation="probe.box"
        )
        cls._insert_field(
            box_id,
            "probe.box",
            "slot_ids",
            "many2many",
            relation="probe.slot",
            relation_table="probe_box_slot_rel",
            column1="probe_box_id",
            column2="probe_slot_id",
        )
        cls._insert_field(crate_id, "probe.crate", "label", "char")
        cls._insert_field(
            crate_id,
            "probe.crate",
            "spare_slot_ids",
            "many2many",
            relation="probe.slot",
            relation_table="probe_crate_slot_rel",
            column1="probe_crate_id",
            column2="probe_slot_id",
        )
        cls._insert_field(log_id, "probe.log", "res_id", "many2one_reference")
        cls._insert_field(note_id, "probe.note", "ref", "reference")
        cls.env.cr.execute(
            "INSERT INTO ir_model_data (module, name, model, res_id) "
            "VALUES ('test_rekey', 'probe_two', 'probe.box', 2)"
        )
        cls.action = cls.env["ir.actions.act_window"].create(
            {"name": "probe box", "res_model": "res.partner", "res_id": 2}
        )
        cls.env.flush_all()
        cls.env.cr.execute(
            "UPDATE ir_act_window SET res_model = 'probe.box' WHERE id = %s",
            [cls.action.id],
        )
        # each box takes the id another one holds until it moves too
        rekey_records(
            cls.env.cr, ["probe.box", "probe.crate"], "probe_box", {1: 2, 2: 3, 3: 10}
        )

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
        columns = ["model_id", "model", "name", "ttype", "state", "field_description"]
        params = [model_id, model, name, ttype, "base", '{"en_US": "probe"}']
        columns.append("store")
        params.append(True)
        for column, value in values.items():
            columns.append(column)
            params.append(value)
        cls.env.cr.execute(
            "INSERT INTO ir_model_fields (%s) VALUES (%s)"
            % (", ".join(columns), ", ".join(["%s"] * len(params))),
            params,
        )

    def _rows(self, query):
        self.env.cr.execute(query)
        return self.env.cr.fetchall()

    def test_the_rows_take_their_new_ids_crate_table_included(self):
        self.assertEqual(
            self._rows("SELECT id, name FROM probe_box ORDER BY id"),
            [(2, "one"), (3, "two"), (10, "three")],
        )
        self.assertEqual(
            self._rows("SELECT id, label FROM probe_crate"), [(10, "crate")]
        )

    def test_the_sequence_continues_after_the_new_ids(self):
        self.assertEqual(self._rows("SELECT nextval('probe_box_id_seq')"), [(11,)])

    def test_a_many2one_follows_through_its_unique_key(self):
        self.assertEqual(
            self._rows("SELECT id, box_id FROM probe_slot ORDER BY id"),
            [(1, 2), (2, 3), (3, 10)],
        )

    def test_a_many2many_follows(self):
        self.assertEqual(
            self._rows(
                "SELECT probe_box_id, probe_slot_id FROM probe_box_slot_rel ORDER BY 2"
            ),
            [(2, 1), (10, 3)],
        )

    def test_a_foreign_key_into_the_crate_table_follows_and_comes_back(self):
        self.assertEqual(
            self._rows(
                "SELECT probe_crate_id, probe_slot_id FROM probe_crate_slot_rel"
            ),
            [(10, 2)],
        )
        self.assertEqual(
            self._rows(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'probe_crate_slot_rel'::regclass AND contype = 'f'"
            ),
            [
                (
                    "FOREIGN KEY (probe_crate_id) REFERENCES probe_crate(id) ON DELETE CASCADE",
                )
            ],
        )

    def test_a_model_and_id_pair_follows_only_for_these_models(self):
        self.assertEqual(
            self._rows("SELECT res_model, res_id FROM probe_log ORDER BY id"),
            [("probe.box", 2), ("probe.crate", 10), ("res.partner", 1)],
        )

    def test_a_reference_value_follows_only_for_these_models(self):
        self.assertEqual(
            self._rows("SELECT ref FROM probe_note ORDER BY id"),
            [("probe.box,3",), ("res.partner,2",)],
        )

    def test_an_action_opening_a_box_follows(self):
        self.assertEqual(
            self._rows(f"SELECT res_id FROM ir_act_window WHERE id = {self.action.id}"),
            [(3,)],
        )

    def test_an_external_id_follows(self):
        self.assertEqual(
            self._rows(
                "SELECT res_id FROM ir_model_data "
                "WHERE module = 'test_rekey' AND name = 'probe_two'"
            ),
            [(3,)],
        )


@tagged("post_install", "-at_install")
class TestRekeyRecordsReadsEveryModelColumn(TransactionCase):
    def test_every_undeclared_record_id_is_known(self):
        """An Integer that holds a record id beside a model name, and is not a
        Many2oneReference, is listed for rekey_records, or it is missed."""
        listed = {(table, column) for table, column, __ in UNDECLARED_REFERENCES}
        suffixes = ("res_id", "_thread_id", "record_id")
        for name, model in self.env.registry.items():
            if model._abstract or model._transient or not model._auto:
                continue
            for field in model._fields.values():
                if (
                    field.type == "integer"
                    and field.store
                    and field.name.endswith(suffixes)
                ):
                    with self.subTest(model=name, field=field.name):
                        self.assertIn((model._table, field.name), listed)

    def test_every_stored_model_and_id_pair_is_the_one_it_reads(self):
        """rekey_records pairs a res_id with its model column by name, before
        any registry exists; every pair the registry knows must match it."""
        for name, model in self.env.registry.items():
            if model._abstract or not model._auto:
                continue
            for field in model._fields.values():
                if field.type == "many2one_reference" and field.store:
                    model_field = model._fields[field.model_field]
                    expected = (
                        (model_field.name, False)
                        if model_field.store
                        else (model_field.related.removesuffix(".model"), True)
                    )
                    with self.subTest(model=name, field=field.name):
                        self.assertEqual(
                            _model_column_of(self.env.cr, model._table, field.name),
                            expected,
                        )


@tagged("post_install", "-at_install")
class TestRehomeReferences(TransactionCase):
    """A crate became its box's row extended: what was filed under the crate
    is the box's, while its external id still names the crate."""

    def test_the_references_move_to_the_parent_model(self):
        cr = self.env.cr
        cr.execute("""
            CREATE TABLE probe_log (id serial PRIMARY KEY, res_model varchar, res_id int);
            INSERT INTO probe_log (res_model, res_id) VALUES
                ('probe.crate', 3), ('res.partner', 3);
            INSERT INTO ir_model (model, name, "order", state)
                 VALUES ('probe.log', '{"en_US": "probe"}', 'id', 'base');
            INSERT INTO ir_model_fields (model_id, model, name, ttype, state,
                                         field_description, store)
                 SELECT id, 'probe.log', 'res_id', 'many2one_reference', 'base',
                        '{"en_US": "probe"}', true
                   FROM ir_model WHERE model = 'probe.log';
            INSERT INTO ir_model_data (module, name, model, res_id)
                 VALUES ('test_rehome', 'crate_three', 'probe.crate', 3);
        """)
        rehome_references(cr, ["probe.crate"], "probe.box")
        cr.execute("SELECT res_model, res_id FROM probe_log ORDER BY id")
        self.assertEqual(cr.fetchall(), [("probe.box", 3), ("res.partner", 3)])
        cr.execute("SELECT model FROM ir_model_data WHERE module = 'test_rehome'")
        self.assertEqual(cr.fetchall(), [("probe.crate",)])


@tagged("post_install", "-at_install")
class TestLiftColumns(TransactionCase):
    """A box's columns become its shelf's, on the same id; a crate is a box."""

    def setUp(self):
        super().setUp()
        self.env.cr.execute("""
            CREATE TABLE probe_shelf (id int PRIMARY KEY, note varchar);
            CREATE TABLE probe_box (id int PRIMARY KEY, size int, note varchar);
            CREATE TABLE probe_crate (label varchar) INHERITS (probe_box);
            INSERT INTO probe_shelf VALUES (1, NULL), (2, 'kept'), (3, NULL);
            INSERT INTO probe_box VALUES (1, 10, 'one'), (2, 20, 'two');
            INSERT INTO probe_crate (id, size, note, label) VALUES (3, 30, NULL, 'c');
        """)

    def _rows(self, query):
        self.env.cr.execute(query)
        return self.env.cr.fetchall()

    def test_the_values_move_and_the_columns_go(self):
        lift_columns(
            self.env.cr,
            "probe_box",
            "probe_shelf",
            ["size", "note"],
            keep_target=["note"],
        )
        self.assertEqual(
            self._rows("SELECT id, size, note FROM probe_shelf ORDER BY id"),
            [(1, 10, "one"), (2, 20, "kept"), (3, 30, None)],
        )
        self.assertEqual(
            self._rows(
                "SELECT count(*) FROM information_schema.columns"
                " WHERE table_name IN ('probe_box', 'probe_crate')"
                " AND column_name IN ('size', 'note')"
            ),
            [(0,)],
        )

    def test_a_column_can_take_a_new_name(self):
        lift_columns(self.env.cr, "probe_box", "probe_shelf", [("size", "width")])
        self.assertEqual(
            self._rows("SELECT id, width FROM probe_shelf ORDER BY id"),
            [(1, 10), (2, 20), (3, 30)],
        )

    def test_a_view_reading_the_column_on_any_table_of_the_tree_is_dropped(self):
        self.env.cr.execute(
            "CREATE VIEW probe_crate_sizes AS SELECT id, size FROM probe_crate"
        )
        lift_columns(self.env.cr, "probe_box", "probe_shelf", ["size"])
        self.assertEqual(
            self._rows(
                "SELECT count(*) FROM pg_class WHERE relname = 'probe_crate_sizes'"
            ),
            [(0,)],
        )
        self.assertEqual(
            self._rows("SELECT id, size FROM probe_shelf ORDER BY id"),
            [(1, 10), (2, 20), (3, 30)],
        )

    def test_a_value_with_nowhere_to_go_drops_nothing(self):
        self.env.cr.execute("INSERT INTO probe_box VALUES (4, 40, NULL)")
        with self.assertRaisesRegex(ValueError, "1 row"):
            lift_columns(self.env.cr, "probe_box", "probe_shelf", ["size"])
        self.assertEqual(
            self._rows(
                "SELECT count(*) FROM information_schema.columns"
                " WHERE table_name = 'probe_box' AND column_name = 'size'"
            ),
            [(1,)],
        )
