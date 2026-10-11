Resources, devices and business vocabulary
=========================================

A resource is the shared operational identity of a person or material slot.
An employee, asset, vehicle, room or work center is a business representation
of that identity. Business models keep their names and workflow; shared models
use resource, reservation, assignment, device, observation and reading.

Ownership and capability boundaries
-----------------------------------

=============================== ================================================
Abstraction                     Owns
=============================== ================================================
``resource.resource``           Identity, company, working timezone, calendar,
                                capacity, roles and operational availability
``mixin.resource``              A host's reference to that identity; creation and
                                copy semantics distinguish owners and references
``resource.reservation``        Time-bounded capacity claims projected from work
``resource.assignment``         Effective-dated roles and custody
``resource.relation``           Effective-dated containment and dependencies
``mixin.resource.scheduling``   Projection of business dates/resources into claims
``mixin.resource.allocation``   Allocated share and working hours
``mixin.resource.ledger``       Reconciliation of business projections by identity
``device.device``               Endpoint identity, credentials and communications
``device_resource``             Optional, non-owning resource representation
``device.data.log.gps``         Device observations with timestamps and provenance
``resource.gps.binding``        Effective-dated device attachment and known gaps
``mixin.gps``                   Shared telemetry, bounded readers and navigation
=============================== ================================================

Do not create an additional resource merely because the same physical thing
appears in another business application. A referencing host uses the existing
``resource_id`` and ``_resource_owns = False``. Its copy gets a new identity;
an owning host copies its resource. Device attachments are not copied.

A resource has one owning host across installed business models. Asset kinds
share their root namespace for that lookup, and an owner must match the
resource's person/material type. Referencing hosts claim no ownership.
The mixin discovers owners from model capabilities rather than depending on
business modules. It serializes explicit claims on the resource row, including
a tuple touch for repeatable-read retries, so concurrent claims cannot both
become owners. Creating on a recordset does not exclude its existing owner.

All typed representations, including references, must match the resource type.
A reference with a unique ``resource_id`` claims one representation in its own
business namespace, including archived records; endpoints may share identities.
Referencing hosts check normal resource visibility before attaching and serialize
claims on the same resource row. Creating a representation preserves existing
calendar and efficiency settings unless explicitly supplied by the caller.

A work center's ``asset_id`` is a vocabulary projection of ``resource_id.asset_id``.
It is not a second identity pointer. Changing the represented resource updates
that projection. Releasing a provisioned slot archives it only when no owning or
referencing host, current or planned relation, reservation, assignment, endpoint,
GPS attachment or maintenance profile still uses it. Composition retains each
member's identity and never implies a reservation for the whole assembly.

The manufacturing bridge's 1.1 migration validates legacy machine pointers
against resource identities before removing the redundant column. Manufacturing
maintenance 1.8 imports legacy equipment membership as resource containment,
without creating artificial asset owners; existing containment remains authoritative.
Conflicting legacy identities or ambiguous new membership abort the upgrade.

A business model translates at its boundary. For example, a work center's
throughput vocabulary maps to resource capacity, and a vehicle's operator maps
to an assignment role. The scheduling engine accepts resource identities,
intervals and allocation percentages; it does not accept employee, vehicle or
manufacturing-specific parameters. Reservation and assignment are distinct:
a claim consumes capacity, while an assignment records a role or custody.

Identity, composition and endpoint representation
-------------------------------------------------

Sharing an identity means two records represent the same thing. Composition
means one resource contains or uses other resources. Those members keep their
own identities, capacities, calendars, timezones, assignments and reservations.
A room and its equipment, or a vehicle and its tracker, can be independent
resources even when their lifecycles are connected. Detaching a component must
not replace either resource's identity or reinterpret its observation history.

The current asset hierarchy records physical components through
``resource.asset.parent_id``. Each component has its own ``resource_id``.
The device hierarchy records endpoint structure through ``device.device.parent_id``;
it does not automatically change physical asset containment. Several device
endpoints can refer to one physical asset through ``own_asset_id``. Conversely,
a parent endpoint and its child can refer to distinct component assets, or to
the same physical asset. Mapping that latter endpoint edge into resource
containment would create a false self-cycle. These supported cardinalities are covered by the asset/device integration tests.

A device's endpoint identifier, credentials and channels identify a communication
endpoint. The physical thing represented by that endpoint may already have a
resource through its own asset; its tracking target is another relationship.
A virtual endpoint need not consume operational capacity merely to communicate.
A physical device that needs reservations, custody or maintenance should have
an operational resource, with an existing asset's identity reused when they
represent the same thing. This does not merge a device component with its parent
or with the resource it observes.

