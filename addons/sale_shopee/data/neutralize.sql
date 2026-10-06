-- neutralize Shopee API credentials
UPDATE shopee_account
   SET api_endpoint = 'test',
       partner_identifier = 1,
       account_credential_id = NULL;

UPDATE shopee_shop
   SET shop_identifier = 1,
       shop_credential_id = NULL;
