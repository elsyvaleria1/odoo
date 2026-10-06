# GeoEngine Module Architecture

> **Version**: 19.0.1.18.0
> **Last Updated**: 2026-09-10
> **Module**: `geoengine`

## Overview

The GeoEngine module provides a complete geospatial data visualization and management system for Odoo 19.0. It extends Odoo's core functionality with PostGIS-backed geometry fields and an OpenLayers-based map view.

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Database** | PostgreSQL 18 + PostGIS 3.6 | Spatial data storage and queries |
| **Backend** | Python 3.12+ | ORM extensions, domain parsing |
| **Frontend** | OWL 3 + OpenLayers 10.10 | Map rendering and interactions |
| **Classification** | geostats + chroma-js | Choropleth and proportional maps |

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (JavaScript/OWL)                 │
├─────────────────────────────────────────────────────────────┤
│  GeoengineView → GeoengineController → GeoengineModel       │
│                          ↓                                   │
│               GeoengineRenderer + Helpers                    │
│     (GeoengineRendererLayers, Styling, Interactions, etc.)  │
├─────────────────────────────────────────────────────────────┤
│                    BACKEND (Python/Odoo)                     │
├─────────────────────────────────────────────────────────────┤
│                      Base Mixin                              │
│      (get_layers(), aggregates, _get_default_map_extent)    │
├─────────────────────────────────────────────────────────────┤
│  GeoField Classes        │     Domain System                │
│  (GeoPoint, GeoPolygon,  │  (GeoDomain, spatial SQL,        │
│   GeoLine, Multi*)       │   DomainOperator enum)           │
├─────────────────────────────────────────────────────────────┤
│                Layer Configuration Models                    │
│        GeoVectorLayer       │      GeoRasterLayer           │
├─────────────────────────────────────────────────────────────┤
│                   PostGIS (PostgreSQL Extension)             │
│      GEOMETRY columns, GIST indexes, ST_* functions         │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
geoengine/
├── __manifest__.py          # Module metadata, dependencies
├── __init__.py              # Package initialization
├── ARCHITECTURE.md          # This file
│
├── models/
│   ├── __init__.py
│   ├── base.py              # Base mixin with get_layers() RPC
│   ├── fields.py            # GeoField classes (GeoPoint, etc.)
│   ├── geo_types.py         # Enums, type aliases, constants
│   ├── geo_domain.py        # Domain operator optimization
│   ├── geoengine_vector_layer.py  # Vector layer model
│   ├── geoengine_raster_layer.py  # Raster layer model
│   ├── ir_ui_view.py        # View extension for geoengine type
│   ├── geoengine_view_settings.py  # Per-view map settings
│   ├── ir_model_fields.py   # Field registry extension
│   └──│
├── static/src/
│   ├── geoengine/
│   │   ├── geoengine_view.js       # View registration
│   │   ├── geoengine_controller.js # Controller component
│   │   ├── geoengine_model.js      # Data model (extends RelationalModel)
│   │   ├── geoengine_renderer.js   # Main renderer
│   │   ├── geoengine_arch_parser.js # XML parser
│   │   └── renderer/
│   │       ├── geoengine_renderer_layers.js
│   │       ├── geoengine_renderer_styling.js
│   │       ├── geoengine_renderer_interactions.js
│   │       ├── geoengine_renderer_utils.js
│   │       ├── geoengine_renderer_trails.js
│   │       └── render_strategies.js
│
├── security/
│   ├── res_groups.xml       # User/Admin groups
│   └── ir.access.csv        # Model access rights
│
├── views/
│   ├── geo_vector_layer_view.xml
│   ├── geo_raster_layer_view.xml
│   ├── ir_model_fields_views.xml
│   ├── ir_ui_view_views.xml
│   └── geoengine_menus.xml
│
├── wizards/
│   ├── geo_trail_wizard.py
│   └── res_config_settings.py
│
├── tests/
│   ├── common.py            # Test fixtures, mixins
│   ├── test_geo_fields.py   # Field conversion tests
│   ├── test_geo_domain.py   # Domain parsing tests
│   └── test_coordinate_transform.py
│
├── data/
│   └── ir_config_param_data.xml
│
└── i18n/
    └── (translations)
```

## Core Components

### 1. GeoField Classes (`models/fields.py`)

Custom Odoo field types that store PostGIS geometry data:

| Field Type | PostGIS Type | Use Case |
|------------|--------------|----------|
| `GeoPoint` | POINT | Locations, POIs |
| `GeoLine` | LINESTRING | Routes, paths |
| `GeoPolygon` | POLYGON | Areas, boundaries |
| `GeoMultiPoint` | MULTIPOINT | Multiple locations |
| `GeoMultiLine` | MULTILINESTRING | Route networks |
| `GeoMultiPolygon` | MULTIPOLYGON | Complex regions |

**Key Methods**:
- `convert_to_column()` - any value → EWKB hex in the field's SRID and dimension
- `convert_to_cache()` - the same EWKB hex, so cache and column agree
- `convert_to_record()` - Cache → Shapely geometry for Python
- `convert_to_read()` - Geometry → GeoJSON for API/frontend
- `update_db_column()` - Create/validate column + GIST index

### 2. Spatial Operators (`models/geo_domain.py`, `geo_types.py`)

Domain operators for spatial queries in Odoo domains:

```python
# Example domain expression:
[("location", "geo_intersect", some_polygon)]

# Distance-based query:
[("location", "geo_dwithin", {"geometry": point, "distance": 1000})]
```

**Available Operators**:

| Operator | PostGIS Function | Description |
|----------|------------------|-------------|
| `geo_intersect` | ST_Intersects | Geometries share space |
| `geo_contains` | ST_Contains | First contains second |
| `geo_within` | ST_Within | First within second |
| `geo_touch` | ST_Touches | Touch at boundary |
| `geo_equal` | ST_Equals | Topologically equal |
| `geo_overlap` | ST_Overlaps | Partial overlap |
| `geo_covers` | ST_Covers | First covers second |
| `geo_covered_by` | ST_CoveredBy | First covered by second |
| `geo_disjoint` | ST_Disjoint | No common space |
| `geo_crosses` | ST_Crosses | Cross each other |
| `geo_dwithin` | ST_DWithin | Within distance |

### 3. Layer Configuration Models

**GeoVectorLayer** (`geoengine_vector_layer.py`):
- Defines how to render feature data on the map
- Classification: `unique`, `quantile`, `interval`, `custom`
- Representations: `basic`, `colored`, `colored_field`, `proportion`, `heatmap`, `cluster`
- Render engines: `auto`, `canvas`, `webgl`

**GeoRasterLayer** (`geoengine_raster_layer.py`):
- Background map layers (OSM, satellite, etc.)
- Tile sources: `osm`, `xyz`, `wmts`
- Visibility and opacity controls

### 4. Frontend Architecture

**GeoengineModel** (extends RelationalModel):
- Manages standard Odoo data + geo-specific data
- Layer data caching with LRU eviction
- Classification computation (choropleth, proportional)
- Parallel data loading for multi-model scenarios

**GeoengineRenderer**:
- OpenLayers map initialization
- Layer creation and styling
- Feature interactions (click, hover)
- WebGL acceleration for large datasets

**Layer configuration** is state of the model instance (`model.layers`, set by
`get_layers()`), read by the renderer and the layers panel through the reactive
model prop; a toggle or reorder in the panel is seen by the map with no event
bus in between.

## Performance Optimizations

### 1. N+1 Query Prevention

`get_layers()` uses batch fetching:
```python
# BEFORE: N+1 queries
for layer in view.vector_layer_ids:
    layer.read()[0]  # 1 query per layer
    self.env["ir.model.fields"].browse(...)  # More queries!

