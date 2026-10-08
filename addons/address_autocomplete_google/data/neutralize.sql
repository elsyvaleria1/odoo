-- stop address lookups spending the production Google Places key
DELETE FROM credential_credential
 WHERE company_id IS NULL
   AND name = 'System secret: address_autocomplete_google.api_key';
