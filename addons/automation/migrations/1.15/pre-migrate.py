from collections import defaultdict

from odoo.db import schema

from odoo.addons.automation.models._steps import make_step_key


def migrate(cr, version):
    if not version:
        return
    # Before the schema update, so no data file reaching a step meets it keyless.
    if not schema.column_exists(cr, "ir_act_server", "step_key"):
        schema.create_column(cr, "ir_act_server", "step_key", "VARCHAR")
    cr.execute(
        """
        SELECT id, automation_rule_id, step_key,
               COALESCE(name->>'en_US', (SELECT value FROM jsonb_each_text(name) LIMIT 1))
          FROM ir_act_server
         WHERE automation_rule_id IS NOT NULL
         ORDER BY automation_rule_id, sequence, id
        """
    )
    taken = defaultdict(set)
    pending = []
    for action_id, rule_id, key, name in cr.fetchall():
        if key:
            taken[rule_id].add(key)
        else:
            pending.append((action_id, rule_id, name))
    for action_id, rule_id, name in pending:
        key = make_step_key(name or "", taken[rule_id])
        taken[rule_id].add(key)
        cr.execute(
            "UPDATE ir_act_server SET step_key = %s WHERE id = %s", (key, action_id)
        )
