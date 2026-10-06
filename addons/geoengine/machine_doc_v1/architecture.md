# Geoengine Architecture

## Subsystem Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ir.ui.view (type=geoengine)                      │
│  projection   default_map_extent   render_engine   webgl_threshold      │
│  raster_layer_ids ──→ geoengine.raster.layer (o2m)                     │
│  vector_layer_ids ──→ geoengine.vector.layer (o2m)                     │
└──┬───────────────────────────────┬───────────────────────────┬──────────┘
   │                               │                           │
┌──▼──────────┐  ┌─────────────────▼──────────┐  ┌────────────▼──────────┐
│ GEO FIELDS  │  │     LAYER SYSTEM           │  │    DOMAIN SYSTEM      │
│             │  │                             │  │                       │
│ GeoField    │  │ Raster: osm, xyz, google,  │  │ 11 domain operators   │
│  + 6 types  │  │   wmts, d_wms, i_wms, mvt   │  │ geo_intersect, etc.  │
│ PostGIS col │  │ Vector: basic, proportion,   │  │ @operator_optimization│
│ GIST index  │  │   colored, colored_field,   │  │ → ID-based SQL       │
│ WKB cache   │  │   heatmap, cluster           │  │ Domain.custom → SQL  │
│             │  │ Classification: unique,     │  │                       │
│             │  │   interval, quantile        │  │                       │
└──────┬──────┘  └──────────────┬──────────────┘  └───────────────────────┘
       │                        │
┌──────▼────────────────────────▼──────────────────────────────────────────┐
│                         FRONTEND (JS/OWL)                               │
│                                                                          │
│  Controller ──→ Model (extends RelationalModel) ──→ Renderer            │
│  loadGeoLibs()  load() → super.load() → _prepareGeoData()              │
│  ↳ ol,chroma-js layerDataCache (LRU)   classifyLayerData()             │
│    geostats     getLayerData()         → OpenLayers map                │
│                                                                          │
│  Renderer subsystems:                                                    │
│  ├── Layers: vector/raster layer creation, GeoJSON parsing              │
│  ├── Styling: 6 modes (basic, proportion, colored, colored_field,       │
│  │            heatmap, cluster)                                          │
│  ├── Interactions: select, draw, modify (editing, admin-gated)          │
│  ├── MapTools: measure, locate, box-select, snap, export PNG            │
│  ├── Trails: time-based animation with WebGL support                    │
│  ├── Utils: coordinate transforms, geometry helpers                     │
│  └── RenderStrategies: auto/WebGL/Canvas selection                      │
│                                                                          │
│  Panels:                                                                 │
│  ├── LayersPanel: layer visibility/opacity toggles                      │
│  ├── FeaturesList: sidebar feature list                                 │
│  └── TimeSlider: trail animation time control                           │
│                                                                          │
│  Services:                                                               │
│  └── model.layers: the view's layer configuration, state of the model    │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                           WIZARDS                                        │
│                                                                          │
│  wizard.base.view.trail       Trail generation from position records          │
│  wizard.base.import.geodata      GeoJSON/Shapefile/GeoPackage, auto-detected     │
│  wizard.base.export.geodata      GeoJSON/Shapefile/GeoPackage with CRS selection │
│  res.config.settings    4 config parameters                             │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Geo Field Data Flow: WKB <-> GeoJSON <-> Shapely

GeoField handles conversion between four representations. The canonical storage
format is WKT with SRID prefix in PostGIS columns.

```
                 Python code                 ORM Cache               Database (PostGIS)
            ┌────────────────┐        ┌─────────────────┐      ┌──────────────────────┐
            │ Shapely         │        │ WKB hex string   │      │ WKT with SRID        │
            │ BaseGeometry    │◄──────►│ (compact binary  │◄────►│ "SRID=3857;POINT(..)"│
            │                 │        │  for fast parse) │      │ geometry column       │
            └────────┬────────┘        └─────────────────┘      │ + GIST spatial index  │
                     │                                          └──────────────────────┘
                     ▼
            ┌────────────────┐
            │ GeoJSON string  │
            │ with CRS meta   │───────► Web client (OpenLayers)
            │ {"type":"Point",│
            │  "crs":{"name": │
            │  "EPSG:3857"}}  │
            └────────────────┘
```

**Conversion methods on GeoField:**

| Method | Direction | Format |
|--------|-----------|--------|
| `convert_to_column(value, record)` | Python -> DB | EWKB hex carrying the field's SRID |
| `convert_to_cache(value, record)` | Any -> Cache | the same EWKB hex the column returns |
| `convert_to_record(value, record)` | Cache -> Python | Shapely `BaseGeometry` |
| `convert_to_read(value, record)` | Any -> API | GeoJSON string with `crs` property |

**Parsing pipeline** (`_parse_geometry`), a module-level function, not a method.
The SRID a value declares travels on the returned geometry (`shapely.get_srid`,
0 when none is declared), so storage and the domain operators reproject from it
instead of re-reading the value:
1. Falsy (`None`, `""`, `False`) -> `None`
2. `BaseGeometry` already -> returned as-is, with whatever SRID it carries
3. `dict` -> `shapely.geometry.shape()`, SRID from its `crs` member. A GeoJSON
   mapping is the natural Python spelling of a geometry and used to fall through
   to `None`, so a domain built with one silently matched no rows instead of raising
