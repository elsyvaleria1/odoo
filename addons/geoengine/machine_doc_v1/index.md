# Geoengine Module -- Machine Documentation v1

## Purpose

PostGIS-based geospatial framework for Odoo. Provides geometry field types
(Point, Line, Polygon, Multi*), a full map view type ("geoengine"), spatial
domain operators (geo_intersect, geo_contains, etc.), raster/vector layer
configuration, spatial aggregates for read_group, GeoJSON import/export,
trail generation, and an OWL-based OpenLayers map renderer with WebGL support.

Choropleth classification has one contract, in
`static/src/geoengine/classification.js`: `mode` says how to read `values`, and
`classIndexFor()` is the only implementation of the class lookup. Nothing else
may re-derive it -- see 19.0.1.5.0 in ARCHITECTURE.md for what happened when
three consumers each had their own idea.

## Module Metadata

| Key | Value |
|-----|-------|
| Technical name | `geoengine` |
| Category | GeoBI |
| License | AGPL-3 |
| Dependencies | `web` |
| External Python | `shapely`, `pyproj`, `shapefile` (Shapefile import/export, no GDAL) |
| External DB | PostGIS |
| pre_init_hook | `_pre_init_postgis` (creates PostGIS extensions) |
| Python lines | ~11,600 (models 3,540 + wizards 2,227 + tests 5,794 + root `__init__.py` 50) |
| JS lines (src) | ~10,060 (27 files) |
| JS lines (lib) | OpenLayers 10.10.0, chroma-js 3.2.0, geostats 2.1.0 -- all ESM, all import-map externals |
| JS lines (tests) | 1,656 (11 test files) |
| Python models | 2 new ORM + 5 extended + 6 transient |
| Views | 5 XML files (plus 4 `wizards/*_views.xml`) |
| Wizards | 4 files, 6 transient models (setup, trail + trail.result, import + import.mapping, export) |
| Test files | 23 Python + 11 JS |
| Security groups | 2 (User = every internal user; Admin). User gets **read** on the two layer models and **CRUD** on the five transient wizard models; `ir.model` / `ir.ui.view` are Admin-only |

Counts measured 2026-08-10 by `wc -l` / `grep` against the actual files -- this
table had drifted badly from code before that (stale field lists, a removed
raster type, a fabricated enum member); re-measure rather than trusting it.

The same day, a proof-based pass over all four pages (module installed, 256
tests green, claims checked against the live registry) removed a second layer of
drift that the count fix had not touched: claims describing what the code *used
to* do. A fabricated `SRID` enum and `MAX_GEOMETRY_SIZE_BYTES` constant, the
`custom` classification dropped in 19.0.1.3.0, `_validate_layer_configurations`,
a public `validate_geo_view_configuration`, a `ttype` `selection_add`,
`OptimizationLevel.FULL`, "no automatic server-side reprojection", "always
creates a GIST index", "SRID changes raise TypeError", "WebGL has no labels",
and `_check_nb_class_vs_data` counting distinct values were all wrong, and in
four cases one page already contradicted another. **When two pages here
disagree, neither is authority -- go to the code.**

## File Inventory

### Models (`models/`)

| File | Lines | Models | Purpose |
|------|-------|--------|---------|
| `geo_types.py` | 125 | -- (enums/types) | `SpatialOperator`, `DomainOperator` enums; `CLIENT_RENDERABLE_SRIDS`; `GeometryValue` |
| `fields.py` | 714 | `GeoField` + 6 subclasses | Geometry field types, WKT/WKB/GeoJSON conversion, auto-validation |
| `geo_domain.py` | 305 | -- (domain registration) | Registers geo operators with Odoo domain system via `@operator_optimization` |
| `base.py` | 443 | extends `base` (Abstract) | spatial aggregates, `get_layers()`, view validation |
| `geoengine_raster_layer.py` | 236 | `geoengine.raster.layer` | Raster layer config (OSM, XYZ, WMTS, WMS, Google) |
| `geoengine_vector_layer.py` | 715 | `geoengine.vector.layer` | Vector layer config with classification, styling, heatmap/cluster, render engine |
| `ir_ui_view.py` | 197 | extends `ir.ui.view` | `geoengine` view type, layer o2m, `map_settings_id`, view-load validation |
| `geoengine_view_settings.py` | 148 | `geoengine.view.settings` | Per-view map settings: projection, extents, zoom, render engine, control toggles (one row per view that departs from the defaults) |
| `ir_model_fields.py` | 55 | extends `ir.model.fields` | `geo_type`/`dim`/`srid`/`is_geo_field` metadata. Does **not** touch `ttype` -- see models.md |

