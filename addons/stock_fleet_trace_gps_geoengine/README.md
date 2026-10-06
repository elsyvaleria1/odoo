# Delivery Trips - GPS Track Map (t32945)

Bridge between `stock_fleet_trace_gps` (trips stamped from the vehicle's GPS)
and `device_gps_geoengine` (GPS trails on a map); installs itself when both are.

*View GPS Track* on a traced trip that departed draws the vehicle's GPS trail
from departure to return (or to now, while it travels) on the trail map of
`device_gps_geoengine`, with the trip's places marked on a second layer:

| Colour | Marker |
|---|---|
| grey | planned stop: the customer's coordinates of each delivery |
| blue | departure |
| violet | return |
| yellow | arrival at a customer |
| green | delivery |
| orange | not delivered or product rejected |
| red | incident or handover |
| pink | GPS alert (unplanned stop, harsh driving, silence…) |

Clicking a marker names it (delivery, event, time).

The track runs from the first sign of departure (the GPS leaving the warehouse
geofence, or the departure) to the last of return, or to now while the trip
travels. Only events that carry a place are marked (GPS stamps, the phone's
captures, incidents with coordinates). The points are transient
(`wizard.stock.trip.track.point`), created each time the button is pressed and
tied to the trail they are drawn with; opening the map again later means
pressing the button again.

A stock user draws a trip's track without seeing GPS devices: the trail and its
points are made under the privilege *a trip draws the GPS track of its
vehicle*, and the user only reads the trails and points they drew (the trail keeps no
device). GPS users read the points they drew too, since every trail map carries
the layer.

A rescue trip after a breakdown has its own track, on its own vehicle.