4. `bytes`/`bytearray`/`memoryview` -> `shapely.wkb.loads()`, SRID from the EWKB
5. Any other non-`str` -> `TypeError`. Returning `None` here is what made a
   mistyped operand indistinguishable from "no geometry"
6. From here the value is a `str`: strip whitespace, then read a `SRID=n;`
   prefix (no `;`, or a non-integer `n`, is a `ValueError`)
7. Starts with `{` -> GeoJSON string, `json.loads()` then as 3. This is the
   format `convert_to_read` emits and the OpenLayers editor posts back, so the
   field can ingest what it serves
8. An all-hex, even-length string -> WKB/EWKB; anything else -> WKT

Until 2026-10-01 only the `SRID=` prefix and the GeoJSON `crs` were honoured: an
EWKB value, or a shapely geometry carrying an SRID (every geometry read from
another field), was stored unreprojected and silently mislabelled with the
field's SRID. **Dimensions** follow the column: a Z is dropped for a 2D field and
added at 0 for a 3D one, where PostGIS used to abort the INSERT.

**Validation pipeline** (`_check_geometry`):
1. Check `geoengine.validate_geometry` config param (default: enabled)
2. If geometry is invalid and auto-repair is enabled, apply `shapely.make_valid()`
3. Check WKT byte size (`geometry_size`) against `geoengine.max_geometry_size`
   (`max_geometry_size(env)`, default 1 MB). The trail wizard simplifies a trail
   that would exceed it rather than failing on it

**Column creation** (`update_db_column`), three branches:
1. **No column** -> `create_geo_column()` -> `AddGeometryColumn()`, then the GIST
   index below
2. **Column exists and is `geometry`** -> `_sync_geometry_column()` reads
   `geometry_columns` (current schema) once: a pure SRID change is reprojected in
   place to the field's full type, Z included (the type used to lose its `Z`, so
   a 3D column came back 2D); a type/dimension change or an unknown SRID warns.
   Then the GIST index below
3. **Column exists and is something else** -> warn and `return` **without**
   indexing. `CREATE INDEX ... USING GIST` over a varchar raises *"data type
   character varying has no default operator class"*, so indexing unconditionally
   turned a warning into an aborted module upgrade

So the GIST index is created on branches 1 and 2, not "always". Name:
`{table}_{column}_gist_index`, hash-truncated past PostgreSQL's 63-byte limit --
a silently truncated name never matches `index_exists()` and re-issues
`CREATE INDEX` on every upgrade.

---

## Map View Rendering Pipeline

```
User opens geoengine view
         │
         ▼
┌─ GeoengineView.props() ─────────────────────────────────────────────┐
│  GeoengineArchParser.parse(arch)                                     │
│  → Lists the arch's PostGIS geometry fields (geoFields)             │
│  → Extracts fields, templates (info_box), trail config               │
│  → Returns archInfo with all parsed configuration                    │
└──────────────────────────────────────────────────┬───────────────────┘
                                                   │
         ▼                                         │
┌─ GeoengineController.setup() ────────────────────┤
│  1. Load libraries via loadGeoLibs() (ESM):       │
│     - OpenLayers 10.10.0                          │
│     - chroma-js 3.2.0                             │
│     - geostats 2.1.0                              │
│  2. Create GeoengineModel (extends RelationalModel)
│  3. Set up pager                                  │
└──────────────────────────────────────────────────┬┘
                                                   │
         ▼                                         │
┌─ GeoengineModel.load() ─────────────────────────┐│
│  1. Await layer configs (model.layers)            ││
│  2. super.load() — standard Odoo record loading   ││
│  3. _prepareGeoData():                            ││
│     a. _prepareVectorLayers()                     ││
│        - Group layers by model                    ││
│        - Load views in parallel (mutex per model) ││
│        - Fetch layer data in parallel (LRU cache) ││
│        - Classify data (geostats/chroma)          ││
│     b. _prepareRasterLayers()                     ││
│  4. notify() → triggers renderer useEffect()      ││
└──────────────────────────────────────────────────┘│
                                                    │
         ▼                                          │
┌─ GeoengineRenderer ──────────────────────────────┐│
│  onMounted():                                     ││
│  1. Get vectors from model.layers                  ││
│  2. Create OpenLayers map (ol.Map)                 ││
│                                                    ││
│  useEffect([model.root.data]):                     ││
│  1. renderVectorLayers() → Layers module           ││
│     - Create ol.layer.Vector per layer config      ││
│     - Parse GeoJSON → ol.Feature[]                 ││
│     - Apply styling via Styling module             ││
│     - Select render strategy (WebGL/Canvas)        ││
│  2. Fit map to feature extent                      ││
└────────────────────────────────────────────────────┘
```

**Data flow is unidirectional:** Model prepares all data (fetch + classify) in `load()`,
renderer consumes `props.model.root.data` reactively. The `useEffect` on `model.root.data`
triggers re-rendering whenever the model notifies a change (search filter, pager, etc.).

## Vector Tiles: Drawing a Whole Population