New ORM models (2): `geoengine.raster.layer`, `geoengine.vector.layer`. Extended
models (5, via `_inherit`): `base` (Abstract), `ir.ui.view`, `ir.model.fields`,
`ir.actions.act_window.view`, and `res.config.settings` (in `wizards/`, below).

### Wizards (`wizards/`)

| File | Lines | Models | Purpose |
|------|-------|--------|---------|
| `wizard_base_view_trail.py` | 381 | `wizard.base.view.trail` | Trail generation from position records |
| `wizard_base_view_trail_result.py` | 37 | `wizard.base.view.trail.result` | One generated trail line, shown on the map |
| `wizard_base_import_geodata.py` | 553 | `wizard.base.import.geodata` | GeoJSON/Shapefile/GeoPackage import with field mapping |
| `wizard_base_import_geodata_mapping.py` | 30 | `wizard.base.import.geodata.mapping` | One property-to-field mapping line of an import |
| `wizard_base_export_geodata.py` | 468 | `wizard.base.export.geodata` | GeoJSON/Shapefile/GeoPackage export |
| `res_config_settings.py` | 162 | extends `res.config.settings` | 4 config params, create-missing and rebuild of spatial indexes, country extent auto-detect |

`res_config_settings.py` carried 16 config parameters, and the setup wizard
(removed in 19.0.1.17.0) 15 fields, until 19.0.1.3.0. Every field no code path ever read was removed
then (`default_srid`, `display_srid`, `region`, `enable_cache`,
`cache_timeout`, `max_cache_entries`, `index_buffer`, `coordinate_precision`,
`use_company_country_extent`, `auto_spatial_indexes`, `vacuum_indexes`,
`log_operations`, `monitor_cache`, `default_map_zoom`, `setup_type`,
`enable_monitoring`) -- see the comment at the top of `res_config_settings.py`.
What remains: 4 config fields (`enable_geometry_validation`,
`auto_repair_geometry`, `max_geometry_size`, `geoengine_map_extent`) plus the
two action methods; the setup wizard's 7 surviving fields are in `models.md`.

### Tests (`tests/`)

| File | Lines | Coverage Area |
|------|-------|---------------|
| `common.py` | 42 | Base test setup (test partner with geo fields) |
| `test_geo_fields.py` | 242 | GeoField conversion (WKT/WKB/GeoJSON), validation, auto-repair |
| `test_geo_domain.py` | 163 | Spatial domain operators (intersect, contains, within, dwithin) |
| `test_geo_io.py` | 233 | GeoJSON/Shapefile/GeoPackage import/export wizard |
| `test_ir_ui_view.py` | 169 | View validation (geometry field present, webgl_trail config) |
| `test_get_layers_contract.py` | 195 | Every key `get_layers()` sends (top-level and per-layer) has a reader |
| `test_ol_inventory_contract.py` | 242 | Every `ol.*` call site uses must be in the OpenLayers entry inventory |
| `test_no_dead_js.py` | 78 | Every method this module declares must be called by something |
| `test_setup_wizard_access.py` | 77 | Settings: group membership, byte semantics, spatial index actions (tag `geoengine_audit`) |
| `test_coordinate_transform.py` | 120 | SRID coordinate transformations |
| `test_make_valid.py` | 104 | Geometry auto-repair (make_valid) |
| `test_spatial_aggregate.py` | 52 | geo_union, geo_collect, geo_extent, geo_centroid aggregates |

The tests that write to fixture models (geometry storage and coercion, geo
domains and their SQL, I/O round trips, CRS contracts, map access, layers,
tiles, OGC features, trails, static maps and the query budgets) live in the
test_geoengine module, which declares those models.

### JS Tests (`static/tests/`)

