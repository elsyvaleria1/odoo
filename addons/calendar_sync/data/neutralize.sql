-- neutralization of calendar synchronization: integration deactivates every
-- connection; no account resumes from where production left off
UPDATE calendar_sync_account
   SET stopped = true,
       sync_token = NULL,
       last_sync_date = NULL;
