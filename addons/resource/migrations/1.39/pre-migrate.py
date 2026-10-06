MOVED_FIELDS = (
    "field_res_partner__place_of_birth",
    "field_res_partner__country_of_birth",
)


def migrate(cr, version):
    if not version:
        return
    # where a person was born is resource's now, as a human resource's origin;
    # hr declared it, and its record must not leave with hr's
    cr.execute(
        """
        UPDATE ir_model_data source
           SET module = 'resource'
         WHERE source.module = 'hr'
           AND source.model = 'ir.model.fields'
           AND source.name = ANY(%s)
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data target
                 WHERE target.module = 'resource' AND target.name = source.name
           )
        """,
        [list(MOVED_FIELDS)],
    )
