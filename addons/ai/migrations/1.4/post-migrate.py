from odoo.tools import SQL


def migrate(cr, version):
    if not version:
        return
    # 'to upgrade', not 'to install': an install rewrites the noupdate records
    # ai_speech adopts from ai, and would lose their customisations.
    cr.execute(
        SQL(
            """
            UPDATE ir_module_module bridge
               SET state = 'to upgrade'
             WHERE bridge.name = 'ai_speech'
               AND bridge.state = 'uninstalled'
               AND NOT EXISTS (
                   SELECT 1
                     FROM ir_module_module_dependency dep
                     JOIN ir_module_module needed ON needed.name = dep.name
                    WHERE dep.module_id = bridge.id
                      AND needed.state NOT IN ('installed', 'to upgrade')
               )
            """
        )
    )