# AFTER: a fixed number of queries regardless of layer count
rows = layers.read(_VECTOR_LAYER_FIELDS)
(layers.geo_field_id | layers.attribute_field_id | ...).fetch(["name"])
layers.model_id.fetch(["model"])
```

Measured 2026-09-09 over the six demo views: 12-18 queries on a cold cache and
4-8 warm, the warm floor being the view, its two layer lists, the config
parameter and the company country. Cross-model layers no longer add one
`search_count` each (19.0.1.17.0).

### 2. LRU Caching

Classifications are cached in core's `LruCache` (`classificationCache`, 50
entries), keyed by the layer configuration and a fingerprint of the data.
Layer rows are not cached: every root load re-prepares them from the records
the framework just loaded.

### 3. Parallel Data Loading

Multi-model scenarios load all views and data in parallel:
```javascript
// Phase 1: Load all views in parallel
await Promise.all(viewLoadPromises);

// Phase 2: Fetch all layer data in parallel
await Promise.all(dataPromises);
```

### 4. Deduplication

Identical parallel fetches share one RPC call:
```javascript
if (this.inflightFetches.has(cacheKey)) {
    return await this.inflightFetches.get(cacheKey);
}
```

### 5. WebGL Rendering

Large datasets (>1000 features by default) use WebGL:
- Hardware-accelerated rendering
- Significant performance improvement for point layers
- Configurable threshold per view

## Security Model

### Groups

| Group | Permissions | Implied By |
|-------|-------------|------------|
| `group_geoengine_user` | Read layers | `base.group_user` |
| `group_geoengine_admin` | Full CRUD | `base.group_erp_manager` |

### Access Rights

- Vector/Raster layers: User=Read, Admin=Full
- Setup/Trail wizards: User=CRUD (transient)
- ir.model/ir.ui.view: User=Read (required for layer config)

Note: The module uses model-level access control. Record-level rules could be
added to restrict layer access by company or other criteria if needed.

## Configuration Parameters

Seeded in `data/ir_config_param_data.xml`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `geoengine.default_map_extent` | (auto) | Default map extent bounds |
| `geoengine.default_map_zoom` | (seeded) | Default zoom level |
| `geoengine.validate_geometry` | True | Enable geometry validation |
| `geoengine.max_geometry_size` | 1000000 | Max geometry size (bytes) |

Read from code with a fallback default (not seeded):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `geoengine.default_srid` | 3857 | Default spatial reference |
| `geoengine.auto_repair_geometry` | True | Auto-repair invalid geometry via `make_valid` |
| `geoengine.tile_timeout_ms` | 4000 | Time budget of one vector tile or tiled-layer extent query |

## Testing

```bash
# Run all geoengine tests (tests/ holds the current list)
./odoo-bin -u geoengine -d test_db --test-enable --test-tags /geoengine --stop-after-init

# Run the DB-backed audit suite (PostGIS): reprojection, geo_extent, SRID
# migration, GeoJSON-on-write, spatial search, get_layers query count, wizard ACL
./odoo-bin -u geoengine -d test_db --test-enable --test-tags geoengine_audit --stop-after-init
```

Note: most test classes are untagged, so `--test-tags geoengine` (no leading `/`)
matches nothing; use `/geoengine` to run the whole module, or `geoengine_audit`
for the tagged DB-backed audit suite (`test_audit_db.py`,
`test_setup_wizard_access.py`).

**Test Coverage** (`tests/`): geo field conversion/validation, operator SQL,
domain parsing, coordinate transforms, make_valid, vector/raster layer config,
view validation, GeoJSON I/O, spatial aggregates, plus the DB-backed audit and
setup-wizard-access suites.

## Extending GeoEngine

### Adding a New Geo Field Type

```python
# In your module's fields.py
from odoo.addons.geoengine.models.fields import GeoField


class GeoGeometryCollection(GeoField):
    type = "geo_geometry_collection"
    geo_type = "GeometryCollection"
```

### Creating a Custom Vector Layer

```xml
<record id="my_vector_layer" model="geoengine.vector.layer">
    <field name="name">My Custom Layer</field>
    <field name="view_id" ref="my_geoengine_view"/>
    <field name="geo_field_id" ref="field_my_model__location"/>
    <field name="classification">quantile</field>
    <field name="nb_class">5</field>
