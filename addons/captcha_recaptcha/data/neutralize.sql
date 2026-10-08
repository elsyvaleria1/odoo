-- disable reCAPTCHA
UPDATE ir_config_parameter
SET value = ''
WHERE key = 'captcha_recaptcha.site_key';
