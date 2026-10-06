-- stop the long-lived streams (MQTT, websockets) that open to live devices
UPDATE integration_stream
   SET active = false;

-- disconnect the outbound connections to third-party services
UPDATE integration_connection
   SET active = false;
