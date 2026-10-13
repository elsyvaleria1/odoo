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
    # A unit whose rule domain was edited by hand falls back to the group it named,
    # unless another unit holds that group or shares the unit's name.
    cr.execute(
        """
        UPDATE account_tax_unit unit
           SET horizontal_group_id = grp.id
          FROM account_report_horizontal_group grp
         WHERE unit.horizontal_group_id IS NULL
           AND grp.name->>'en_US' = unit.name
           AND EXISTS (
                   SELECT
                     FROM account_report_horizontal_group_rule rule
                    WHERE rule.horizontal_group_id = grp.id
                      AND rule.field_name = 'company_id'
               )
           AND NOT EXISTS (
                   SELECT
                     FROM account_tax_unit holder
                    WHERE holder.horizontal_group_id = grp.id
               )
           AND NOT EXISTS (
                   SELECT
                     FROM account_tax_unit twin
                    WHERE twin.id != unit.id
                      AND twin.name = unit.name
                      AND twin.horizontal_group_id IS NULL
               )
        """
    )
