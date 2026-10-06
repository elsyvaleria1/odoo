-- the account's token, app secret and verify token rest in the vault and
-- cannot be blanked column by column: the account is detached from them
UPDATE whatsapp_account
   SET credential_id = NULL
 WHERE credential_id IS NOT NULL;
