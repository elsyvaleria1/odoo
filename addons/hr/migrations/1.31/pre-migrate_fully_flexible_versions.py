def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE hr_version
           SET resource_calendar_id = data.res_id,
               is_flexible = TRUE,
               is_fully_flexible = TRUE
          FROM ir_model_data data
         WHERE data.module IN ('resource', 'base')
           AND data.name = 'resource_calendar_fully_flexible'
           AND hr_version.resource_calendar_id IS NULL
        """
    )
