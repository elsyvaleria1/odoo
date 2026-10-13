# stock_fleet_trace — the load of a delivery trip, from loading to its balance

Extends the dispatch trips of `stock_fleet` (a `stock.picking.batch` with a
vehicle, an operator, a supervisor, departure and return). Active only on
operation types with **Trace Load on Vehicle** (`stock.picking.type.trip_trace`),
so a route can be piloted without changing the others.

## Flow

| Step | What happens in stock | Recorded |
|---|---|---|
| Depart | Every delivery's reserved goods move from where deliveries leave (the shipping transit) to the vehicle's own location, a child of it. A loading leg is inserted in the chain SHIP -> **load** -> OUT, so each delivery keeps its lots. Fuel at departure is required. | `load`, `departure` checkpoints, frozen weight per delivery and trip |
| Stop | *Delivered* validates as loaded. *Partial* (wizard) takes what the customer took per product and lot; a refusal needs a reason from the catalogue. A reason with **Creates Backorder** leaves the rest pending, released from the vehicle. Nothing taken falls back to stock_fleet's *Not delivered*. | `arrival`, `delivery`, `rejection`, `not_delivered` |
| Route incident | Spill, damage, theft, breakdown, relief driver, refuelling. A loss writes its goods off the vehicle only once the trip's supervisor or a stock manager approves it. A breakdown hands pending deliveries and remaining goods to a rescue trip that departs at once. | `incident*`, `handover` |
| Return | Fuel at return is required. What is left on the vehicle becomes an unloading the warehouse counts and validates: goods still reserved to a delivery go back to the transit for the next trip, the rest to stock. | `return`, `unload` |
| Balance | Per product and lot: loaded + received − delivered − written off − handed over = expected back; unloaded − expected = difference. A difference schedules an activity for the supervisor. | `balance_state` |

## Where the trips go

One reader per place, shared by the GPS and routing modules:

- `stock.warehouse._trip_origin()`: where the trips start and end, from
  *Trip Origin Latitude/Longitude* (warehouse form, *Delivery Trips*), or the
  coordinates of the warehouse's address.
- `stock.picking._trip_location()`: where a delivery goes, from its address,
  or the customer's company when the address has no coordinates.

## Expired lots

Expired product does not travel without an approver's signature
(`stock_expired_lot_guard`, active on CDG's SHIP and OUT types; approvers are the
members of *Expired lot sale approver*). In a two-step warehouse the refusal
happens at the SHIP, before the goods reach the shipping transit; where a
delivery still draws from inside the warehouse, loading the trip runs the same
check first, so an expired lot is never found on the vehicle. The rejection
catalogue therefore carries no expiry reason.

## The log

`stock.trip.checkpoint` rows cannot be written or deleted through the ORM, and
each seals the one before it (SHA-256 over its fields and the previous digest).
*Verify Log* recomputes the chain and names the altered checkpoints. A mistake is
answered with a new checkpoint, never an edit.

## Access