A layer whose features would be truncated is drawn as Mapbox vector tiles of
its whole population instead (`GeoengineModel._tiledLayer`): the view's own
layer when the page holds fewer records than the search matched, any other
layer when `search_count` exceeds `LAYER_DATA_FETCH_LIMIT`. A complete layer
keeps the feature path, with editing and selection. Maps in another projection
than EPSG:3857 and grouped views are not tiled; a heatmap reads its view instead
(below).

| Piece | Where | What |
|-------|-------|------|
| `get_tile(z, x, y, layer_domain)` | `models/geoengine_vector_layer.py` | Base64 MVT of the layer's population in one tile, or `too_dense` |
| `get_tile_extent(layer_domain)` | same | Web Mercator bounds of the population, to frame the map |
| `get_cell_records(cell, layer_domain)` | same | The records stacked in one fine-grid cell |
| `get_heat_cells(extent, zoom, layer_domain)` | same | A heatmap view's weighted cells |
| `tile_sql` / `render_tile` | `models/vector_tiles.py` | The tile query, run under `geoengine.tile_timeout_ms` |
| `TileStrategy` | `static/src/geoengine/renderer/render_strategies.js` | `ol.layer.VectorTile` whose loader calls `get_tile` |

The tile query is the layer model's `_search(domain)` with an `&&` envelope
condition and a projection added, so record rules, `active_test` and the
company scope apply unchanged; the geometry and every emitted field pass
`_check_field_access`. The envelope is transformed into the field's CRS after
`ST_Segmentize`, because a non-Mercator CRS bends tile edges. Points are
always counted in cells, `CLUSTER_CELLS` per tile side below
`FINE_GRID_MIN_ZOOM` and `FINE_CELLS` from it on (`count`; a one-record cell
keeps its id and values), so a tile stays bounded where records stack: 60,000
GPS fixes at one depot made 940 KiB per raw tile. Lines and polygons are one
feature per record with its id and styled values (attribute, colour, heatmap
weight). A tile that does not render within the budget is
`too_dense`: the layer status says to zoom in or narrow the search, and nothing
is drawn wrong. Pending writes are flushed before the budget's savepoint.

