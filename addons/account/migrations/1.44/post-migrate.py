def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE account_move SET is_invoice_date_due_chosen = TRUE
         WHERE invoice_payment_term_id IS NULL
           AND invoice_date_due IS NOT NULL
           AND (invoice_date IS NULL OR invoice_date_due != invoice_date)
        """
    )