| File | Lines | Coverage Area |
|------|-------|---------------|
| `geoengine_arch_parser.test.js` | 129 | View XML parsing |
| `geoengine_model.test.js` | 226 | Data model loading |
| `webgl_style_converter.test.js` | 256 | WebGL flat-style expression builders |
| `classification.test.js` | 167 | Choropleth classification contract (`classIndexFor`, class colors) |
| `geo_libs_contract.test.js` | 231 | What the code assumes about OpenLayers, checked against the real library (awaits `loadGeoLibs()`) |
| `heatmap_weight.test.js` | 46 | Heatmap weight normalization to 0..1 |
| `map_tools.test.js` | 39 | Measurement formatting (geodesic length/area display) |
| `popup_lifecycle.test.js` | 65 | info_box popup open/close lifecycle |
| `record_values.test.js` | 53 | `record_values.js` display/saved-value helpers |
| `renderer_trail_parts.test.js` | 86 | `webgl_trail` XYM line-part construction |
| `geoengine_view_e2e.test.js` | 180 | Real OpenLayers and the real renderer against a mocked `get_layers`: first paint, narrowing load redraws, root reload redraws, panel toggle |
| `geoengine_controller.test.js` | 78 | Controller chassis with the renderer stubbed: root class, search bar, mobile toggler |

### Static (`static/src/`) -- JS Architecture

| File | Lines | Purpose |
|------|-------|---------|
| **View MVC** | | |
| `geoengine/geoengine_view.js` | 70 | View registration (`geoengine` type) |
| `geoengine/geoengine_arch_parser.js` | 173 | XML arch parser (fields, geometry fields, webgl_trail config) |
| `geoengine/classification.js` | 196 | The choropleth classification contract: one lookup, three modes |
| `geoengine/geoengine_model.js` | 964 | Data model (record loading, spatial queries, trail data) |
| `geoengine/layer_classifier.js` | 375 | Choropleth and proportional classification: population from the server, class bounds/colours/legend, size map, LRU cache keyed on config + data fingerprint |
| `geoengine/geoengine_controller.js` | 330 | Controller (search, pager, action dispatch) |
| `geoengine/geoengine_renderer.js` | 764 | Main renderer (OpenLayers map init, layer orchestration) |
| `geoengine/geoengine_record.js` | 187 | Record popup/info_box rendering |
| `geoengine/record_values.js` | 26 | Display-value / saved-value helpers shared by record and renderer |
| **Renderer subsystems** | | |
| `geoengine/renderer/geoengine_renderer_layers.js` | 265 | Layer creation (vector/raster), data loading |
| `geoengine/renderer/raster_layers.js` | 315 | Background layers: OSM, XYZ, WMTS, tiled and single-image WMS, vector tiles, OSM fallback |
| `geoengine/renderer/trail_layer.js` | 274 | The animated WebGL trail layer: XYM parts, timestamp interpolation, time style variable |
| `geoengine/renderer/geoengine_renderer_styling.js` | 430 | Feature styling (basic, proportional, colored, color-from-field, heatmap, cluster) |
| `geoengine/renderer/geoengine_renderer_interactions.js` | 1,230 | Map interactions (select, draw, modify) |
| `geoengine/renderer/geoengine_renderer_trails.js` | 263 | Live position trails, stored and drawn per model |
| `geoengine/renderer/geoengine_renderer_utils.js` | 207 | Utility functions (coordinate transform, geometry helpers) |
| `geoengine/renderer/geoengine_map_tools.js` | 451 | Measure, locate, box-select, snap, export-PNG map tools |
| `geoengine/renderer/render_strategies.js` | 577 | WebGL/Canvas render strategy selection |
| `geoengine/renderer/webgl_style_converter.js` | 244 | Converts OL styles to WebGL flat styles |
| **Panels** | | |
| `geoengine/panels/features_list.js` | 221 | Feature list sidebar panel |
| `geoengine/panels/layers_panel.js` | 404 | Layer toggle/opacity panel |
| `geoengine/panels/time_slider.js` | 204 | Time slider for trail animation |
| **Domain support** | | |
| `domain/geo_domain_selector.js` | 43 | Geo domain selector integration |
| `domain/geo_tree_processor.js` | 38 | Domain tree processing for geo operators |
| `domain/geo_virtual_operators.js` | 51 | Virtual operator definitions for UI |
| `domain_selector/domain_field.js` | 42 | Domain field extension for geo types |
| **Fields** | | |
| `fields/geo_form_field.js` | 46 | Geo field form widget (the eager, always-loaded part) |
| **Services** | | |
| **Libs / debug** | | |
| `lib/geo_libs.js` | 108 | Dynamic `import()` of ol/chroma-js/geostats, one deduped promise per session |
| `geo_debug.js` | 24 | Console debug helpers |

domain_selector/domain_selector_geo_field_dialog.js (previously documented
here, 43 lines) no longer exists in the tree — named in plain prose, not
backticks, because a backticked path asserts the file exists.

### External Libraries (`static/lib/`)