Clicking a coarse cell zooms in. On the fine grid a cell of several records
carries its address (`z/i/j`), and clicking it lists them
(`get_cell_records`, up to `CELL_RECORD_LIMIT`, in the model's order): zooming
in would not separate records that stack at one spot. Clicking a record reads
it (`readTiledRecord`) and opens its popup.

A heatmap cannot be tiled, because OpenLayers draws one from a single vector
source. Instead `ViewportHeatStrategy` refills that source on every view change
with `get_heat_cells(extent, zoom, layer_domain)`. These are the population's
points in the view, summed into cells of `HEAT_CELL_PX`, weighted by the heat
weight field or by count, and capped at `MAX_HEAT_CELLS`. Each cell is drawn
with the square root of its share of the densest, and a response that a later
move superseded is dropped. Tiled layers are not editable. A tiled layer holds no rows
client-side, so its classes come from the population alone: bounds from
`get_class_bounds` (interval, proportional), distinct values (unique) or
database quantiles from `get_class_quantiles`.

On a foreign table the remote side needs its own GiST index;
`device_gps_geoengine` creates it for the GPS log (`_create_remote_geo_indexes`).
Measurements (7.7M GPS rows through `postgres_fdw`) are in the knowledge
vault's geoengine vector tiles plan of 2026-10-01.

---

## Layer System

### Raster Layers (`geoengine.raster.layer`)

Background tile layers. Ordered by `sequence ASC`. Only the first non-overlay
base layer is visible on startup (prevents tile flickering).

| Type | Source | Notes |
|------|--------|-------|
| `osm` | OpenStreetMap | Default, no URL needed |
| `xyz` | XYZ Tiles | URL with `{x}`, `{y}`, `{z}` placeholders; `{0-3}` rotates subdomains |
| `google` | Google Maps | URL optional (falls back to the Google satellite template) |
| `wmts` | WMTS | wmts_layer (the GetCapabilities identifier; the translated `name` used to be sent), matrix_set, format_suffix, request_encoding, projection |
| `d_wms` | WMS, tiled (`ol.source.TileWMS`) | server_type, params_wms (JSON with LAYERS key) |
| `i_wms` | WMS, single image (`ol.source.ImageWMS`) | same params_wms; the form's WMS group and the LAYERS check cover both flavours |
| `mvt` | Vector tiles (`ol.layer.VectorTile` + `ol.format.MVT`) | Geometry not pixels: sharp at any zoom, restyleable without refetching. Deliberately **not** `type: "base"`, so it does not join the mutually-exclusive base-layer group |

### Vector Layers (`geoengine.vector.layer`)

Data layers displaying model records on the map. Each layer binds to:
- `geo_field_id` — the geometry field to render
- `attribute_field_id` — optional field for classification/sizing
- `color_field_id` — optional field for direct color values

**Representation modes (`geo_repr`):**

| Mode | Description | Requires |
|------|-------------|----------|
| `basic` | Single color for all features | Nothing extra |
| `proportion` | Symbol size varies by numeric value | `attribute_field_id` (numeric), optionally `min_size`/`max_size` |
| `colored` | Color gradient via classification | `attribute_field_id` + `classification` + `nb_class` |
| `colored_field` | Color read from a Char field | `color_field_id` |
| `heatmap` | Density heatmap (`ol.layer.Heatmap`) | Point/multipoint geo field; optionally `heatmap_weight_field_id` (numeric, normalized to 0..1), `heatmap_radius`, `heatmap_blur` |
| `cluster` | Points grouped by pixel distance (`ol.source.Cluster`) | Point/multipoint geo field; `cluster_distance`, optionally `cluster_min_distance` |

`heatmap` and `cluster` require a point or multipoint geo field --
`_check_point_only_repr` rejects them on a polygon/line field, since
OpenLayers would otherwise render an empty layer without reporting an error.

**Classification algorithms** (via geostats.js + Chroma.js):

| Algorithm | Description |
|-----------|-------------|
| `unique` | One class per distinct value |
| `interval` | Equal-width bins |
| `quantile` | Equal-count bins; at most `values - 1` classes |

There is no `custom` classification. It was offered in the selection and
documented here as "user-defined breakpoints" while nothing implemented it;
the 19.0.1.3.0 pre-migrate (since retired) dropped it and rewrote existing rows to
`unique`.

**Render engine** (per view or per layer):

| Engine | When to use |
|--------|-------------|
| `auto` | Canvas if editing is actually possible, else WebGL above `webgl_threshold` features (default 1000), else Canvas |
| `webgl` | GPU-accelerated, best for large datasets. **Draws its own labels** since OpenLayers 10.10; no on-map editing |
| `canvas` | Full feature support; required for on-map geometry editing |

`auto`'s order is: editing -> Canvas; else feature count > threshold -> WebGL;
else Canvas. **Labels no longer force anything** -- `needsLabels` is still
computed from `display_polygon_labels` but does not enter the decision, because
the WebGL renderer gained text support in OL 10.10. The `hybrid` engine that
existed to pair the two is retired, though `createRenderStrategy` still accepts
the string for rows written before the migration.

The editing test is `archInfo.editable && !config.readonly && isGeoengineAdmin`.
Testing admin-ness alone sent every layer to Canvas for anyone implied by
`base.group_erp_manager`, which made `webgl_threshold` and the whole WebGL
strategy unreachable in `auto`.

The `webgl_style_converter.js` translates OpenLayers styles to WebGL flat styles
when the WebGL strategy is selected.

### Layer Configuration Loading

```
Controller.setup()
    │
    ▼
Model.setup()
    ├── layers = {vectors, rasters}  (state of the model)
    └── _layerConfigsLoaded = orm.call(resModel, 'get_layers')
                                   │
                                   ▼
                          base.py get_layers()
                              ├── _get_geo_view()
                              ├── check_access("read") on the model
                              ├── _check_geo_view_configuration()
                              ├── read rasters (_RASTER_LAYER_FIELDS)
                              ├── _vector_layer_payload(): read vectors
                              │   (_VECTOR_LAYER_FIELDS), one fetch of the
                              │   referenced ir.model.fields, one of ir.model
                              └── _extent_in_projection() on both extents
                                   │
                                   ▼
                          GeoengineModel._setLayers(actives, backgrounds)
                              └── model.layers = {vectors, rasters}
```

The field lists are named, not defaulted: `search_read` with no field list
shipped both audit users, both audit dates and two non-stored computes, one of
which ran a 1000-record search per layer per map open. The vector payload sends
the referenced fields and model by name (`geo_field_name`, `model`, ...) and the
layer's `domain` as the server evaluates it (`uid`, `user`, `context_today`; `null` when it
cannot, `{ACTIVE_IDS}` left for the client to fill), not the
`(id, name)` tuples no client read. `test_get_layers_contract` holds every key --
top level and per layer -- to the rule that everything sent has a reader.

The layers are read with sudo, so a raster URL's API key reaches whoever opens
the map: `get_layers` therefore first checks that the caller may read the
model. Without a view id it serves the model's default view
(`ir.ui.view.default_view`: primary, by priority), the one the client opens.

The layer configuration is state of the model instance (`model.layers`), so
two geoengine views of the same model each hold their own; the renderer and the
panel read it through the reactive model prop. `layerScopeKey(resModel, viewId)`
survives only as the key of the per-view zoom in localStorage.

---

## Trail Generation Wizard Flow

```
User opens wizard.base.view.trail
    │
    ├── Select model_id (with geo fields)
    ├── Select date_field (create_date | write_date | any stored Datetime
    │       field of the model, per _selection_date_field; default write_date)
    ├── Set date_from / date_to
    ├── Choose group_by: none | day | device_id
    ├── Optional: domain filter, trail_color, width, opacity
    │
    ▼
action_generate_trails()
    │
    ├── _get_geo_fields(model) → find geo_point fields (preferred) or other geo types
    ├── _build_search_domain() → date range + safe_eval user domain
    ├── search(domain, order=date_field ASC)
    │
    ├── _generate_trails(records, geo_field):
    │   ├── group_by=none → single LineString from all coordinates
    │   ├── group_by=day → one LineString per calendar day
    │   └── group_by=device_id → one LineString per device record
    │
    ├── _extract_coordinates() → for each record:
    │   ├── Point → (x, y)
    │   └── Other → centroid (x, y)
    │
    ├── _store_trail_results() → create wizard.base.view.trail.result records
    │   └── the_trail = GeoLine(srid=4326)
    │   └── length_km computed via PyProj Geod (WGS84 ellipsoid)
    │
    └── _open_trail_map() → ir.actions.act_window for wizard.base.view.trail.result
```

