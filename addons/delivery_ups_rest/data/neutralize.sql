-- disable ups rest connector
UPDATE delivery_carrier
SET ups_shipper_number = 'dummy',
    ups_client_id = 'dummy';