| Library | Version | Purpose |
|---------|---------|---------|
| OpenLayers | 10.10.0 | Map rendering engine. Locally built, tree-shaken over `lib/ol/entry.js` |
| chroma-js | 3.2.0 | Color scale generation for classification |
| geostats | 2.1.0 | Statistical classification (quantile, interval, unique). Fork-modified -- 4 `AgroMarin:` markers |

### Data (`data/`)

| File | Content |
|------|---------|
| `ir_config_param_data.xml` | 4 params: default_map_extent, validate_geometry, auto_repair_geometry, max_geometry_size. No zoom param -- `geoengine.default_map_zoom` was shipped here once, unread by any code path, and was removed; `get_layers()` takes zoom from the view's own `default_map_zoom` field |

### Security (`security/`)

| File | Content |
|------|---------|
| `res_groups.xml` | Privilege `Geoengine` with User (all internal users) and Admin groups |
| `ir.access.csv` | 13 access rows. `ir.model` and `ir.ui.view` are ADMIN-only: granting them to the user group handed every employee every view arch in the database (19.0.1.11.0) |

## Directory Structure

```
geoengine/
├── __init__.py              # pre_init_hook: _pre_init_postgis
├── __manifest__.py
├── ARCHITECTURE.md
├── models/
│   ├── geo_types.py         # Enums, constants, type aliases
│   ├── fields.py            # GeoField base + 6 concrete field classes
│   ├── geo_domain.py        # Domain operator registration
│   ├── base.py              # Base model extension (get_layers, aggregates)
│   ├── geoengine_raster_layer.py
│   ├── geoengine_vector_layer.py
│   ├── ir_ui_view.py        # View type + validation
│   ├── geoengine_view_settings.py  # Per-view map settings
│   ├── ir_model_fields.py   # Field type registration
│   └──├── wizards/
│   ├── wizard_base_view_trail.py
│   ├── wizard_base_view_trail_result.py
│   ├── wizard_base_import_geodata.py
│   ├── wizard_base_import_geodata_mapping.py
│   ├── wizard_base_export_geodata.py
│   └── res_config_settings.py
├── views/                   # 5 XML view files
├── data/                    # Config params
├── security/                # Groups + ACLs
├── tests/                   # 13 Python test modules (+ common.py, mvt.py)
├── static/
│   ├── src/                 # 27 JS files (~10,060 lines)
│   │   ├── geoengine/       # View MVC + renderer subsystems + panels
│   │   ├── domain/          # Domain selector geo support
│   │   ├── domain_selector/ # Domain field extension
│   │   ├── fields/          # Geo field form widget
│   │   ├── services/        # Layer data service
│   │   ├── libs/            # geo_libs.js (dynamic ol/chroma-js/geostats import)
│   │   ├── geo_debug.js     # Console debug helpers
│   │   └── css/             # Styles
│   ├── lib/                 # OpenLayers, chroma-js, geostats (ESM; see its README)
│   └── tests/               # 11 JS test files
└── i18n/                    # Translations
```

## Key Architecture Decisions

1. **Assets**: view/field JS goes in `web.assets_backend` (eager — the geo field form widget must be available in any form/list view, not just the map). OpenLayers/chroma-js/geostats are ES modules resolved through the import map and loaded by `lib/geo_libs.js` with one dynamic `import()` when the map view opens.
2. **Domain integration**: Geo operators contributed to the domain language via `register_condition_operators()` and given meaning by `@operator_optimization` -- works in any search/filter.
3. **Spatial aggregates**: Registered in `READ_GROUP_AGGREGATE` -- any model with geo fields can use `geo_union`, `geo_collect`, `geo_extent`, `geo_centroid` in `_read_group()`.
4. **Render strategies**: Auto/WebGL/Canvas per-view or per-layer. WebGL for large datasets (>1000 features) and draws its own labels since OpenLayers 10.10; Canvas is required only for on-map editing.
5. **Geometry validation**: Auto-repair via `shapely.make_valid()`, configurable size limits, all controlled by `ir.config_parameter`.

## Reading Order

1. **models.md** -- All models, fields, relationships
2. `geo_types.py` -- Enums and constants (foundation)
3. `fields.py` -- GeoField class hierarchy (core)
4. `geo_domain.py` -- domain registration and the only spatial-SQL path
5. `base.py` -- Model extension, get_layers()
6. `ir_ui_view.py` -- View type and validation
7. `geoengine_renderer.js` + renderer subsystems -- Frontend architecture