Composition implementation and endpoint boundary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Resource 1.25 adds ``resource.relation``. Both ends are resource identities;
business adapters may display components, rooms, machines or peripherals.
``contains`` records physical containment and ``depends_on`` an operational
dependency. Each relation has an inclusive UTC start and exclusive UTC end;
an empty bound is unbounded, preserving an unknown legacy start when needed.
``resource.relation._get_domain_live_relations(at, relation_type)`` selects the edges live at
a moment; reading their members applies the caller's company and read
permissions, and nothing traverses or reserves them implicitly.

Containment permits one physical parent per member at a time. Dependencies
permit several parents, while duplicate overlapping edges are rejected. Each
type rejects cycles only when all edges share an overlapping time interval.
Graph edits lock the existing weakly connected components, including hidden
and archived edges, and touch the identity tuples for repeatable-read retries.
This serializes competing edits even when the new edges have disjoint endpoints.
Mutating a relation requires relation permission and write authority on both
endpoint resources; membership grants no authority over either resource.
Changing a resource's company also validates incident relations.

Close a relation with ``date_end`` to preserve earlier membership. Archiving a
relation disables it, including historical queries; use that for corrections.
Resource archiving and copying do not replace member identities or copy edges.
The asset adapter projects ``resource.asset.parent_id`` and ``child_ids`` from
current containment. Searching the asset parent uses the same relation and
asset access rules. Reparenting closes the old interval and opens a new one;
future planned membership remains in place. Asset editors need write authority
on the component and both affected assets. This authorizes a scoped relation
change without granting general resource editing rights. A non-asset parent
has an empty asset projection; clearing that projection leaves its membership
alone. Assets participating in relation history must be archived rather than
deleted.

Before the fold into ``resource``, ``resource_asset`` 1.12 moved stored parent
links, including archived components, into containment records with unknown
starts. It preserved resource IDs and removed the redundant parent column from
the root and physical subtype tables. Existing matching resource history was
retained; conflicting history aborted the upgrade for reconciliation.
The endpoint tree remains separate: its edges can represent several endpoints
on one physical asset and therefore cannot be copied blindly into containment.
``resource.assignment`` cannot already serve as that relation: its holder must
be a human resource and its roles describe custody. Asset part installation
also records products and serials that need not have independent resource
identities; those rows must not all become resources automatically.

An assembly can therefore have several independent resource members without
merging their identities or duplicating their scheduling data. Operational
consumers resolve relations for the relevant moment and translate the resulting
resource IDs at their business boundary.

Composition itself grants no edit authority over members and does not add their
capacities or automatically reserve them. Scheduling policy must explicitly
select the members needed for a job and claim their capacity. Maintenance may
explicitly affect those members' availability. Physical containment, temporary
installation and operational dependency may require different relationships;
multiple membership and effective dates must be decided before choosing a
single-parent tree as the generic storage model.

``device_resource`` bridges endpoints to optional material ``resource_id``
references. It installs automatically when device and resource are present,
without adding inventory, accounting or asset dependencies. It does not use
``mixin.resource``: that mixin provisions a required identity and copies a new
one, whereas several endpoints may represent one existing resource. Registering
an unrepresented endpoint creates no resource. Copying an endpoint clears its
representation; deleting or detaching it retains the represented resource.
Endpoint managers can reference resources they may read, without gaining edit
rights on them. Company compatibility applies to both endpoint edits and
resource company/type changes, including archived endpoints. A shared resource
may be represented by endpoints in several companies.

``asset_device`` retains ``own_asset_id`` as an editable asset projection of
that reference, with no independent stored identity. Its identifier vocabulary,
navigation, defaults and asset-side endpoint list remain available. Clearing
an empty asset projection does not detach a non-asset resource. Contradictory
asset/resource inputs are rejected. Represented identity, endpoint parent
structure, physical resource containment and GPS observation targets are four
separate relationships; changing one does not implicitly rewrite the others.

Upgrade ``asset_device`` to 19.0.1.4.0 together with its ``device_resource``
dependency. Existing physical asset references, including archived endpoints,
are mapped to their existing resource IDs and the redundant asset column is
removed. Missing assets, conflicting resource references and incompatible
companies abort the migration. Endpoint IDs, credentials, child structure and
GPS binding history remain intact. The bridge also supports resources that have
no asset record.

