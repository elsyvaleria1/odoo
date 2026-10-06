DELETE FROM credential_credential
 WHERE company_id IS NULL
   AND name = 'System secret: product_barcodelookup.api_key';
