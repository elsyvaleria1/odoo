-- account tokens are encrypted and cannot be blanked column by column
UPDATE social_account
   SET account_credential_id = NULL
 WHERE account_credential_id IS NOT NULL;
