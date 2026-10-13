def migrate(cr, version):
    if not version:
        return
    # _compute_account_map kept the highest id per source account; keep that row
    # so the unique (position_id, account_src_id) constraint can be added.
    cr.execute(
        """
        DELETE FROM account_fiscal_position_account mapping
         USING account_fiscal_position_account later
         WHERE later.position_id = mapping.position_id
           AND later.account_src_id = mapping.account_src_id
           AND later.id > mapping.id
        """
    )