The base device integrity probe executes bounded, administrator-only checks
contributed by its extensions. Resource compatibility checks belong to
``device_resource``; GPS receiver checks belong to ``device_gps``. Sharing a
resource across endpoints is valid and is not reported as duplicate equipment.

Timezone and observations
-------------------------

Working schedules and operational dates use ``resource.resource.tz``.
``_get_local_date(moment)`` returns that resource's calendar date; callers do not
substitute the cron user or company's timezone. Multiple resources in one
company may have different local dates at the same UTC moment.

A device clock timezone is a separate fact. A PLC sending an offset-free
wall-clock timestamp needs its source clock configuration to convert that
observation to UTC. It need not match the working timezone of the resource.
GPS observation timestamps remain UTC. Display uses the viewer's timezone;
resource-based ledger dates use the resource's timezone.

GPS attachment is stored once on ``resource.resource.gps_device_id``. The
unique index spans all business representations and archived resources.
``device.device.tracked_resource_id`` is the reverse relation. Every host of
``mixin.resource`` receives a writable related device field and the shared
GPS capability when ``device_gps`` is installed. A product trace projects the
asset's attachment and inherits the same capability; it owns no attachment.

Live telemetry requires the GPS user capability and computes with the caller's
rights. Position readers preserve the caller's GPS access. Odometer readers use the
company-scoped resource odometer privilege and return an immutable value and
timestamp, never an elevated observation record. Bounded reads preserve
unknown/no-reading separately from measured values. Legacy numeric odometer
helpers retain their zero fallback for existing callers.

A device's own physical asset and the resource it observes are different
relationships. ``asset_device.own_asset_id`` identifies the device itself;
``tracked_resource_id`` identifies its observation target. Reassignment of
the target must not rewrite the device's serial number or ownership.
The asset-side device projection follows asset edit permissions. Clearing an
empty asset projection leaves a non-asset observation target alone; moving
away from such a target requires resource authority. The generic inverse also
requires resource authority, rather than granting GPS managers broad writes to
resource identity, capacity or company. Company consistency is checked from
both ends of the attachment. Resources and devices with attachment history
retain their company and are archived rather than deleted.

Employee custody of a phone and the person represented by a GPS observation
also remain distinct facts; an employee can hold several devices.

Module and repository boundaries
--------------------------------

``base`` holds the resource itself, with units of measure: everything in the ERP
can be a resource, so every database has them. Until ``base`` 1.151 they were the
``resource`` and ``uom`` modules; their widgets are ``web``'s.

* Resources: identity and operational mechanics. An asset is a resource of a
  ``resource.kind``; the kind, its identifiers, meters, odometer, components,
  custody and the Assets menu are ``base``'s, and a model extending one kind
  inherits ``mixin.resource.kind``. They need no ``mail``: ``resource_mail``
  makes resources and kind models mail threads, tracks an asset's changes and
  posts its custody hand-overs.

``odoo/addons`` owns generic infrastructure and integration capabilities:

* The ``resource_asset_*`` bridges extend assets into products, stock,
  accounting, employees, manufacturing and calendars.
* ``device`` and its transport, access, mobile, DAV and manufacturing adapters:
  endpoint capabilities. Protocol adapters remain optional dependencies.
* ``device_gps``: ingestion, validation, observations and resource tracking.
* ``geoengine`` and ``device_gps_geoengine``: generic geometry, map rendering,
  geofences and trails; scheduling and GPS do not require PostGIS themselves.
* ``asset_gps``: automatic asset ledger snapshots and asset report dimensions.
  It contains no independent device attachment or telemetry reader.
* ``asset_gps_hr`` and ``asset_gps_geoengine``: optional employee and geographic
  report dimensions. Delivery and maintenance bridges own their workflow
  decisions about consuming GPS readings.
* Generic asset accounting, documents, compliance, manufacturing, commerce,
  wallets and delivery routing remain independently installable
  application bridges.

``agromarin`` owns agricultural concepts and AgroMarin-specific rules:
``agro_surface_device_gps_geoengine`` connects GPS geography to agricultural
surfaces. ``product_asset_fuel_charge`` and its payroll/wallet bridges implement
AgroMarin's fuel recovery policy. ``project_task_device_visit`` retains the
company's agronomist visit thresholds and planning cutoff. Provider integrations
and company configuration remain there. Core modules never depend on those policy modules.

A module is justified by an optional dependency or a distinct business policy,
not by another synonym for the same fact. Consolidating behavior does not
require installing manufacturing, employees, accounting or PostGIS for every
GPS tracker. All relocated modules retain their technical names, XML IDs,
model names and routes; the configured addon paths continue to discover them.

