import uuid

from .conftest import requires_pg


@requires_pg
def test_the_next_holder_sees_what_the_previous_one_wrote(base_db):
    import odoo.db
    from odoo.modules.loading import _lock_module_operations

    key = f"loading.lock_commit.{uuid.uuid4().hex}"
    connection = odoo.db.db_connect(base_db)
    try:
        with connection.cursor() as cr_a, connection.cursor() as cr_b:
            with _lock_module_operations(cr_a, base_db):
                cr_a.execute(
                    "INSERT INTO ir_config_parameter (key, value) VALUES (%s, '1')",
                    (key,),
                )
            with _lock_module_operations(cr_b, base_db):
                cr_b.execute("SELECT 1 FROM ir_config_parameter WHERE key = %s", (key,))
                seen = cr_b.fetchone()
            cr_a.commit()
        assert seen, (
            "the lock was released before the operation committed, and the next "
            "holder took its snapshot without the operation's writes"
        )
    finally:
        with connection.cursor() as cr:
            cr.execute("DELETE FROM ir_config_parameter WHERE key = %s", (key,))
            cr.commit()
