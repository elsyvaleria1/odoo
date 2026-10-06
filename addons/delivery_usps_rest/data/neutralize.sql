-- disable usps
UPDATE delivery_carrier
SET usps_eps_account_number = 'dummy',
    usps_crid = 'dummy',
    usps_mid = 'dummy',
    usps_manifest_mid = 'dummy';
