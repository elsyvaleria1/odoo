def migrate(cr, version):
    if not version:
        return
    # A version without a calendar was fully flexible; resource's 1.34 created
    # the schedule that says so before this module upgrades, and base 1.151
    # holds it since resource folded into base.
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
