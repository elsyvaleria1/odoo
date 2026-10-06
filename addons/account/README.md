# Accounting and Invoicing

Record invoices, bills, payments and journal entries.

Provides journals, accounts, taxes, customer invoices, vendor bills, payment registration and reconciliation. Configuration determines the chart of accounts and available accounting workflows; country-specific requirements use localization addons.

Unreconciliation reverses posted automatic cash-basis and exchange-difference entries by default and deletes eligible draft entries. Localizations can override `account.move._get_unreconcile_entry_policy()` to select `delete_if_allowed` for posted automatic entries. Core checks ownership and deletion safeguards before removing reconciliation links; protected entries use the standard reversal flow. The policy never grants extra access rights.

Dependent reconciliations follow normal `unlink()` inheritance, with matching-number and payment-state updates for each affected component. A savepoint keeps the full correction atomic if cleanup fails. Shared exchange entries require all owning partials to be unreconciled together; partial removal would retain an incorrect exchange adjustment. Cleanup discovers linked entries and all their journal items independently of record visibility, then checks the caller's read access before proceeding; a filtered subset cannot be used to delete or reverse an entry. Deletion uses an internal, entry-scoped capability solely to allow eligible posted journal items to be removed; audit, hash, sequence, fiscal and tax protections still run.

A readable posted automatic entry that the caller cannot delete uses reversal if the caller can perform it. Draft automatic entries must be deleted or the operation refused; posting a reversal of an unposted entry would create a spurious ledger amount.