---

## Import/Export Wizard Flows

### Import (`wizard.base.import.geodata`)

Accepts GeoJSON, a zipped Shapefile (`.shp`/`.shx`/`.dbf`, optional `.prj`),
or a GeoPackage (`.gpkg`, a SQLite database) -- detected from the upload's
content (zip signature / SQLite header / JSON), not the filename.
`_read_geojson()` normalizes any of the three into the same GeoJSON-shaped
dict, so everything from field mapping onward is format-agnostic.

```
1. Select target model_id
2. Upload a file (max 50,000 features; GeoJSON, zipped Shapefile or GeoPackage)
3. _onchange_file_data():
   - _read_geojson(): GeoJSON -> parsed directly; Shapefile ->
     _shapefile_to_geojson() unzips shp/shx/dbf, reads CRS from .prj;
     GeoPackage -> _geopackage_to_geojson() reads the first feature table
     via gpkg_contents/gpkg_geometry_columns, decodes each GPB geometry
     blob (_gpb_to_wkb)
   - Count features, extract available properties for preview
4. Select geo_field_id (target geometry field)
5. Configure mapping_lines (property → model field; a Shapefile's DBF
   column names, capped at 10 characters, are what appear here -- a
   GeoPackage's column names have no such cap)
6. action_import():
   - Parse each feature's geometry via shapely.shape()
   - Map properties to field values
   - Create records in target model
   - Skip invalid geometries if skip_invalid=True
```

### Export (`wizard.base.export.geodata`)

```
1. Select source model_id
2. Select geo_field_id and property_field_ids
3. Set output_format (GeoJSON, Shapefile or GeoPackage) and output_srid
   (4326 or 3857)
4. action_export():
   - Search records with domain
   - For each record: read geometry + property fields
   - GeoJSON: build a FeatureCollection
   - Shapefile: _build_shapefile_zip() -- ring winding to ESRI's
     clockwise-exterior convention (_geom_to_pyshp_parts), deduplicated
     10-char DBF field names, a .prj stating the output CRS
   - GeoPackage: _build_geopackage() -- an in-memory SQLite database
     (sqlite3 serialize()/deserialize(), no temp file) with the three
     required system tables, one feature table, and a GPB-encoded geometry
     column (_geom_to_gpb); no ring-winding step, GeoPackage's WKB carries
     no orientation requirement of its own
   - Generate downloadable binary file
```

---

## JS Architecture

### Component Hierarchy

```
GeoengineController (OWL Component)
    ├── Layout, SearchBar, CogMenu (standard Odoo)
    ├── GeoengineRenderer (OWL Component)
    │   ├── LayersPanel (layer visibility/opacity)
    │   ├── GeoengineRecord (info_box popup)
    │   └── TimeSlider (trail animation)
    └── Pager (standard Odoo)
```

### MVC Architecture

| Component | File | Lines | Responsibility |
|-----------|------|-------|----------------|
| **View** | `geoengine_view.js` | 105 | Registry entry, arch parser binding, props transform |
| **ArchParser** | `geoengine_arch_parser.js` | 352 | XML -> archInfo (fields, geoFields, webgl_trail, features list, templates) |
| **Model** | `geoengine_model.js` | 1,536 | Extends RelationalModel. Loads records + layer data + classification |
| **LayerClassifier** | `layer_classifier.js` | 354 | Held by the model; classifies a layer's rows (quantile/interval/unique, proportional) over the server-side population when available |
| **RasterLayerBuilder** | `raster_layers.js` | 335 | Held by the renderer; builds the base-map and overlay layers from raster configs |
| **TrailLayerBuilder** | `trail_layer.js` | 275 | Held by the renderer; builds the animated WebGL trail layer for `webgl_trail` views |
| **Controller** | `geoengine_controller.js` | 500 | Library loading, pager, CRUD, form dialog |
| **Renderer** | `geoengine_renderer.js` | 984 | OpenLayers map init, delegates to subsystem modules |

### Renderer Subsystem Modules

Each subsystem is a plain JS class instantiated by the Renderer in `setup()`.
They receive a reference to the renderer (`this`) for shared access to `this.map`,
`this.state`, `this.props`, etc.