Upgrade and temporal limits
---------------------------

``uom`` and ``resource`` folded into ``base`` in ``base`` 1.151, which refuses a
database whose ``uom`` is below 1.2 or whose ``resource`` is below 1.40.
``resource_asset`` folded into ``resource`` in ``base`` 1.150, which refuses a
database whose ``resource_asset`` is below 2.0. Such a database upgrades on a
commit before the fold first, so a database still below ``base`` 1.150 crosses
the two folds in two upgrades. The paragraphs below describe the upgrades that
preceded them.

Upgrade ``resource``, ``resource_asset``, ``device_gps`` and ``asset_gps``,
together with installed GPS report bridges. Asset GPS 1.14.0 transfers stored attachments from every
asset kind to the shared resource before removing the inherited asset columns.
Conflicting attachments abort the transaction. Resource Asset 1.11 rejects
existing identities with several owning assets before upgrading. History and
archived assets are preserved; deployment must update both repositories together.

GPS 1.14.0 creates an append-only ``resource.gps.binding`` timeline. Every
attachment change closes the previous period and records the new one in the
same transaction. Intervals are half-open: the observation at a transition
belongs to the new target. Detachment records an explicit unassigned period.
Current attachments and open periods each have database uniqueness constraints.
Business modules edit the resource attachment; public history mutation is denied.

Existing attachments, including archived resources, receive an unbounded
``legacy`` period. Its unknown start is explicit: migration preserves the old
interpretation of earlier readings and cannot recover unrecorded reassignments.
New attachments never claim observations from before their recorded start.
Upgrade the installed GPS, asset, geographic, employee and delivery bridges,
and the Agromarin fuel-charge adapter together with the resource module.

Readers resolve ownership at the observation timestamp. Delayed GPS messages
therefore retain their historical target without modifying telemetry storage or
FDW source schemas. Summary, speed, stop and map dimensions use those periods;
window calculations stop at attachment boundaries. Historical asset navigation,
delivery tracks and fuel calculations remain available after detachment. Live
speed, ignition and fuel snapshots reject a device's last reading when it belongs
to a previous target or lies in the future. Connection and battery indicators
remain facts about the currently attached hardware.

Custody is a separate timeline. ``resource.assignment`` provides a shared SQL
projection matching its current-holder lookup: the latest-started active role
wins an overlap, with the record ID breaking ties. A temporary assignment can
end and reveal an older still-open role. Composition intersects those effective
roles with GPS attachment periods before filtering selected holders. Business
adapters translate the resulting resource identities to operators or employees.
Inactive assignments cannot terminate the current holder's custody.

The rolling GPS summary and stored stop rows are invalidated by attachment or
resource timezone changes. Their next cron rebuild can include settled history;
the normal trailing window alone is insufficient. Historical periods use the
resource's configured working timezone; timezone configuration and device
calibration are not themselves effective-dated. Observation provenance retains
the source device and timestamp; this is query-time attribution, not a frozen
copy of every historical business label.

``resource.gps.binding._custody_query`` owns the SQL intersection of attachment
and effective roles. Its recordset adapter applies access checks and returns
immutable periods; SQL view adapters constrain their identities and company.
Attendance-based trip reports, fuel charging and company visit reconciliation
use this projection rather than repeating interval mechanics. Daily and weekly
visit evidence is clipped to
owned periods, including temporary holders and archived vehicles. A one-point
parcel entry remains a drive-by; it does not become proof of never entering.

GPS parcel replay lives in ``device_gps_geoengine`` and shares the live tracker's
proximity and silence settings. It requires manager authority, respects device
and parcel companies, and preserves ongoing visits. The generic replay wizard
uses a selected calendar timezone. Agromarin's thin wizard adapter retains its
legacy model, action IDs, vehicle vocabulary and Mexico calendar policy;
planning cutoffs and visit verdict thresholds remain in the company module.
Trip reports have company-scoped access and include all available attendance
history, with no company rollout date embedded in the generic query. Distances
exclude odometer readings marked invalid and observations outside the owned
period.
Client-visit asset/operator dimensions resolve at arrival, and preceding trip
speed is bounded to that attachment and the target's working-calendar day.

Legacy ``asset_gps.privilege_read_vehicle_gps`` and its access XML ID remain
aliases of the shared resource odometer privilege, without duplicate policy.
Company training scripts live under
``agromarin/stock_fleet_trace_training/scripts/manual_review``; they are not
shipped with the generic delivery tracing module.

