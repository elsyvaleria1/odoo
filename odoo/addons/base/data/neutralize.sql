-- deactivate crons
UPDATE ir_cron
   SET active = false
 WHERE id NOT IN (
       SELECT res_id
         FROM ir_model_data
        WHERE model = 'ir.cron'
          AND name = 'autovacuum_job'
          AND module = 'base'
);

-- neutralization flag for the database
INSERT INTO ir_config_parameter (key, value)
VALUES ('database.is_neutralized', true)
    ON CONFLICT (key) DO
       UPDATE SET value = true;

-- the source seals its secret with an ODOO_API_ENCRYPTION_KEY the copy does
-- not hold, and every request (CSRF, sessions, signed links) needs it: the
-- copy gets a secret of its own, in clear, which signs nothing of the source's
UPDATE ir_config_parameter
   SET value = gen_random_uuid()::text
 WHERE key = 'database.secret';

-- deactivate webhooks
UPDATE ir_act_server
   SET webhook_url = 'neutralization - disable webhook'
 WHERE state = 'webhook';

-- cut every foreign server: through the user mappings the copy carries,
-- postgres_fdw and dblink would read and write the source's databases
DO $$
DECLARE
    mapping record;
BEGIN
    FOR mapping IN SELECT srvname, usename FROM pg_user_mappings LOOP
        EXECUTE 'DROP USER MAPPING FOR ' || quote_ident(mapping.usename)
             || ' SERVER ' || quote_ident(mapping.srvname);
    END LOOP;
END $$;

-- cancel every unfinished job: its arguments carry production endpoints (webhook
-- URLs), and a job left 'started' by the dump is requeued by the reaper
UPDATE ir_job
   SET state = 'cancelled',
       done_at = (now() AT TIME ZONE 'UTC'),
       exc_name = 'Neutralized',
       exc_message = 'the database was neutralized before this job ran',
       write_date = (now() AT TIME ZONE 'UTC')
 WHERE state IN ('wait_deps', 'scheduled', 'pending', 'started');
