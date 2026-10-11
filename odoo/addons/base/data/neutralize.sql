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
