def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE ir_act_server
           SET input_form_node_id = id
         WHERE automation_rule_id IS NOT NULL
        """
    )