Drivers act with their stock rights. What the trip records on their behalf
(checkpoints, balance lines, the vehicle's location) goes through the privilege
`stock_fleet_trace.privilege_trip_trace_record`, not `sudo()`.

## Offline stops

The driver's phone works the route without connection and syncs later
(`stock.trip.offline.event`, JSON-RPC, `auth="user"`):

| Route | Does |
|---|---|
| `/stock_fleet_trace/trip/<id>/package` | The trip, its stops in route order with the lines on board, the rejection reasons with their scope, the incident types and the server time. Takes an optional `head`, see *Phone head* below. |
| `/stock_fleet_trace/trip/<id>/events` | `events`: a list of `{client_uuid, event_type, picking_id, payload, captured_at, latitude, longitude, device_uuid, prev_hash, event_hash}`, plus an optional `head`. Returns each `client_uuid` with its state and error. |

Only the trip's driver, its supervisor or a stock manager syncs it.
`event_type` is `deliver` (`payload.receiver_name`, `payload.signature`, both
optional), `partial` (`payload.note`, required; `payload.receiver_name`,
`payload.signature`, both optional), `not_delivered` (`reason_id`, `note`),
`scan` (`code`, `quantity`) or `incident` (`payload.incident`, which stays
*Reported* for the supervisor). `captured_at` is ISO 8601, UTC when it carries no
offset. `client_uuid` is unique: sending an event again returns it as it stands.

### Delivered and partial: receiver and signature

`deliver` and `partial` may carry `payload.receiver_name` (who took the goods)
and `payload.signature` (a base64-encoded PNG), written to the delivery's
`trip_receiver_name` and standard `signature` fields. On `deliver`, `date_done`
is set to the event's `captured_at` — the valuation posting date this leaves on
the resulting stock move is not verified; check it before relying on it for
accounting.

### Partial: the phone sends no quantities

The phone cannot capture a partial delivery's quantities by lot offline — it
sends `payload.note` describing what the customer took, and the delivery is
**not validated**. The goods stay reserved on the vehicle, the picking's
`trip_partial_review` is set, a note (the receiver and the phone's note) is
posted on the delivery's chatter, and an activity goes to the trip's
supervisor. The trip may still return while the flag is set, but its unloading
is **not validated** until the supervisor captures the real quantities with the
*Partial* wizard (`action_trip_stop_result`), whose confirmation clears the flag.
A `partial` event with no note goes straight to *To review* instead.

### Phone hash chain

Each event carries `prev_hash` (the `event_hash` of the event before it on the
trip, `""` for the trip's first) and `event_hash`: SHA-256 hex of
```
json.dumps(
    {
        "client_uuid": ..., "event_type": ..., "picking_id": ...,
        "captured_at": ...,  # the ISO string as sent
        "latitude": ..., "longitude": ..., "payload": ..., "prev_hash": ...,
    },
    sort_keys=True, separators=(",", ":"), ensure_ascii=False,
)
```
encoded UTF-8. The phone app must reproduce this exactly, including the
`captured_at` string as sent (not re-parsed) and `payload`/`prev_hash`
defaulting to `{}`/`""`. An event with no hash, an altered hash, or a `prev_hash`
that does not match the trip's last received `event_hash` goes to *To review*
and sets the trip's `trip_offline_chain_broken`, with an activity for the
supervisor — some events may have been altered or lost and the record should
not be trusted until reviewed.

### Phone head

Either route accepts `head`: the phone's own latest `event_hash`, when it still
holds events beyond what it is syncing (e.g. a partial upload). The trip
records it as `trip_offline_phone_head`. *Return* refuses while it is known and
differs from the trip's last received `event_hash` — the phone must finish
syncing first.

Events apply in the order captured, each in its own savepoint, through the same
buttons and wizards as online. Their checkpoints carry the phone's time and
coordinates, method *Manual*, and the note "Captured offline <uuid>". An event
that fails goes to *To review* with its error and an activity for the supervisor.
While any event is pending or to review, or a phone head is unsynced, the trip
does not return; while a partial delivery or an offline event awaits review,
its unloading is not validated either. The supervisor or a stock manager
resolves an event by hand and *Dismisses* it (Inventory › Delivery › Offline
Events, or the trip's tab).

## Weight by delivery and the rescue trip

When a delivery boards a trip — at loading, or at the handover for a rescue
trip — `stock.trip.stop` freezes what it weighs on that trip. The trip sheet
(the BATCH PDF) is read from those rows, so a delivery that rides a later trip
does not change an earlier trip's sheet. For each delivery it shows the weight
at departure, delivered, written off, handed over and returned, with totals
that add up to the trip's weight at departure; the sheet says so when they do
not, or when a row goes negative. A delivery brought back is checked against
its own weight.

- **Written off** is charged to the delivery whose reservation the approved
  incident released. Goods nobody reserved (rejections) are lost first, so a
  spill of refused goods never shortens another customer's delivery.
- **Rejections** stay on the vehicle, free. A write-off or a handover of free
  goods comes out of the rejecting deliveries first; what is left, and what a
  rescue trip took over free, shows on a row for goods nobody reserved.
- A delivery back on the road (loaded again after it was not delivered) starts
  its result over; its earlier trip keeps its own.
- A loaded delivery does not leave a trip that has not departed while its goods
  are on the vehicle: unload the trip first.

After a breakdown, the sheet of the broken-down trip also carries the rescue
trip: its name, driver, vehicle, supervisor, departure, the reason of the
breakdown that sent it, the weight it took over and the goods the handover
moved (delivery, product, lot, quantity). The rescue trip's sheet names the
trip whose load it took over and adds up on its own.

The weight at departure of a delivery lives only on its `stock.trip.stop`
row; the transfer keeps none of its own (the old
`stock.picking.trip_weight_departure` moved to stops in the 19.0.1.1.0
migration). The transfers' list inside the trip shows their shipping weight,
which adds up to stock_fleet's load.

On the form (es_MX) the weights say what they are: *Peso de las entregas* is
stock_fleet's weight of the deliveries still on the trip against the vehicle's
capacity (it drops when goods are rejected, written off, not delivered or
handed over), *Peso al salir* what loaded (`weight_departure`) and *Peso a
bordo ahora* what the vehicle carries now (`weight_on_board`). Weights show two
decimals, in the configured weight unit.

## Signature and who received

A delivery signed on the phone shows the signature in its *Additional Info*
tab and has a *View Signature* button that opens it with who received it, so
nobody has to print the slip to check it; the trip's list of deliveries shows
*Received By* and the same button. On the delivery slip, under the signature,
*Received By:* carries the name captured on the phone (a clerk or the warehouse
keeper may sign for the customer), or a blank line to fill in by hand. A trip
delivery without a phone signature prints lines to sign on paper, and the
slip's *Operator* is the trip's driver.

At the customer's door the delivery does not ask the expiry question again when
the operation type's expired-lot guard already judged the lots on loading
(*Block expired lots*); without the guard, Odoo still asks.

## Driver's trips waiting for loading

On the driver's form a planned trip says the warehouse has not loaded it yet,
and the driver screen lists it as *Planned: waiting for the warehouse to load
it*: nothing can be done on the road until the goods are on the vehicle.

The GPS track of a trip is drawn by `stock_fleet_trace_gps_geoengine`.

## Driver screen

`/stock_fleet_trace/driver` is the phone app that works a trip offline on top
of the routes above. It is a standalone page (not the web client) with plain
ES modules in `static/driver/`, a Web App Manifest and a service worker, so
Chrome on Android installs it and it reopens without signal.

| Route | Does |
|---|---|
| `GET /stock_fleet_trace/driver` | The page (`auth="user"`); `?trip=<id>` opens that trip. Its texts come translated in `<body data-boot>` (`_driver_terms` in `controllers/main.py`), so they work offline. |
| `GET /stock_fleet_trace/driver/manifest.webmanifest` | The manifest: scope and start URL `/stock_fleet_trace/driver`, standalone. |
| `GET /stock_fleet_trace/driver/sw.js` | The service worker (`auth="public"`), with `Service-Worker-Allowed: /stock_fleet_trace/driver`. Its version is a hash of the files in `static/driver/`: changing one makes phones install the new version. |
| `/stock_fleet_trace/driver/trips` | JSON-RPC: the traced trips, planned, loaded or in transit, the user drives (`operator_id.user_id`) or supervises. |
| `GET /.well-known/assetlinks.json` | Digital Asset Links (`auth="public"`) for an Android app that wraps this page as a Trusted Web Activity: the package in system parameter `stock_fleet_trace.driver_app_package`, the SHA-256 of its signing certificate in `stock_fleet_trace.driver_app_sha256` (several separated by commas or spaces). Until both are set it answers `[]` and Chrome shows its address bar inside the app. |

The package route also answers `chain_head`, the trip's last received
`event_hash`, where a phone with no events of its own starts its chain.

**Opening and installing.** The *Driver Screen* button on a traced trip opens it
on that trip. On the phone, open `https://<server>/stock_fleet_trace/driver`
in Chrome, log in, and use *Add to Home screen* / *Install app*: from then on
it opens full screen from its icon. The first opening needs signal: the service
worker caches the page and its files then.

**Offline.** Choosing a trip downloads its package to IndexedDB; from then on
the stops, the lines on board, the rejection reasons and the incident types
come from the phone. The page and its files are served cache-first; the page is
refreshed in the background whenever there is signal. Every capture is an
immutable event in IndexedDB, chained to the previous one with the canonical
hash (`static/driver/canonical.js`, checked against the server by
`TestDriverHash`), with the phone's time (ISO 8601 with its offset), its
position when the phone gives one within a few seconds (`null` otherwise) and a
device id kept per phone.

**Scanning.** The camera reads QR, Code 128, DataMatrix, EAN-13 and Code 39
where Chrome has `BarcodeDetector`, and takes the lot from a GS1 label's
`(10)`; a hardware scanner or the keyboard types into the scan box.
A delivery slip opens its stop. On a stop, a lot is checked against the
package: a lot that does not travel for that stop is flagged at once, offline,
with the stop it belongs to if any. A lot that checks out is sent as a `scan`
event (one unit per read, never more than travel for the stop).

**Stop actions.** *Delivered* (receiver and signature, optional), *Partial*
(note required, receiver and signature), *Not delivered* (reason from the
package, note) and *Incident* (type from the package, description required,
also from the trip screen). The signature is drawn on a canvas and sent as a
base64 PNG without the `data:` prefix. The phone refuses on the spot what the server
would send to review: *Delivered* at a stop where lots were scanned but not all
the goods (use *Partial*), and any stop result while the trip is still planned
(not loaded). A final result the server sent to review or the supervisor
dismissed opens the stop again. The phone reports spills, damage, theft,
breakdowns and other incidents; refuelling and relief drivers are recorded in
the office.

**Sync.** Without the driver doing anything: on load, when the phone comes back
online, after each capture and every 30 seconds, the queued events of each trip
are posted in chain order to `/events`, five at a time, and the phone's last
`event_hash` goes as `head` with the last batch only, once everything before it
arrived. A request with no answer in 15 seconds counts as no signal; captures
are serialized across tabs. The bar at the top shows the connection, the
pending count and the last sync. An expired session (a redirect to the login,
or Odoo's session error) shows *log in* and keeps the queue; any other server
error is shown as such.

**On the server.** An event whose data checks out becomes the chain's head even
when it did not follow the previous one: the gap goes to review and is flagged
once, and what the phone captured after it is still applied. An event naming a
delivery that does not exist, or a time that cannot be read, goes to review
without failing the rest of the sync. Stop results captured before the
departure wait pending and are applied when the trip departs; events are
applied in the order the phone chained them.

**A phone that will not come back.** When the phone that reported unsent events
is lost, the trip's supervisor or a stock manager presses *Release Phone* on
the trip, which lets it return.

**Shared phones.** Every record on the phone carries the user who captured it:
a driver only sees, and only sends, his own trips and events; another driver's
unsent events are counted in the bar and wait for that driver to log in.

## Known limits

- The vehicle location sits under the transit, so a *make-to-stock* delivery
  sourced at that transit could reserve goods on a vehicle. CDG deliveries are
  chained (make-to-order) and never do.
- The balance weights are theoretical: product weight × quantity, no pallets
  or packaging (`_trip_goods_weight`). What a delivery puts on the vehicle,
  tare included, is stock_fleet's `_trip_shipping_weight` (the load
  percentage, the BATCH sheet's planned weight, the waybill); it is not
  recomputed here.
- Without `stock_fleet_trace_gps` the times are the button presses, recorded
  as `manual`.
- Driver screen: the camera needs Chrome's `BarcodeDetector` (Android Chrome
  has it; desktop Linux does not) and HTTPS; elsewhere the scanner or the
  keyboard is the way in. The phone checks lots and scan counts against its
  downloaded package only: scans made from the backend meanwhile are not
  seen, so a later phone scan may go to *To review*.
- Driver screen: two phones working the same trip each keep their own chain
  and break it for the server; one phone per trip.
