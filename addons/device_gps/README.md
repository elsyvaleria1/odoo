# GPS tracking

Teltonika telemetry is decoded into GPS observations and projected into current
state and reports. AVL field 14 is an ICCID fragment (`iccid2`), not a hardware
IMEI. The legacy tracker endpoint resolves its `gps_receiver_key` globally and
refuses ambiguous keys, including archived duplicates.

Version 19.0.1.11.0 adds an enrollment-scoped endpoint through `device_transport`:

```
POST /device/v1/enrollments/<enrollment-key>/channels/<channel-key>/gps
Authorization: Bearer <enrollment-token>
```

Provision and activate an enrollment, bind it to the operational GPS device,
and create a telemetry channel whose key matches the sender's field 14. Configure
the device's decoder profile for its protocol. The same channel key can exist in
other enrollments or companies; their credentials remain separate. Responses use
the existing binary ACK/NACK contract. Legacy tracker URLs remain supported.

Accepted scoped observations retain their admission `channel_id`, device and
webhook source. Their source cannot be reassigned. Legacy observations retain an
empty channel; upgrading does not invent historical enrollment or vehicle
assignments. Full observation immutability and effective assignment history are
separate, unfinished architecture work.

Upgrade with `-u device_gps`. This installs `device_transport` and adds the nullable
channel reference; foreign-table installations synchronize both local and remote
schemas through the existing FDW helper. The upgrade does not provision tokens,
activate enrollments, or redirect senders automatically. Existing credentials and
legacy authentication policy continue to govern legacy URLs; scoped channels
always enforce bearer authentication.
