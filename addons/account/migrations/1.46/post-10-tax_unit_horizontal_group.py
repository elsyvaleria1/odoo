def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE account_tax_unit unit
           SET horizontal_group_id = (
                   SELECT rule.horizontal_group_id
                     FROM account_report_horizontal_group_rule rule
                    WHERE rule.field_name = 'company_id'
                      AND rule.domain = concat(
                              '[(''account_config_id.account_tax_unit_ids'', ''in'', ',
                              unit.id,
                              ')]'
                          )
                    ORDER BY rule.id
                    LIMIT 1
               )
         WHERE unit.horizontal_group_id IS NULL
        """
    )