</record>
```

### Adding Custom Render Strategy

```javascript
// In your module's static/src/render_strategies.js
class CustomStrategy extends RenderStrategy {
    createLayer(layerConfig, data, styling) {
        // Custom implementation
    }
}
```

## Changelog

### Version 19.0.1.18.0 (2026-09-10)

**The map settings left `ir.ui.view`.** Eleven columns (projection, both
extents, zoom, render engine, WebGL threshold, five control toggles) sat on
every view row in the database, defaults and all, and three constraints ran
on them guarded by `type == 'geoengine'`. They are `geoengine.view.settings`
now: one row per geoengine view that departs from the defaults, `view_id`
unique with cascade, the same three constraints without the type guard, and a
constraint that the view is a map. `ir.ui.view` keeps the type, the two layer
one2manys and a computed `map_settings_id` (with an inverse, so the view form
can pick or create one); `_map_settings()` answers a defaults-only `new()`
record for a view with no row, so `get_layers()` reads one object either way.

Migration `19.0.1.18.0/post-migrate.py` copies the columns into the table for
every geoengine view, coalescing to the field defaults, then drops them. Each
moved row gets a `noupdate` xmlid derived from its view's (`map_settings_` +
the view's name, in the view's module): module data that declares the same
settings, as `geoengine_demo` does for the retail-machine map, then updates
the row instead of colliding on the unique `view_id`, and a row the module
does not declare is not pruned as orphan data on the module's next update.
The first version of the migration gave the rows the view's own `noupdate`,
and a demo reload pruned five of six; that is why the flag is forced.

Replayed on a database built from the previous commit with the demo data:
six views moved, eleven columns dropped, six `noupdate` xmlids, the retail
map's zoom 9 and extents intact, 332 tests green, and a further demo update
leaving all six rows in place.

**Also in this version**: the vector and raster layer suites test a registered
fixture instead of whichever geometry field installed first (twelve silent
skips gone); the trail wizard stores its results once (`trail_ids` is the
One2many over `wizard_id`, the count is computed, the map action forwards no
context, the `ir.ui.view` binding is gone); a view refuses a
`features_list_field`, `features_list_group_by` or `default_order` naming no
field; `i18n/es.po` covers every msgid; the class-values fingerprint hashes
every value; and the `get_layers` reader contract requires a property or key
access rather than a word.

**Structure**: the layers panel and the features list take callbacks and an
`archInfo` prop instead of the renderer instance; the classifier left the
model for `layer_classifier.js` (the model is 800 lines about loading, the
classifier 354 about classes); the raster and trail builders left
`geoengine_renderer_layers.js` for `raster_layers.js` and `trail_layer.js`
(268 / 335 / 275 lines). Nothing behavioural changed in those three; each
was re-driven in the browser after the move. (The body of commit 0a8b7bc92
states the harness at 270; it read 273.)

**Also**: `models/ir_actions.py`, which added `geoengine` to
`ir.actions.act_window.view.view_mode` by `selection_add`, is gone. Core
commit `74537ec7364` derives that selection from `ir.ui.view.type` at call
time, so the extension had become both redundant and fatal (`selection_add`
on a callable selection raises at registry load).

### Version 19.0.1.17.0 (2026-09-10)

Seven commits from one investigation that questioned every claim of the six
audits above and drove each finding in a real Chrome or a real PostGIS
database before fixing it. What was measured:

- **The map never re-rendered after its first paint.** A search narrowing the
  retail-machine demo to one record left all 491 features drawn; an external
  write followed by `root.load()` or `model.load()` left the point where it
  was. The renderer's effect fired on a fresh, empty `root.data`,
  `renderVectorLayers` returned early on zero layers, and the later
  `vectorLayers` assignment mutated the same object. Layers are prepared from
  an `onRootLoaded` listener with the root threaded through and published as
  one new `root.data`; the superseded-root guard compares through `toRaw`,
  because the listener closes over the raw model while `load()` runs through
  the reactive proxy. Every reload now redraws; the view fits once and then
  keeps the user's viewport.
- **Edit mode could select nothing**: the Modify filter was `!feature.get("model")`
  from before every layer carried a model key.
- **A record value could inject HTML into every viewer's legend** through
  geostats' `getHtmlLegend`; the legend is built from data with escaping.
- **`geo_equal` was coordinate-order equality in SQL and topological in
  memory**; a bad geometry was a server error rather than a validation error;
  plain users could not classify a layer (two unsudo'd `ir.model.fields`
  reads); the 1.4.0 migration used `IN %s` with a tuple and could not run on
  psycopg 3.
- **A geofence moved 11 000 km on a type-only write** in
  `device_gps_geoengine`, which patched the field's SRID with raw SQL instead
  of labelling the value; `geo_dwithin` in metres seq-scanned a projected
  field and now carries an indexable `&&` prefilter.
- **Cross-model popups showed whichever own record shared the id**, and every
  foreign layer loaded 10 000 rows it then filtered its own query by; a saved
  layer edit was patched client-side. `relatedModels` holds the foreign arch,
  rows carry the foreign template's fields, and `reloadLayerConfigurations()`
  re-reads `get_layers`.
- **Canvas styles are cached per key** instead of allocated per feature per
  frame (491 points: one Style object; a labelled layer: one per label); one
  colour helper replaces three; the hand-rolled LRU is core's; the map-dialog
  layer form is an inherited view rather than a copy; three domain parsers
  are one.
- **The lat/lon, GeoJSON-text and partner coordinate modes are gone**: parsed,
  fetched, validated, documented, and drawn by nothing.
- **An import says when it assumed the coordinate system** (shapefile with no
  readable `.prj`, GeoPackage with no usable `srs_id` and no blob SRID), and a
  many2one property round-trips by name instead of being dropped.
- **The info-box popup is a keyed child of the renderer's template**, not a
  second Owl `App` mounted and destroyed by hand.
- **The `geo_layers` service is gone**: the layer configuration is state of
  the model (`model.layers`), read by the renderer and the panel through the
  reactive model prop.
- **The setup wizard is gone**: settings carried the same three fields, and its
  one distinct action, creating the missing spatial indexes, sits beside
  "rebuild" there, sharing one enumeration and one DDL loop.
- **`is_wms`/`is_wmts` are gone** (the form names the raster type), and
  box-select works on a WebGL map, where there is no click Select to borrow a
  collection from.
- **An end-to-end HOOT suite** mounts the real renderer over a real OpenLayers
  against a mocked `get_layers` and counts what is on the map: first paint,
  narrowing load, root reload, panel toggle. The frozen map above could not
  have survived it.

Verified: geoengine 332 Python tests and device_gps_geoengine's suite, 0
failed; `@geoengine` HOOT 115 passed on a cold bundle; machine_doc_v1 harness
269 passed; every browser claim re-driven after the fix. The investigation
note is `agromarin-knowledge/research/2026-09-09-geoengine-improvements.md`.

### Version 19.0.1.11.0 (2026-08-09)

Audit campaign. Every claim below was reproduced against a real PostGIS database
and a real headless Chrome before it was fixed — a first read-only pass produced
a list of suspicions, and a second pass wrote a test per suspicion designed to
*falsify* it. **Two suspicions did not survive that, and one of them was
backwards**: chasing it found a worse defect than the one alleged. What follows
is what was measured.

**The canonical CRS reader was reading the wrong number.** A GeoJSON 2008 urn is
`urn:ogc:def:crs:<authority>:<authority version>:<code>`, and
`_srid_from_crs_member` searched for `EPSG:(\d+)` anywhere in it — so
`EPSG:6.6:4326` answered **6** and `EPSG:8.9:32614` answered **8**. Neither is a
real SRID, so writing such a geometry raised
`pyproj.CRSError: crs not found: EPSG:6` out of `convert_to_cache`: an unhandled
500 on an ordinary `create()`, for a valid document. Had a version number ever
collided with a real code, the geometry would have been silently reprojected from
it instead. The docstring claimed it "accepts both spellings OGC ever used"; the
code is anchored at the end of the string now, and a table-driven test walks
every spelling. `geo_io_wizard._get_srid` — a second, simpler implementation
that happened to be *correct* — is deleted in favour of this one.

**The layers panel was wired to the wrong model.** `vectorModel` was
`props.model.root`: the view's own record list, of partners or parcels, not of
layers. Two of its three uses were persistence paths, and both were broken.
Reordering wrote nothing at all — core's `resequence` matches on the datapoint id
(`"res.partner_3"`) and was handed a layer's database id, so it returned before
issuing anything, and a drag was undone by the next reload. Editing a layer's
filter threw for an administrator every time: `TypeError` from `Record._update`
when a business record happened to share the layer's id, and on `undefined`
otherwise. Both now write to `geoengine.vector.layer` directly, and the prop is
gone. (The first draft of this entry claimed the reorder could renumber business
records. Driven in a browser against a model with a `sequence` column and a
colliding id, it cannot — that claim was wrong and is retracted.)

**Every geoengine view was loading its own model twice.** `get_layers()` always
fills a layer's `model` key, falling back to the view's own, so
`_prepareVectorLayers`'s `"__main__"` sentinel was never a group key and PHASE 1
built a second `RelationalModel` over the view's *own* model with `domain: []`
and `limit: 10000`. Measured on a view whose arch says `limit="5"`: two searches,
one at 5 and one at 10 000, on every map open — the second ignoring the arch
limit, the search domain and the pager. One map open now costs one `get_views`,
one `web_search_read` and one `get_layers`.

**`get_layers()` sent 43 columns per layer**, because `search_read` was called
with no field list: both audit users, both audit dates, every layer's raw
`model_domain`, and two non-stored computes — one of which ran a 1000-record
search and a `mapped()` *per layer, per map open*. A cross-model choropleth over
3000 rows cost 22 queries and 14 ms where 7 and 2 ms would do. The columns are
named now, and `test_get_layers_contract` holds the per-layer keys to the rule it
already held the top-level ones to: everything sent has a reader. `_count_values`
counts in the database; the distinct case GROUPS rather than `COUNT(DISTINCT)`,
because the latter drops NULL while the client sees an unset Integer as 0.

**Security**: installing geoengine granted **every internal user** read on
`ir.ui.view` and `ir.model` — `group_geoengine_user` is implied by
`base.group_user`, and stock Odoo grants neither. Measured with a fresh plain
user: the full arch of every view in the database, with its domains, its
`button type="object"` method names and its `groups=` gating. Both moved to the
admin group. The map never needed them: `get_layers()` already resolves field and
model names with `sudo()`, and said so in a comment.

**Configuration that reached nothing, or the wrong thing**:

- `COUNTRY_EXTENTS` was keyed `"UK"`. `res.country.code` is ISO 3166-1 alpha-2,
  so a British company was told "No predefined extent for United Kingdom" while
  the dict held one under a key nothing could match.
- Both extent fields are documented, seeded and validated as Web Mercator, and
  the client hands them to `ol.View`, which reads them **in the view's own
  projection** — one that `_check_projection` lets you set to EPSG:4326 or any of
  120 UTM zones. A 4326 view opened at −13 173 896 degrees. `get_layers` now
  reprojects both extents into the view's projection.
- A vector layer over *another* model needs a geoengine view on that model;
  without one `loadViews` raises, the browser drops the layer and logs a console
  error nobody reads. `_validate_vector_layer` reports it now, and
  `layerStatus` — which recorded every per-layer failure and was read by nothing
  — has its reader: the panel marks a failed layer.
- `_check_model_domain` reimplemented domain validation against a frozen operator
  set that had fallen behind the framework, so `any`, `not any` and `=?` were all
  refused on a layer the ORM would have executed. It asks `Domain` now.
- The raster layer's `projection` was unvalidated while the view's was not, for
  the same rule and the same reason.
- `layer_transparent` was stored, served and read by no JavaScript. Dropped, with
  a migration.

**Behaviour that changed with the feature count, and should not have**: a
choropleth lost its legend the moment it crossed `webgl_threshold`, because
`initLegend` was only reachable through `CanvasStrategy` — the same defect
19.0.1.7.0 fixed for labels, in the file next door. A proportional layer was the
only representation that never labelled. And an all-zero proportional serie was
drawn at `minSize` on WebGL and at the mid size on Canvas, because
`styling.maxValue || 100` fired before the zero-range guard.

**Other measured fixes**: unticking a layer issued a full `model.load()` — a
fresh search of every layer's data, a rebuild of every OpenLayers layer, a
re-registration of the interactions — to answer a checkbox; visibility and
stacking are now applied to the layer that is already on the map. The per-view
zoom key added in 19.0.1.5.0 had its writer moved and its reader left on the old
global `"ol-zoom"`, so the saved zoom was never restored and `getStoredZoom()`
had no caller. `_getDataFingerprint` hashed a numeric `0` as `String(0).length`,
making it indistinguishable from any one-character value. A single-vertex
`LineString` divided by zero in `_interpolateTimestamps` and gave every vertex a
NaN timestamp. The draw control picked its geometry field by enumeration order
while `updateRecord` asked the controller, so a drawn record and an edited one
could write to different fields.

**Deleted**, each verified to have no caller in geoengine or in any of the four
modules that depend on it: `openRecords` and the required `onMarkerClick` prop
the renderer never called; `state.isSavedOrDiscarded`; `clearCache()`;
`reloadLayerConfigurations()`; seven `geo_layers` service methods, two of which
said "Currently unused" in their own docstring; four trail methods; the
`on*Changed` flags stamped onto every layer config on every change; the arch
parser's `widgetNodes`; the `geoengine.vector.layer` branch in `_doLoadView`,
unreachable since the panel stopped loading that model. The arch parser's
`_detectCoordinateMode` was computed, logged and dropped from its return value
while the controller carried a second copy of the same priority chain — the
parser's answer is returned and used now. `geoKeepLast` was constructed and never
used, and `load()` genuinely had no keep-last guard, so it is wired rather than
deleted.

**A gate for the class, and what it caught immediately.** Nine of the defects
above were the same shape -- a method written, wired to nothing, left behind by
the fix that replaced its caller -- and nothing distinguishes a method with one
caller from a method with none. `tests/test_no_dead_js.py` counts how many times
each declared name appears across every source the module ships, plus the
modules that consume it, and fails when the only occurrence is the declaration.
Run once, it found three more that the manual sweep had missed, and one of them
was load-bearing:

- **The layer filter dialog had never worked.** Chasing a dead `dialogTitle()`
  getter led to `DomainSelectorGeoFieldDialog`, whose template was a `t-inherit`
  with no xpath -- a copy of the core dialog under a second name -- and whose
  extra props were aliases: the panel passed `initialValue` and `onSelected`
  where core declares `domain: String` and `onConfirm: Function`, both
  **required**. In a browser: `Invalid props for component
  'DomainSelectorGeoFieldDialog': 'onConfirm' is missing (should be a function),
  'domain' is missing (should be a string)`. The editor opened without the
  layer's current filter and Confirm called `undefined`. The panel uses
  `DomainSelectorDialog` directly now and the subclass is gone.
- `onZoomToState()` in the features list called `renderer.zoomToRecords()`,
  which never existed -- guarded by `&& this.props.renderer.zoomToRecords`, so
  clicking a group did nothing and said nothing. Implemented next to
  `zoomOnFeature`, and the button it was written for is in the template.
- `removeLegend()` was given the job it was written for: `initLegend` only ever
  added or updated, so a deleted layer left its legend on the map explaining
  colours nothing draws. `pruneLegends()` runs on every render.

**Also**: the console.error for a failed cross-model view load is a `debugLog`
now. The condition is reported properly in two places, and Odoo fails a browser
tour on any console error -- so one misconfigured layer failed every tour that
ran on that page. And `test_get_layers_contract` / the CRS round-trip test pick
a fixture whose model is still in the registry: an `ir.ui.view` or
`ir.model.fields` row can outlive its model, and both suites crashed with
`KeyError` on one left behind by another module.

**Retracted a third time**: the audit listed "dotted paths are not supported by
the geo operators" as a design gap, reasoning that
`optimize_geo_operators` reads `model._fields.get(condition.field_expr)`.
Measured: `[('zone_id.area', 'geo_intersect', 'POINT(50 50)')]` matches. Odoo's
optimiser splits the path before the operator hook sees it.

**Verified against the showcase.** `geoengine_demo` exists to exercise every
feature, which makes it the honest end-to-end check: a layer can be configured
perfectly and draw nothing, and only the renderer knows which. All five demo
maps were opened in a real browser -- ZIP (455 polygons, 6 layers), retail
machines (491 records, 9 layers), GPS devices, GPS logs and the animated trail
-- and each renders a canvas with no console error and no layer marked
undrawable. A server-side pass over every configured layer confirms the other
half: every one resolves its model and geometry field and has rows with
geometry behind it.

The WebGL legend fix was verified by counterfactual on that data. With both
classified ZIP layers pinned to `render_engine="webgl"` over 455 features
(headless Chrome reports WebGL available, and the map goes from one canvas to
two):

| | canvases | visible legends |
|---|---|---|
| with the fix | 2 | **2** |
| with the `initLegend` call removed | 2 | **1** |

The one that survives without the fix is the `unique` classification over a text
field, which cannot compile to a shader and falls back to Canvas -- exactly the
layer that was never affected. `test_audit_regressions.TestRendererParity` is
the tripwire, in the same style as the label contract 19.0.1.7.0 established.

Two things that look like defects and are not: the GPS device map draws four of
five devices because its action carries `search_default_active`, and the ZIP
view's `editable="1"` keeps its layers on Canvas under `auto` however low
`webgl_threshold` goes -- editing needs Canvas, which is the documented
priority. The demo's WebGL layer pins `render_engine` explicitly for that
reason.

**A verification that was not one.** The two commits before this reported
"`@geoengine` HOOT 133 passed" after deleting seven `geo_layers` service
methods. `tooling/hoot` keeps one dev server warm across invocations, and it
does not rebuild the bundle when a symbol *disappears* -- so those runs
exercised a bundle that still contained the deleted code. `hoot --restart` on
the same tree reported **10 failed / 123 passed**: every failure a suite
covering a method that no longer existed. The suites are removed with the
methods, `getCount()`'s two tests are restored (they had been swept up with
them), and the numbers below are from a cold bundle. Recorded in
`agromarin-knowledge/reference/dev/error-catalog.md` -- the trap is one-sided,
a warm run after a deletion can only be falsely green.

That also exposed a hole in `test_no_dead_js`: it counted a mention in
`static/tests/` as a caller, so a method whose only user is its own test read as
alive. That is exactly how those seven survived review -- two of them said
"Currently unused" in their own docstring and still had passing suites. The
haystack is production source only now, so deleting a method must take its test
with it.

**Verified**: geoengine 221 Python tests, 0 failed, 0 errors, on a clean install
and on a database carrying a stale fixture model; `@geoengine` HOOT 123 passed (cold bundle);
`geoengine`, `geoengine_demo` and `device_gps_geoengine` install together from
scratch. The frontend fixes were re-checked with the same browser tours that
found them, which now pass: dragging a layer persists its order, editing a
filter persists the domain, the filter dialog opens and confirms without props
errors, an undrawable layer is marked in the panel, one map open issues one
`web_search_read`, and a visibility toggle issues none.

### Version 19.0.1.10.0 (2026-08-09)

Configurable map controls, and two new raster types.

**The map had no Attribution control at all.** `ol.Map` was given an explicit
`controls:` array, which *replaces* OpenLayers' defaults -- and Attribution is
one of those defaults. OpenStreetMap, Esri and CARTO are all base maps this
module ships or that `device_gps_geoengine` configures, and all three require
their credit to be displayed. It is on by default, and configurable only so a
map whose sources genuinely need no credit can drop it. An absent setting reads
as **on**, so a view saved before these fields existed does not silently omit a
required credit.

- New view settings: `show_attribution`, `show_fullscreen`, `show_zoom_slider`,
  `show_overview_map`, `show_mouse_position`. Zoom, Rotate and ScaleLine stay
  unconditional. The overview map gets its own OSM layer rather than sharing
  this map's base layers -- a layer belongs to one map.
- New `raster_type` values:
  - `i_wms`, single-image WMS (`ol.source.ImageWMS`): one request for the
    viewport instead of a tile grid. Right for a server that renders labels or
    continuous symbology, where tiling cuts labels at every seam.
  - `mvt`, vector tiles (`ol.source.VectorTile` + `ol.format.MVT`): geometry
    rather than pixels, so it stays sharp at any zoom. Not marked `type: "base"`
    -- a vector tile layer is normally an overlay, and calling it a base map
    would put it in the mutually-exclusive group with OSM.
  - `is_wms` and the `params_wms` LAYERS check now cover both WMS flavours;
    left keyed on `d_wms` the new type would have saved with no LAYERS at all
    and shown none of its options in the form.
  - The `{x}/{y}/{z}` placeholder rule now covers `mvt`, which is a tile
    template like `xyz`; the WMS types take an endpoint and are exempt.

**COG/GeoTIFF was measured and rejected.** `ol/source/GeoTIFF` pulls in the
`geotiff` package: adding it took the bundle from 677 KB to **1 277 KB**, near
doubling it and undoing the whole tree-shaking win -- for a format no data in
this codebase uses yet. `entry.js` exists precisely so that cost is visible
before it is paid. Vector tiles and single-image WMS together cost 35 KB, which
is why they are here and COG is not.

The four copies of the OSM fallback layer in `_createRasterLayer` are now one
`_fallbackOsmLayer()`; two of them had already drifted apart (`opacity` with and
without its `|| 1`, one titled "Fallback Map").

**Caught by a gate, worth recording**: eslint's `no-fallthrough` rejected the
first placement of the two new `case` blocks. `case "xyz"` deliberately falls
through to `default` when it has no URL, and the new cases had been inserted
between them -- so an XYZ layer with no URL would have fallen into the
single-image WMS branch. They sit above `xyz` now. `test_get_layers_contract`
likewise refused the new `controls` payload key until it was declared with the
JS that reads it.

### Version 19.0.1.9.0 (2026-08-09)

Map tools: measure, locate, box-select, snap and export. New module
`static/src/geoengine/renderer/geoengine_map_tools.js`.

- **Measure** distance and area, geodesically. `ol.sphere.getLength/getArea`
  take the geometry back to the ellipsoid; a planar measurement on Web Mercator
  is inflated by roughly sec(latitude) -- about 1.5x at 48 degrees, 2x at 60 --
  so a parcel would read half again too large and look entirely plausible doing
  it. A live readout follows the sketch while it is drawn. Area is quoted in
  hectares between 1 ha and 1 km², because every other surface in this codebase
  is.
- **Locate** via `ol.Geolocation`, for field use on a tablet. The object is
  built on first press, not at map setup: constructing it eagerly would put a
  browser permission prompt in front of every user who ever opens a map.
  Tracking stops after one fix, and a denied permission is reported as a
  notification rather than surfacing as an unhandled OL error.
- **Box-select** with `ol.interaction.DragBox`, behind the platform modifier
  key -- a bare drag is how the map pans, and an unconditioned DragBox takes
  panning away from the user. The features are pushed into the existing
  click-`Select` collection, so the selection style and info box behave exactly
  as they do for a clicked feature. A box over many features says how many
  rather than popping up whichever happened to be first, and a clustered layer's
  wrapper source is unwrapped so box-select never returns synthetic cluster
  points.
- **Snap** (`ol.interaction.Snap`) on the editing paths, attached *after* Draw
  and Modify: Snap adjusts the pointer event as it travels down the interaction
  list, so an interaction registered earlier never sees the snapped coordinate.
  Detached when editing stops. This is the feature the interactions module's
  docstring and the machine docs had claimed for some time without it existing.
- **Export** the map to PNG. Waits for `rendercomplete` (the map draws
  asynchronously, so reading the canvas immediately yields a half-painted
  image) and composites every layer canvas, since each layer has its own.

Everything except snap is available to any user who can open the view: reading a
distance off a map is not an edit, and gating it on the admin group would have
been copying the editing tools' rule without its reason.

`teardown()` releases the interactions, overlays and position watch from
`cleanupResources`, isolated in its own try so a failure cannot abort the rest of
the teardown -- the same discipline the layer disposal already follows.

**Verified**: the geodesic claim is checked against real OpenLayers rather than
asserted -- one degree of longitude at 48N measures 74-75 km geodesically while
the planar length is more than 1.4x larger. 5 tests of the formatting, plus the
existing browser contract suite. @geoengine: 133 passed.

### Version 19.0.1.8.0 (2026-08-09)

Two new vector representations, both point-only: `heatmap` and `cluster`.

- **Heatmap** (`ol.layer.Heatmap`) with configurable radius, blur and an
  optional numeric weight field. The weight is **normalised against the layer's
  own maximum**, because OpenLayers expects 0..1 and would otherwise clamp any
  field measured in tonnes or pesos to 1 everywhere -- one flat blob that
  renders, looks plausible and means nothing. Normalising also makes the field's
  unit irrelevant, which is correct: a heatmap shows relative density. The
  weight is clamped, since the maximum comes from the data the layer was built
  with and a record can arrive after that scan (a live GPS layer does exactly
  this). No positive values at all falls back to uniform weighting rather than
  dividing by zero and painting nothing.
- **Clustering** (`ol.source.Cluster`) with distance and minimum distance.
  `createCluster` is overridden because clustering replaces features with
  synthetic points carrying none of the original properties, and the popup, info
  box and highlight all read `record` off the feature: a cluster of one keeps its
  record and behaves like an unclustered point, while a cluster of several
  carries a `count` and no record, which is the honest answer to "which record is
  this?". Marker area scales with sqrt(count), not count -- a linear radius makes
  a cluster of 100 a hundred times too loud.
- Both are decided **before** render-strategy selection: they choose the layer
  class, so the WebGL/Canvas question does not apply, and the form hides the
  engine choice for them.
- Both are refused on non-point geometry by a constraint. OpenLayers renders an
  empty layer for a polygon heatmap and reports nothing -- the silent-empty-layer
  failure this module keeps having to design out.
- `get_layers` grew a fourth `ir.model.fields` reference, so the collect and
  enrich loops now iterate `_LAYER_FIELD_REFS` instead of repeating themselves
  per field; adding the weight field is one line rather than four edits.

**Verified**: `static/tests/geo_libs_contract.test.js` is the module's first
suite to run against a *real* OpenLayers -- `ol.layer.Heatmap` builds a gradient
on a canvas in its constructor and cannot be constructed outside a browser at
all, so a mock would encode the same belief it was meant to test. It confirms
Heatmap accepts the options passed, that `createCluster` fires, and that a
cluster of one still answers which record it holds. 11 Python tests on a
registered fixture model (not on whichever geo field another installed module
happens to define -- the existing layer suite skips entirely without one), plus
6 pure tests of the weight normalisation. geoengine: 0 failed, 0 errors.

**Learned, and encoded**: an ESM live binding is live only *within* one esbuild
bundle, where the export compiles to a shared module-scope variable. Across a
bundle boundary it is bridged once, so `web.assets_unit_tests` code importing
`ol` from `geo_libs` holds the `null` from bridge time forever while
`areGeoLibsLoaded()` -- evaluated inside the module -- reports `true`. The
renderer is unaffected (same bundle; verified against the emitted bundle, where
every call site reads the shared variable directly). `geoLibs()` exists for
cross-bundle callers, and says why.

### Version 19.0.1.7.0 (2026-08-09)

WebGL draws its own labels, and `HybridStrategy` is retired.

OpenLayers 10.10 added text support to the WebGL vector renderers. That removes
the only reason the hybrid strategy existed: a labelled layer above the WebGL
threshold used to be rendered **twice** -- a WebGL layer for the geometry, plus a
whole second Canvas vector layer stacked on top carrying nothing but the text,
with its own feature loop, its own source, and its own map registration outside
the layer group.

- `webgl_style_converter` emits `text-*` flat-style properties, so a WebGL layer
  labels itself. `text-value` reads a **string** property, which is safe even
  though `colored_field`'s `["get", <Char field>]` is not: OpenLayers hands text
  expressions to `safeExpressionToGlsl`, catches a compile failure, and
  rasterises the label on a Canvas atlas downstream. A colour expression has no
  such escape and must compile. That asymmetry is why one is supported and the
  other still reports itself unsupported.
- **The two renderers had disagreed about what a layer says.** Canvas labelled
  `attribute_field_name`; the hybrid label layer fell back to `name`, then
  `display_name`, when that was unset. So the same layer labelled itself
  differently depending on how many features it happened to have. `LABEL_STYLE`
  and `labelValueFor()` are now the single answer for both.
- `display_polygon_labels` no longer forces a strategy. The auto-selector picks
  WebGL purely on feature count, and Canvas only where geometry editing is
  actually possible.
- Deleted with the strategy: `_hybridLayers`, `cleanupHybridLayers()`, the
  `isHybrid` branch in `createVectorLayer`, the deferred `setTimeout` that added
  the label layer to the map, and the `hybrid` arms of the two WebGL checks in
  the interactions module. The cleanup path was also **disposing the data layer
  twice** -- teardown step 3 already disposes every layer in
  `vectorLayersResult`, which the hybrid data layer was in.
- `hybrid` is gone from both `render_engine` selections, with a migration
  rewriting stored rows to `webgl` (not `auto`: a row saying `hybrid` was set by
  someone who wanted GPU rendering for a labelled layer, which is what `webgl`
  now means). The JS still maps the string to `WebGLStrategy`, because a view
  arch or an unmigrated database can outlive the migration and an unrecognised
  engine silently falls back to Canvas -- the slow answer, not the safe one.

**Verified**: the five style shapes the converter emits -- polygon, choropleth
`case`, unique `match`, point `interpolate`, line, each with labels and through
the highlight wrapper -- were compiled by OpenLayers' own `parseLiteralStyle`,
which is the check that would have caught the `step` regression of 19.0.1.5.0.
That check is not vacuous: the same parser rejects `step` with `unknown
operator: step`. Migration exercised on a seeded database: 1174 view rows and 3
layer rows rewritten, zero `hybrid` left. `@geoengine` 115 passed (6 new).

### Version 19.0.1.6.0 (2026-08-09)

OpenLayers 10.7.0 → 10.10.0, and all three geospatial libraries moved from
`<script>`-installed globals to ES modules.

**Libraries**:
- The libraries are now import-map externals: `ol`, `chroma-js` and `geostats`
  are bare specifiers registered in `ODOO_EXTERNAL_LIBS`
  (`odoo/tools/assets/constants.py`) and marked external to esbuild in
  `EXTERNAL_BARE_SPECIFIERS`. `static/lib/README.md` documents the layout, and
  `static/lib/versions.json` is the inventory.
- **OpenLayers is built here, not vendored whole.** The npm package ships no
  single-file ESM bundle, so `lib/ol/build.sh` bundles `lib/ol/entry.js` with a
  pinned esbuild. `entry.js` names the 44 symbols the fork uses and tree-shaking
  drops the rest: **610 KB against the 1043 KB full 10.10.0 dist, and 30% less
  than the 869 KB 10.7.0 build it replaces** — a version bump that ships less.
- chroma-js 3.1.2 → 3.2.0. The full entry point is deliberate: the `./light`
  subpath omits the colour-brewer palettes and `chroma.scale("RdYlBu")` is on the
  choropleth path, so `light` would have failed at runtime rather than at build.
- geostats stays at 2.1.0 (its last release) but is fork-modified — 4
  `AgroMarin:` markers. Two exist because module code is always strict and the
  library predates that: the UMD wrapper's `<script>` branch assigned an implicit
  global, and `getHtmlLegend()` assigned four more (`ccolors`, `lg`,
  `getcounter`, `fn`). The second is on the live choropleth-legend path and would
  have thrown `ReferenceError` on the first map with a legend. A third fixes
  `setClassManually` calling an undefined `t()` where it meant `_t()`.
- `geostats.css` was vendored and referenced by nothing — geoengine styles the
  `geostats-legend-*` classes itself. Dropped.
- LICENSE files added for all three; none was present before.

**Loading**:
- `lib/geo_libs.js` owns the load, with one dynamic `import()` per specifier,
  deduped per session. Dynamic rather than static because a top-level `import` in
  `web.assets_backend` resolves on every backend page — ~670 KB for users who
  never open a map. Verified against a running server: the eager bundle contains
  `import("ol")` and no OpenLayers code.
- The nine `/* global ol */` pragmas are gone. `geo_libs.js` exports `let`
  bindings it assigns at load time and ESM export bindings are live, so call
  sites still read `ol.layer.Tile` while eslint now resolves the name.
- `typeof window.chroma === "undefined"` guards became `areGeoLibsLoaded()`.
  Those probes asked about a global that is no longer how the library arrives, so
  left alone they would have answered "not loaded" forever, silently returning
  unstyled layers.
- `device_gps_geoengine`'s polygon dialog loaded OpenLayers by hard-coded path;
  it calls the same `loadGeoLibs()` now.

**Verified**: `CLIENT_RENDERABLE_SRIDS` re-measured against the tree-shaken
build — all 123 resolve and the seven national grids still do not, so the
`geo_types.py` contract is unchanged by tree-shaking. `@geoengine` JS suites 109
passed. Both modules install clean; the import map served on a real backend page
carries all three specifiers.

**Fixed on the way**: `device_gps_geoengine` was uninstallable on HEAD. Commit
`c55b5898` deleted `use_to_edit` from `geoengine.raster.layer` but left 24 data
records writing it, across `views/device_device_views.xml`,
`views/device_geo_fence_views.xml` and `wizards/gps_trail_wizard_views.xml`.

### Version 19.0.1.5.0 (2026-08-08)

Audit-driven correctness campaign, verified in a real browser (Playwright) and a
real PostGIS database rather than by reading.

**Correctness**:
- Choropleth layers mis-coloured in **all three** classification modes.
  `styling.values` meant three different things and one ordinal `>=` scan read
  all of them: `quantile`/`interval` held geostats' *range strings* (a numeric
  comparison against `"0 - 7395.75"` is `NaN`, so every feature took class 0) and
  `unique` held categories geostats sorts *alphabetically* (an ordering lookup
  over which is meaningless). Measured live before the fix: a 4-colour interval
  layer rendered 1 colour across 80 features; a 78-colour unique layer rendered 3.
  The contract is explicit now — see `static/src/geoengine/classification.js`.
- A WebGL choropleth threw `unknown operator: step` (OpenLayers 10.7 has no
  `step`) and took the **whole map** down with it, not just the layer. Rebuilt on
  `case`/`match`; `colored_field` reports itself unsupported (its expression
  could not compile: `["get", <text field>]` is a float against a vec4) and falls
  back to Canvas instead of failing to compile.
- One CRS contract, both ends: `_extract_srid` reads the GeoJSON `crs` member the
  module itself emits, and the draw/modify handlers label what they send. On-map
  editing was writing unlabelled Web-Mercator metres into whatever field it was
  pointed at — correct only by luck for the 3857 default, silent corruption for
  any other SRID.
- A spatial operand that cannot hold a geometry (a GeoJSON dict, raw WKB, a
  number) raises instead of degenerating to the false domain.
- The info-box OPEN button raised a server error on every click: it passed a list
  of `[id, type]` pairs where an id was expected.
- Layer drag-to-reorder scrambled the list (`dataset.id` is a string, layer ids
  are numbers, so `findIndex` returned -1 and `splice(-1, 1)` moved the last
  layer). Toggling a base map hid every overlay.

**Configuration that reached nothing**:
- `default_map_extent`, `restricted_extent`, `default_map_zoom` and the view
  `projection` are read by the map. All four were validated by `ir.ui.view`
  constraints, serialised by `get_layers()` and consumed by no code at all; the
  map hardcoded EPSG:3857 and a slice of Europe.
- The legend container was commented out of the template, so every legend was
  computed and discarded. `display_polygon_labels` had no effect on any path.
- The live-trail store had a caller in `device_gps_geoengine` that could never
  fire (wrong receiver, and a JSON string where an object was read) and no
  renderer. Both ends wired.

**Dead and duplicated code**:
- Deleted the second feature builder (`addFeatureToSource` and friends): only
  reachable if `ol.layer.WebGLVector` were missing, and it built features with a
  different shape, so which builder ran silently changed how every style function
  behaved. Deleted the strategy interface nobody called (`setupHitDetection`,
  `supportsLabels`, `supportsEditing`, `isWebGL`, `isWebGLLayer`).
- `auto` render mode could never choose WebGL for an administrator; interactions
  registered before any layer existed, so the WebGL branch never ran.
- Layers are stored per `(model, view)`, not per model — the service was
  re-creating in the browser the bug `get_layers(view_id)` had just fixed on the
  server. The map, popup and legend are reached through `t-ref`, and the saved
  zoom is per view, not one global key.
- `domainField.component` is patched rather than replaced wholesale, and the
  side features list is configured by view attributes instead of testing for a
  hardcoded model name and a field called `state_id`.

**Configuration and dead ends, second pass**:
- A geoengine view drew 80 records. `ir.actions.act_window.limit` has a column
  default of 80, so every action supplied a list-shaped limit nobody chose, and
  no map in the workspace overrode it: `dummy.zip`'s map showed 80 of 455 and
  looked complete. The arch's own `limit=` is the authority now, falling back to
  a map default of 1000, and the view says so once when it is still truncated.
- Removed `trails=` / `trail_field=`: parsed, validated with a raising
  `ValidationError`, added to `activeFields`, drawn by nothing, and used by no
  view in the workspace. A trail on a record is a line geometry -- configure a
  vector layer on the field. `webgl_trail` is a different feature and does
  render.
- `geo_engine_view_raster_action` was the **vector** layer list, defined in the
  vector view file, and the layers panel's "add a raster layer" button called it:
  asking for a raster layer showed you vector layers. Both actions renamed to say
  what they list, with a migration remapping the external ids.
- Finished the `record_values.js` consolidation (`geoengine_record.js` and the
  WebGL trail builder were the last two open-coded copies), and the
  classification fingerprint now notices a value changing, not just a record
  count changing.

**Tests** (147 -> 161, plus 31 new JS assertions): the classification contract per
mode, a guard that range strings can never be a usable `values` again, WebGL
expressions checked against the operators OpenLayers actually has, the CRS
round-trip and draw simulation against real PostGIS, and a tripwire asserting
every `get_layers()` key still has a reader.


### Version 19.0.1.1.0 (2026-06-26)

Audit-driven correctness, security, and frontend campaign (DB-backed PostGIS tests
under the `geoengine_audit` tag + browser/Playwright verification of the frontend).

**Correctness**:
- Reproject geometry to the field SRID on write/cache (was stored verbatim → silent corruption); migrate columns on SRID change instead of leaving them inconsistent
- `entry_to_shape` raises a clean Validation/Type error (was `AttributeError`); `geo_extent` aggregate returns parseable GeoJSON (was an unparseable `BOX(...)`)
- Accept GeoJSON on write (the field already emits it); repair the dynamic `{ACTIVE_IDS}` filter layers; classify proportional-symbol layers (`geo_repr` value typo)
- Warn instead of silently truncating when a spatial search hits the 50k safety cap
- `geoengine_demo`: advance `last_log_id` on tied timestamps

**Security**:
- Restrict the setup wizard to GeoEngine admins (was reachable by any internal user → `sudo` config writes + DDL)

**Frontend**:
- Activate on-map editing (wire handlers, fix the `editable` gate, reset `isModified`) and render geo fields in form/list views (new geo field widget)
- Fix the per-feature popup OWL `App` leak

**Hardening / hygiene**:
- 63-byte-safe spatial index names + per-index savepoints in the rebuild loops
- Drop the unused `bus` dependency, dead code (`_validate_layer_configurations`), and stale tokens/labels; sync docs

### Version 19.0.1.0.0 (2025-12-07)

**Improvements**:
- Optimized `get_layers()` - reduced from N+1 to 4-5 queries
- Added `geo_crosses` and `geo_dwithin` spatial operators
- Enhanced type hints throughout Python codebase
- Added comprehensive tests for operators and domains
- Created ARCHITECTURE.md documentation

**Technical**:
- Uses Odoo 19.0 patterns (models.Constraint, Command class)
- Full Python 3.12+ type hints
- StrEnum for type-safe operator definitions