Maintenance adapter defaults
----------------------------

Generic maintenance plans keep fixed-date recurrence and reserve their resources
by default. Installing an asset adapter must not change those defaults for every
plan or require an asset on the shared form. Asset plan creation supplies its
completion-based cadence, optional blocking and configured duration only when
an asset is explicitly selected; caller values and context defaults take precedence.
The asset context also schedules its first occurrence one interval ahead.
Manual orders involving only assets retain the asset application's nonblocking
default, while generic resource orders retain normal reservation behavior.

Manufacturing execution identity
--------------------------------

Changing a work center's represented resource projects pending work-order
reservations onto the new identity under the shared reservation constraints.
A hard booking can reject the change atomically. A running work center cannot
be rebound: its active execution must finish first. Completed reservations
retain their execution identity when the station is rebound and when their
dates are subsequently corrected. Composition changes do not rebind the station
or implicitly move bookings onto its members.
The manufacturing 2.14 upgrade reconciles dated work orders awaiting execution
through the same projection engine, leaving running and completed claims intact.

Resource deletion and history
-----------------------------

Operational history keeps its resource identity even after reservations,
assignments or relations are archived or ended. Resources with that history
must be archived rather than deleted. Reservation foreign keys restrict deletion
instead of clearing the identity. This also protects deletion through owning
business models, such as an employee whose unlink releases its resource.
Resources without history can still be deleted subject to ordinary references.

Reservation occupancy projections
---------------------------------

``resource.resource._get_reservation_status`` returns current occupancy and the
next reservation start for a batch of visible resources at a UTC instant.
Intervals include their start and exclude their end; unscheduled, inactive,
ended and zero-allocation claims do not occupy a resource. A partial allocation still
counts as reserved. Capacity headroom and working-calendar availability remain
separate calculations.

The summary includes private claims after checking access to each resource,
without returning booking identities, names or owners. Room adapters project
these facts into their availability and next-booking vocabulary. They retain
their existing kiosk and calendar-event behavior.

Room kiosk capabilities apply only to resources currently owned by a room.
Rebinding a room initializes its replacement resource's kiosk; old links stop
authorizing access even when reservation history keeps the old resource active.
Historical bookings retain their original resource identity.

``resource.reservation._get_domain_occupancy`` owns the selection of scheduled,
active, positive claims with a nonempty duration over optional half-open UTC
bounds. Zero-duration milestones remain valid records but do not occupy time.
It builds a domain without granting access to records. The generic occupancy
summary and the room's private-block projection share it; unscheduled claims
never become dated kiosk blocks, and private block labels remain ``Unavailable``.

Booking-load and reservation-interval batches use the same occupancy selection.
An enforced reservation with no allocated capacity cannot remove working time.
Empty hard claims neither impose a ceiling on other bookings nor prevent their
own creation in a window that permits warning-only overbooking.
Conservative calendars still subtract enforced positive reservations; callers
using capacity-aware scheduling retain their separate capacity calculation.

Exclusive work-slot search
--------------------------

``resource.models.utils.find_available_interval`` searches forward or backward
for a span containing a requested elapsed working duration. Its provider supplies
working intervals clipped to each query window and occupied intervals. The
engine normalizes endpoints to UTC, preserves claims across windows, and permits
calendar pauses inside a span while rejecting reservations and explicit blocks.
Optional earliest placement bounds are strict; duration comparison is exact.

``resource.resource._get_slot_intervals_batch`` supplies scheduled working time
and anonymous occupancy masks, grouped by each resource's current calendar.
It requires resource read access, compares bounds in UTC (including DST folds),
and exposes no private reservation records.
Every resource has a calendar: one left empty is the shared Fully Flexible
schedule, which supplies the whole window; flexible and capacity-aware
scheduling retain their separate policies. The identity-hashable
``SlotIntervals`` snapshot is local to a planning operation and keyed by resource
and calendar identity. ``_get_slot_intervals`` clips both masks to the requested
window and refreshes inputs when the identity, bounds or ignored claims differ.
Changes to claims or attendance during an operation require a fresh snapshot;
new slots planned together remain explicit blocks passed to the search engine.

Manufacturing keeps its work-center horizon, minimum one-second duration,
prefetch window and error vocabulary. Its direction adapters call the resource
engine. Slot queries obtain calendar availability before reservation subtraction
and apply their own reservation mask, so an explicitly ignored hard reservation
does not remain hidden inside calendar unavailability.
