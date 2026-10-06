-- disable fedex rest connector
UPDATE delivery_carrier
SET fedex_rest_developer_key = 'dummy',
    fedex_rest_account_number = 'dummy';
