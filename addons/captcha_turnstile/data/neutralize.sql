-- disable Cloudflare Turnstile
UPDATE ir_config_parameter
SET value = ''
WHERE key = 'captcha_turnstile.site_key';