| Module | File | Lines | Responsibility |
|--------|------|-------|----------------|
| `GeoengineRendererLayers` | `geoengine_renderer_layers.js` | 1,030 | Create ol.layer.Vector/Tile, load GeoJSON features, manage layer lifecycle |
| `GeoengineRendererStyling` | `geoengine_renderer_styling.js` | 562 | Style functions for 6 representation modes, legend data |
| `GeoengineRendererInteractions` | `geoengine_renderer_interactions.js` | 798 | ol.interaction.Select/Draw/Modify/Snap, feature click/hover handling |
| `GeoengineRendererTrails` | `geoengine_renderer_trails.js` | 333 | Live position trails: `addPosition()` stores a point and draws the line |
| `GeoengineRendererUtils` | `geoengine_renderer_utils.js` | 210 | Coordinate transforms (EPSG:4326 <-> EPSG:3857), overlay management |
| `GeoengineMapTools` | `geoengine_map_tools.js` | 565 | Measure, locate, box-select, snap, export PNG |
| `EditHistory`, `ProblemMarker` | `geoengine_edit_session.js` | 175 | Undo/redo of reshapes, edit keys, part counts, the marker where a drawn shape is unstorable |
| `GeoengineSpatialFilter` | `geoengine_spatial_filter.js` | 291 | Filter by place: a drawn area, the visible map or a distance from a clicked point, as search facets |
| `RenderStrategies` | `render_strategies.js` | 416 | Auto/WebGL/Canvas strategy selection, feature count heuristics, vector tiles |
| `WebGLStyleConverter` | `webgl_style_converter.js` | 364 | Convert OL Style objects to WebGL flat style format |

### Library Loading

The three libraries are ES modules, owned by `static/src/lib/geo_libs.js`:

```javascript
// geo_libs.js -- one dynamic import per specifier, deduped per session
Promise.all([import("ol"), import("chroma-js"), import("geostats")])
```

`ol`, `chroma-js` and `geostats` are bare specifiers resolved by the browser import map,
declared under the `esm.external_libs` key of geoengine's own `__manifest__.py`.
odoo's esm_registry.py merges that into the table `external_bare_specifiers()` reads,
and its esbuild.py turns each entry into an `--external:` flag. Both are named in plain
prose: they live in the odoo checkout, which this repo's CI does not have. See
`static/lib/README.md` for
how the bundles are built, and for why the two framework-side constants this paragraph
used to name no longer exist.

Consumers write `ol.layer.Tile` exactly as before, but `ol` is an imported name rather
than a global: `geo_libs.js` exports `const` stand-ins that forward every read, call and
`new` to the module `loadGeoLibs()` stored. They used to be `let` bindings reassigned at
load time, which only worked while every importer shared the facade's bundle: a bridge or
strict stub copies a module's exports once, at registration, and would have kept `null`.
A binding that never changes survives any copy. That keeps call sites unchanged while
giving eslint a name it can resolve -- the `/* global ol */` pragmas are gone.

The imports are dynamic rather than static because a static `import` in
`web.assets_backend` would resolve on every backend page, pulling ~770 KB in for users who
never open a map. Verified: the eager bundle contains `import("ol")` and no OpenLayers
code.

`GeoengineModel.setup()` starts the load and `load()` awaits it; it is deliberately NOT an
`onWillStart` hook on the controller, because OWL runs those concurrently with the model's
first `load()`. `device_gps_geoengine`'s polygon dialog calls the same `loadGeoLibs()`, and
either module can be the first to do so.

The view's own JS is in `web.assets_backend` (eager): the geo field widget has to exist in
any form or list view, not only inside the map.

---

## Coordinate Transform System

Two SRIDs are used throughout:

| SRID | Name | Usage | Units |
|------|------|-------|-------|
| 3857 | Web Mercator | **Storage default**, map display | Meters (approximate, distorted near poles) |
| 4326 | WGS84 | GPS data, GeoJSON standard, trail results | Degrees (lat/lon) |

**Server-side transforms:** pyproj throughout. `Geod` for geodesic calculations
(trail length); a cached `Transformer` (`_get_transformer`) for reprojection,
which happens automatically in two places:

- **On write** -- `_normalize_for_storage` reads the SRID the *value* declares
  (an `SRID=...;` prefix, a GeoJSON `crs`) and reprojects it into the field's
  SRID. `"SRID=4326;POINT(8.5417 47.3769)"` written to a 3857 field is stored as
  `SRID=3857;POINT (950857.69 6003812.20)`. A value with no declared SRID is
  taken to already be in the field's SRID -- there is nothing to reproject from.
- **On read** -- `convert_to_read` reprojects to `DISPLAY_SRID` (4326) when the
  field's SRID is outside `CLIENT_RENDERABLE_SRIDS`, and labels the GeoJSON with
  the SRID it actually emitted. See *What the browser can and cannot resolve* in
  conventions.md.

Storage itself is never silently reprojected: the column keeps its own SRID, and
changing it is the migration described under *Column creation* above.

**Client-side transforms:** OpenLayers handles 4326 <-> 3857 automatically when GeoJSON
includes `crs` metadata. The `convert_to_read()` method always includes `crs.properties.name`
so the frontend knows the source projection:
- If `srid=4326`: OL transforms 4326 -> 3857 for map display
- If `srid=3857`: OL uses identity (no transform needed)

**`geoengine_renderer_utils.js`** provides helper functions for coordinate transforms
in the frontend when manual conversion is needed (e.g., for trail overlays).

