-- an archived credential is how a bot goes off the air; the stored hash would still route webhooks
UPDATE credential_credential
   SET active = FALSE
 WHERE id IN (SELECT credential_id FROM telegram_bot);
UPDATE telegram_bot
   SET token_hash = NULL
 WHERE token_hash IS NOT NULL;
UPDATE telegram_bot
   SET on_air = FALSE
 WHERE on_air;