**Map projections beyond the built-ins:** a view or raster layer may be set to
any EPSG CRS PostGIS describes, EPSG:6372 (Mexico, ITRF2008 / LCC) for one.
`get_layers` sends `projections`, the proj4 text and area-of-use extent from
`models/projections.py`. The model registers them before the map is built
(`registerProjections`), and OpenLayers then reprojects XYZ/OSM base maps and
vector features into the view. A map outside EPSG:3857 is not tiled: its layers
take the feature path.

---

## Editing a Shape

The Draw and Modify tools ask the server, after each drawn shape and each
reshape, whether it can be stored as drawn:
`<model>.get_geometry_problem(field_name, value)` (`models/geometry_check.py`)
runs the steps saving runs (parse, reproject to the field's SRID, dimension,
validity, the field's geometry type, `geoengine.max_geometry_size`) without the
repair, and returns `{message, location}` or None. The location is in the
value's own coordinates, the map's projection, so `ProblemMarker` rings it.
Saving still repairs (`geoengine.auto_repair_geometry`): a bow-tie becomes two
triangles, which a Polygon field refuses as two parts and a MultiPolygon field
stores; the check shows the crossing in both cases. A drawn shape with a
problem opens no form.

Reshapes form an `EditHistory` of `{resId, geoField, before, after}`: Ctrl+Z
and Ctrl+Y (or Ctrl+Shift+Z, or the buttons under the tools, shown while
reshaping) write the earlier or later shape back to its record. Steps name the
record, not the map feature, because a save redraws the layers. While drawing,
Ctrl+Z or Backspace takes back the last point and Escape drops the shape.
Changing tools starts a new history.

While reshaping, three more buttons edit the selected shape's areas:
**Add an area** (a drawn polygon is joined to the shape: an overlap grows the
part it overlaps, a separate area becomes another part), **Cut an area** (taken
out of the shape; inside it, a hole) and **Remove one part** (the part nearest
the next click). `<model>.get_edited_shape(field_name, value, sketch, edit)`
(`models/geometry_edit.py`) computes the result with shapely, in the map's
projection, and refuses an edit that would leave nothing, a crossing outline or
an area edit of a line; the client writes the result as a reshape, so it is
checked and undone like one. Both Draw interactions set `stopClick`, so the
double click that ends an outline does not zoom the map.

Two more change records, not one shape, so they are not undone from the map
and clear its history: **Split** (a line drawn across the selected area;
`action_split_shape(field_name, line)` keeps the parts the line does not
cross and the largest piece on the record, and gives every other piece to a
`copy()` of it) and **Merge** (shapes shift-clicked into the selection;
`action_merge_shapes(field_name)` joins them into the first one selected and
archives the others, refusing a model without `active`). Both save the edited
record first, reload the view, and return a `display_notification`.

The Draw tool finds the view's geometry field by `geo_type`, which reaches the
client only because `_get_view_field_attributes` lists `geo_type`, `srid` and
`dim`; `get_views` sends no other field attribute.

## Spatial Search

The map's filter control (`GeoengineSpatialFilter`) turns a place into a search
facet on the view's own geometry field, which is the first vector layer of the
view's model:

| Menu item | Facet | Domain |
|-----------|-------|--------|
| Inside an area I draw | Inside the drawn area | `[(field, "geo_intersect", "SRID=<map>;POLYGON(...)")]` |
| On the visible map | On the visible map | the same, with the view's extent |
| Within 1 / 5 / 25 km of a point I click | Within N km of a point | `[(field, "geo_dwithin", {"geometry": "SRID=<map>;POINT(...)", "distance": N*1000, "unit": "m"})]` |

`createNewFilters` adds the facet, so it combines with other filters, removes
like any facet and saves into a favourite. The geometry is EWKT in the map's
projection; the server reprojects it into the field's CRS. Coordinates are
rounded to 2 decimals in metric CRSs and to 7 in degrees. While a filter
sketch or a measurement is being drawn, a click does not also open a feature's
popup or zoom into a cell (`_isSketching`).

---

## Static Maps for Printed Documents

WeasyPrint runs no JavaScript, so a report cannot embed the map view.
`models/static_map.py` draws an SVG on the server:

- **Framing:** `frame_for` picks the whole zoom at which the items fit the
  padded box; a lone point is framed `POINT_SPAN_M` wide.
- **Basemap:** the tiles that frame covers come from one XYZ server
  (`geoengine.static_map_tile_url`, OpenStreetMap by default, credited with
  `geoengine.static_map_attribution`). Each tile is cached on disk under
  `data_dir/geoengine_tiles` for `TILE_CACHE_DAYS`, and one map spends at most
  `MAP_TILE_BUDGET_S` fetching. A tile that cannot be fetched leaves a gap, and
  a map with none is drawn without a basemap and without the credit.
- **Shapes:** lines and polygons are simplified to half a pixel; points are
  drawn last, with optional labels. Every value goes in through `Markup.format`.

`BaseModel._geo_static_map(field_names=None, style=None, **options)` maps the
records' readable geo fields. A report calls it in QWeb:
`<t t-out="o._geo_static_map('the_point')"/>`.
`stock_fleet_trace_gps_geoengine` uses `render_static_map` for the trip sheet's
route: the GPS track (for users with the `view_gps_track` verb), the trip's
events, and its stops numbered with the sheet's sequence.

---

## OGC API - Features (GIS clients)

`controllers/ogc_features.py` serves OGC API - Features Part 1 (core, GeoJSON)
so QGIS, GDAL and other GIS clients can read the geometries geoengine maps draw.
The logic is in `models/ogc_features.py`, plain functions of an `env`.

| Route | Answers |
|-------|---------|
| `GET /ogcapi` | Landing page: links to the API definition, conformance and collections |
| `GET /ogcapi/api` | A minimal OpenAPI 3.0 description (`service-desc`) |
| `GET /ogcapi/conformance` | `core` and `geojson` |
| `GET /ogcapi/collections` | Every collection the caller may read |
| `GET /ogcapi/collections/{id}` | One collection, with its CRS84 extent |
| `GET /ogcapi/collections/{id}/items` | GeoJSON features: `bbox`, `limit` (default 100, at most 10,000), `offset`, `next`/`prev` links |
| `GET /ogcapi/collections/{id}/items/{fid}` | One feature (a record id) |

- **Authentication:** `auth="bearer"` with scope `ogcapi`, so a key bound to
  that scope, or to none, works; a browser session works too. In QGIS: an
  "API Header" authentication with `Authorization` = `Bearer <key>`. In GDAL:
  `GDAL_HTTP_AUTH=BEARER`, `GDAL_HTTP_BEARER=<key>`.
- **Collections** are the stored geo fields that geoengine vector layers draw,
  `<model>.<field>`, offered only where the caller may read the model and the
  field.
- **Properties** are the readable scalar fields of the model's geoengine view,
  the same ones a map popup shows. A many2one is its display name and a date is
  ISO 8601.
- **Reads** run as the caller, through `_search` and `read`, so record rules,
  `active_test` and field access apply as in the client.
- **Geometry** is CRS84 (lon/lat), transformed by PostGIS. `bbox` is
  segmentized before it is transformed into the field's CRS.
- **Budget:** each query runs under `geoengine.tile_timeout_ms`; one over it is
  HTTP 503. Extents in `/collections` get `LIST_EXTENT_TIMEOUT_MS`, because
  clients re-read that list on every connection, and an extent that takes
  longer is left out there.
- Read-only: Part 4 (transactions, editing from QGIS) is not implemented.
  `numberMatched` is not sent: counting a large table on every page would cost
  more than the page.

---

## PostGIS Integration

### Database Setup

The `pre_init_hook` (`_pre_init_postgis`) creates PostGIS extensions at install time:
```sql
CREATE EXTENSION postgis;
```

### Column Management

GeoField columns are created via `AddGeometryColumn()` (not standard `ALTER TABLE`),
which registers them in PostGIS's `geometry_columns` metadata table. This enables
PostGIS-aware tools and SRID validation.

### Spatial Indexes

Every geo field automatically gets a GIST index:
```sql
CREATE INDEX {table}_{column}_gist_index ON {table} USING GIST ({column})
```

GIST indexes enable efficient bounding-box queries that all spatial operators
(`ST_Intersects`, `ST_Contains`, etc.) rely on internally.

### Domain-to-SQL Translation

```
Odoo domain: [('geo_field', 'geo_intersect', wkt_or_geojson)]
         │
         ▼
geo_domain.py: optimize_geo_operators()
    ├── Parse geometry value (_parse_geometry)
    ├── Map DomainOperator → SpatialOperator enum
    │
    ▼
Domain.custom(to_sql=...)
    ├── _parse_srid_wkt(value) → extract WKT + SRID
    └── Generate: ST_Intersects(table.col, ST_GeomFromText(%s, %s))
         │
         ▼
Execute SQL → collect matching IDs
         │
         ▼
Return: Domain([('id', 'in', [matched_ids])])
```

The `@operator_optimization(GEO_OPERATORS, OptimizationLevel.DYNAMIC_VALUES)`
decorator resolves spatial queries to ID lists before the standard Odoo domain
engine processes them. The level is `DYNAMIC_VALUES`, not `FULL`: the operand may
be a cross-model reference (`{'other.model.geo_field': [...]}`) whose value is not
knowable at parse time, so the optimization has to run where the environment is
available.

---

## Spatial Aggregates

Four spatial aggregates are registered in `READ_GROUP_AGGREGATE` at module import:

| Aggregate | PostGIS SQL (inside `ST_AsGeoJSON(..., 15, 2)`) | Returns |
|-----------|-------------|---------|
| `geo_union` | `ST_Union(...)` | Merged geometry |
| `geo_collect` | `ST_Collect(...)` | GeometryCollection |
| `geo_extent` | `ST_SetSRID(ST_Extent(...)::geometry, MIN(ST_SRID(...)))` | Envelope polygon |
| `geo_centroid` | `ST_Centroid(ST_Collect(...))` | Center point |

Usage: `self.env["my.model"]._read_group([], ["owner_id"], ["boundary:geo_union"])`

`Base._read_group_select` builds them with `geo_aggregate_sql`, which knows the
field's SRID: PostGIS returns GeoJSON with its `crs` member, transformed to
EPSG:4326 when the field's SRID is not one OpenLayers resolves. An empty group
is `False`. `ST_Extent` streams; the former `ST_Envelope(ST_Collect())` built the
whole collection in memory first.
