# Geoengine Models

## Model Relationship Diagram

```
ir.ui.view (extended)
    ├── raster_layer_ids ──→ geoengine.raster.layer (o2m via view_id)
    │                          └── field_id ──→ ir.model.fields
    ├── vector_layer_ids ──→ geoengine.vector.layer (o2m via view_id)
    │                          ├── geo_field_id ──→ ir.model.fields
    │                          ├── attribute_field_id ──→ ir.model.fields
    │                          ├── color_field_id ──→ ir.model.fields
    │                          ├── model_id ──→ ir.model (computed)
    │                          └── model_view_id ──→ ir.ui.view (computed)
    └── type = "geoengine"

base (extended, Abstract)
    └── Provides: get_layers(), _read_group_select(),
        _vector_layer_payload(), _check_geo_view_configuration()


wizard.base.view.trail (Transient)
    └── trail_ids ──→ wizard.base.view.trail.result (m2m)

wizard.base.view.trail.result (Transient)
    ├── the_trail: GeoLine (srid=4326)
    └── wizard_id ──→ wizard.base.view.trail

wizard.base.import.geodata (Transient)
    ├── model_id ──→ ir.model
    ├── geo_field_id ──→ ir.model.fields
    └── mapping_lines ──→ wizard.base.import.geodata.mapping (o2m)

wizard.base.import.geodata.mapping (Transient)
    ├── wizard_id ──→ wizard.base.import.geodata
    └── field_id ──→ ir.model.fields

wizard.base.export.geodata (Transient)
    ├── model_id ──→ ir.model
    ├── geo_field_id ──→ ir.model.fields
    └── property_field_ids ──→ ir.model.fields (m2m)
```

## Non-ORM Classes

### GeoField (and subclasses) -- `models/fields.py`

Base class for PostGIS geometry fields. Extends `odoo.fields.Field`.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `geo_type` | `str \| None` | `None` | PostGIS type (set by subclasses) |
| `dim` | `str` | `"2"` | Dimension: "2" (2D), "3" (3D), "4" (4D) |
| `srid` | `int` | `3857` | Spatial Reference System ID |
| `aggregator` | `str` | `"geo_collect"` | Default spatial aggregate for read_group |

**Concrete subclasses** (registered on `odoo.fields`):

| Class | `type` | `geo_type` | Registered as |
|-------|--------|------------|---------------|
| `GeoPoint` | `geo_point` | `Point` | `fields.GeoPoint` |
| `GeoLine` | `geo_line` | `LineString` | `fields.GeoLine` |
| `GeoPolygon` | `geo_polygon` | `Polygon` | `fields.GeoPolygon` |
| `GeoMultiPoint` | `geo_multi_point` | `MultiPoint` | `fields.GeoMultiPoint` |
| `GeoMultiLine` | `geo_multi_line` | `MultiLineString` | `fields.GeoMultiLine` |
| `GeoMultiPolygon` | `geo_multi_polygon` | `MultiPolygon` | `fields.GeoMultiPolygon` |

**Key methods:**

| Method | Description |
|--------|-------------|
| `convert_to_column(value, record)` | Python -> DB: returns `"SRID=3857;POINT(0 0)"` WKT with SRID |
| `convert_to_cache(value, record)` | Any format -> the EWKB hex the column holds |
| `convert_to_record(value, record)` | Cache -> Shapely `BaseGeometry` object |
| `convert_to_read(value, record)` | Any -> GeoJSON string with CRS metadata |
| `entry_to_shape(value, same_type)` | Parse and optionally type-validate geometry |
| `update_db_column(model, column)` | Create/validate PostGIS column + GIST index |
| `_validate_geometry(shape, record)` | Auto-repair via `make_valid()`, size limits |

**Spatial aggregates** (registered globally in `READ_GROUP_AGGREGATE`):

| Aggregate | SQL emitted | Returns |
|-----------|-------------|---------|
| `geo_union` | `ST_Union(...)` | Merged geometry |
| `geo_collect` | `ST_Collect(...)` | GeometryCollection |
| `geo_extent` | `ST_SetSRID(ST_Extent(...)::geometry, MIN(ST_SRID(...)))` | Envelope polygon |
| `geo_centroid` | `ST_Centroid(ST_Collect(...))` | Center point |

`geo_aggregate_sql` wraps each in `ST_AsGeoJSON(..., 15, 2)` (transformed to
EPSG:4326 for a non-renderable SRID), so PostGIS returns the GeoJSON, `crs`
member included, and no Python post-processing runs. `ST_Extent` returns a
`box2d`, hence the cast and the SRID read back from the rows.


### Enums -- `models/geo_types.py`

| Enum | Values | Purpose |
|------|--------|---------|
| `SpatialOperator` (StrEnum) | `ST_Intersects`, `ST_Contains`, `ST_Within`, `ST_Touches`, `ST_Overlaps`, `ST_Covers`, `ST_CoveredBy`, `ST_Disjoint`, `ST_Crosses`, `ST_Equals`, `ST_DWithin` (11) | PostGIS function names. No `ST_Distance`/`ST_Area`/`ST_Length` members -- those PostGIS functions exist but this enum does not carry them |
| `DomainOperator` (StrEnum) | `geo_intersect`, `geo_contains`, `geo_within`, `geo_touch`, `geo_equal`, `geo_overlap`, `geo_covers`, `geo_covered_by`, `geo_disjoint`, `geo_crosses`, `geo_dwithin` (11) | Odoo domain operators |

There is no `SRID` enum. One was documented here with `WGS84`/`WEB_MERCATOR`/
`UTM_NORTH`/`UTM_SOUTH` members; no such class has ever existed in the module.
The two SRIDs the code names are the plain `int` constants below, and the set
OpenLayers can resolve is `CLIENT_RENDERABLE_SRIDS`.

**Constants** -- this is the whole public surface of `geo_types.py`:

| Name | Value | Purpose |
|------|-------|---------|
| `DEFAULT_SRID` | `3857` | Web Mercator for storage |
| `DISPLAY_SRID` | `4326` | WGS84 for display, and the reprojection target for a non-renderable SRID |
| `parse_epsg_code(raw)` | -- | `"EPSG:<n>"` -> `n`, else `None`; the one projection parser |
| `CLIENT_RENDERABLE_SRIDS` | `{4326, 3857, 900913}` + UTM 32601-32660 / 32701-32760 | SRIDs OpenLayers resolves without proj4 |
| `GEO_FIELD_TTYPES` | the 6 `geo_*` ttypes | Single spelling of "which ttypes are geometry" |
| `is_client_renderable_srid(srid)` | -- | Membership test on the set above |
| `GeometryValue` | `BaseGeometry \| str \| None` | Type alias |

There is no `MAX_GEOMETRY_SIZE_BYTES` constant either: the 1 MB default is the
literal `"1000000"` passed to the settings port in `GeoField._check_geometry`
(`fields.py`).

---

## ORM Models

### `geoengine.raster.layer` -- `models/geoengine_raster_layer.py`

| Property | Value |
|----------|-------|
| Type | `models.Model` |
| `_order` | `sequence ASC, name` |

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `view_id` | Many2one(`ir.ui.view`) | Yes | -- | Parent geoengine view |
| `name` | Char | Yes | -- | Layer name (translatable) |
| `sequence` | Integer | No | `6` | Display order |
| `raster_type` | Selection | Yes | `osm` | `osm`, `xyz`, `google`, `wmts`, `d_wms`, `i_wms`, `mvt` |
| `url` | Char | No | -- | Service URL |
| `wmts_layer` | Char | WMTS | -- | Layer identifier from GetCapabilities |
| `matrix_set` | Char | No | -- | WMTS matrix set |
| `format_suffix` | Char | No | -- | Format (e.g., png) |
| `request_encoding` | Char | No | -- | e.g., REST |
| `projection` | Char | No | -- | e.g., EPSG:21781 |
| `resolutions` | Char | No | -- | Resolution list |
| `max_extent` | Char | No | -- | Max extent |
| `params` | Char | No | -- | JSON dict for dimension values |
| `server_type` | Char | No | -- | WMS server type |
| `params_wms` | Char | No | -- | WMS params JSON (needs LAYERS) |
| `attribution` | Char | No | -- | Data-source credit text shown on the map |
| `max_zoom` | Integer | No | `20` | Highest zoom level this tile source serves; beyond it the provider returns blank tiles |
| `overlay` | Boolean | No | -- | Is overlay layer |
| `opacity` | Float | No | `1.0` | 0=transparent, 1=opaque |

There is no `field_id` field and no `odoo` raster type -- both were previously
documented here but do not exist in the code.

**Constraints:**

| Name | Rule |
|------|------|
| `_opacity_range` | `CHECK(opacity >= 0 AND opacity <= 1)` |
| `_sequence_positive` | `CHECK(sequence >= 0)` |
| `_max_zoom_range` | `CHECK(max_zoom >= 0 AND max_zoom <= 24)` |
| `_check_url` | URL format validation for remote services |
| `_check_projection` | Same rule `ir.ui.view._check_projection` enforces for the map |
| `_check_params_json` | Valid JSON in params |
| `_check_params_wms_json` | Valid JSON in params_wms |

---

### `geoengine.vector.layer` -- `models/geoengine_vector_layer.py`

| Property | Value |
|----------|-------|
| Type | `models.Model` |
| `_order` | `sequence ASC, name` |

**Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | Char | Yes | -- | Layer name (translatable) |
| `sequence` | Integer | No | `6` | Display order |
| `geo_repr` | Selection | Yes | -- | `basic`, `proportion`, `colored`, `colored_field`, `heatmap`, `cluster` |
| `heatmap_radius` | Integer | No | `8` | Heatmap point radius (px) |
| `heatmap_blur` | Integer | No | `15` | Heatmap blur size (px) |
| `heatmap_weight_field_id` | Many2one(`ir.model.fields`) | No | -- | Numeric field normalized to 0..1 for heatmap weight |
| `cluster_distance` | Integer | No | `40` | Max pixel distance to cluster points together |
| `cluster_min_distance` | Integer | No | `20` | Min pixel distance kept between distinct clusters |
| `classification` | Selection | No | -- | `unique`, `interval`, `quantile` |
| `begin_color` | Char | No | -- | Hex start color for gradient |
| `end_color` | Char | No | `#FF680A` | Hex end color for gradient |
| `nb_class` | Integer | No | `1` | Number of classification bins |
| `nb_class_recommended` | Integer (computed) | -- | -- | `min(max(1, distinct - 1), 10)`, so it is capped at 10; `0` unless `geo_repr = colored` with an attribute field |
| `model_id` | Many2one(`ir.model`) | No | computed | Cross-model layer target |
| `model_name` | Char (related) | -- | -- | Technical model name |
| `model_domain` | Char | No | `[]` | Domain filter for layer data |
| `model_view_id` | Many2one(`ir.ui.view`) | No | computed | Geoengine view for model |
| `view_id` | Many2one(`ir.ui.view`) | Yes | -- | Parent geoengine view |
| `geo_field_id` | Many2one(`ir.model.fields`) | Yes | -- | Geometry field to display |
| `attribute_field_id` | Many2one(`ir.model.fields`) | No | -- | Field for classification |
| `color_field_id` | Many2one(`ir.model.fields`) | No | -- | Char field with hex colors |
| `readonly` | Boolean | No | -- | Layer is read-only |
| `display_polygon_labels` | Boolean | No | -- | Show labels on polygons |
| `active_on_startup` | Boolean | No | -- | Show layer on initial load |
| `layer_opacity` | Float | No | `1.0` | 0=transparent, 1=opaque |
| `min_size` | Integer | No | `5` | Min symbol size (proportional repr) |
| `max_size` | Integer | No | `15` | Max symbol size (proportional repr) |
| `webgl_threshold` | Integer | No | -- | Per-layer override of the view's `webgl_threshold` |
| `render_engine` | Selection | No | `inherit` | `inherit`, `auto`, `webgl`, `canvas` |

**Constraints:**

| Name | Rule |
|------|------|
| `_opacity_range` | `CHECK(layer_opacity >= 0 AND layer_opacity <= 1)` |
| `_sequence_positive` | `CHECK(sequence >= 0)` |
| `_nb_class_positive` | `CHECK(nb_class >= 1)` |
| `_symbol_sizes_sane` | min_size/max_size bounds for proportional repr |
| `_webgl_threshold_positive` | webgl_threshold, if set, is positive |
| `_check_geo_field_id` | geo_field belongs to model |
| `_check_geo_repr` | Numeric field required for colored/proportional |
| `_check_if_attribute_in_geo_field` | Attribute field same model as geo field |
| `_check_color_field` | Color field required for colored_field mode |
| `_check_point_only_repr` | heatmap/cluster require a point (or multipoint) geo field |
| `_check_heatmap_weight_field` | heatmap_weight_field_id, if set, is numeric and same model |
| `_check_cluster_distances` | cluster_min_distance <= cluster_distance |
| `_check_heatmap_sizes` | heatmap_radius/heatmap_blur are positive |
| `_check_hex_colors` | Valid hex color format |
| `_check_model_domain` | Valid Odoo domain syntax |

There is no save-time check of `nb_class` against the data: the classifier
clamps quantile classes to `values - 1` (geostats' own limit), and
`nb_class_recommended`, which counts distinct values, is advisory.

`get_class_bounds(layer_domain)` / `get_class_values(layer_domain)` read the
layer's population with the domain the map evaluated -- its filter (or the
user's session filter), the search, `{ACTIVE_IDS}` expanded; without one the
stored filter applies. They used to AND the stored filter onto it a second time.
The map skips them when the drawn rows already are the population.
`get_class_values(..., distinct=True)` names each value once (a group-by;
datetimes stay row by row so they match the timestamps the map compares), which
is all unique classes need. When a quantile population exceeds
`MAX_CLASS_VALUES`, `get_class_quantiles(layer_domain, nb_class)` returns the
bounds `percentile_cont` cuts in the database.

**Key methods:**

| Method | Description |
|--------|-------------|
| `_count_distinct_values(limit=1000)` | Distinct attribute values under the stored filter (dates by day) |
| `_attribute_target()` | The target model and stored attribute field, or None |
| `_compute_model_id()` | Set model_id when geo_field is from different model |
| `_compute_model_view_id()` | The default geoengine view of model_id (primary, by priority) |
| `_compute_nb_class_recommended()` | Max safe classification bins |

---

### `geoengine.view.settings` -- `models/geoengine_view_settings.py`

One row per geoengine view that departs from the defaults; a view with no row
uses them. Until 19.0.1.18.0 these were eleven columns on every `ir.ui.view`
row; the 19.0.1.18.0 post-migrate (since retired) copied them into this table and
dropped them, giving each moved row a `noupdate` xmlid derived from its view's
so that module data declaring the same settings updates rather than collides.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `view_id` | Many2one(`ir.ui.view`), required, unique, cascade | -- | The geoengine view (constraint: `type == 'geoengine'`) |
| `projection` | Char | `EPSG:3857` | Map projection |
| `default_map_extent` | Char | -- | `min_x, min_y, max_x, max_y` |
| `restricted_extent` | Char | -- | Pan/zoom limits |
| `default_map_zoom` | Integer | -- | Initial zoom (0-21) |
| `render_engine` | Selection | `auto` | `auto`, `webgl`, `canvas` |
| `webgl_threshold` | Integer | `1000` | Feature count for auto WebGL switch |
| `show_attribution` | Boolean | `True` | Show data-source credits control |
| `show_fullscreen` | Boolean | `True` | Show fullscreen-expand control |
| `show_mouse_position` | Boolean | `False` | Show pointer coordinates control |
| `show_overview_map` | Boolean | `False` | Show locator-map control |
| `show_zoom_slider` | Boolean | `False` | Show zoom-slider control |

| Method | Description |
|--------|-------------|
| `_check_map_extents()` (constrains) | Rejects a `default_map_extent`/`restricted_extent` OpenLayers cannot parse |
| `_check_projection()` (constrains) | Validates the `projection` string |
| `_check_map_numbers()` (constrains) | Validates `default_map_zoom`/`webgl_threshold` ranges |

---

### `ir.ui.view` (extended) -- `models/ir_ui_view.py`

**Added fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | Selection (extended) | -- | Adds `geoengine` option; `ir.actions.act_window.view.view_mode` derives its modes from this selection (core `74537ec7364`) |
| `raster_layer_ids` | One2many(`geoengine.raster.layer`) | -- | Background layers |
| `vector_layer_ids` | One2many(`geoengine.vector.layer`) | -- | Data layers |
| `map_settings_id` | Many2one(`geoengine.view.settings`), computed with inverse | -- | The view's map settings row, if one exists; `_map_settings()` answers a defaults-only `new()` record otherwise |

**Key methods:**

| Method | Description |
|--------|-------------|
| `_map_settings()` | The view's `geoengine.view.settings` record, or a `new()` one carrying the defaults |
| `_get_view_info()` | Icon: `fa-solid fa-earth-americas` |
| `_is_qweb_based_view(type)` | Returns True for `geoengine` |
| `_postprocess_view(node, ...)` | On a `geoengine` arch: runs info_box, geometry-field-present, the client attributes, and (if `webgl_trail` is set) webgl_trail validation. Layer presence is deliberately **not** checked here -- see below |
| `_check_info_box_template()` | Requires `t-name="info_box"` template |
| `_check_geometry_field_present()` | Requires at least one PostGIS geometry field in the arch |
| `_check_client_attributes()` | `features_list_field`, `features_list_group_by` and `default_order` name fields of the model |
| `_check_webgl_trail_configuration()` | `trail_timestamps_field` exists and is valid, when `webgl_trail="True"` |
| `_check_view_field()` / `_suggest_fields()` | Shared field-existence check with a `difflib` "did you mean" suggestion |

Raster/vector layer *presence* is validated at render time, not at view save:
layers reference the view by FK, so they can only be created after the view
exists (`Base._validate_geo_view_configuration()`, called from
`Base.get_layers()` -- see below). There is no save-time check of trail or
layer configuration.

---

### `base` (extended, Abstract) -- `models/base.py`

**Key methods:**

| Method | Description |
|--------|-------------|
| `_read_group_select(aggregate_spec, query)` | Spatial aggregates on a GeoField only, as PostGIS GeoJSON |
| `_get_default_map_extent(view)` | Hierarchy: view -> system param -> company country -> fallback |
| `_extent_in_projection(extent, projection)` | Restates a Web-Mercator extent in the view's projection |
| `_get_geo_view(view_id=None)` | The geoengine view the client asked for, else the model's default one (`default_view`) |
| `get_layers(view_id=None)` | Full layer config dict (raster + vector + projection + controls + validation) |
| `_validate_geo_view_configuration(view)` | Returns `{valid, errors, warnings}` |
| `_validate_vector_layer(...)` | Per-layer half of the above |

The validation entry point is `_validate_geo_view_configuration`, with the
leading underscore. There is no public `validate_geo_view_configuration`.

**Country extents** (14 countries in Web Mercator):
AR, AU, BR, CA, CN, DE, ES, FR, GB, IN, IT, JP, MX, US

The UK key is `GB` (ISO code), not `UK` -- `COUNTRY_EXTENTS.get("UK")` returns
`None`.

---

### `ir.model.fields` (extended) -- `models/ir_model_fields.py`

**Added fields:**

| Field | Type | Description |
|-------|------|-------------|
| `geo_type` | Selection | PostGIS type name |
| `dim` | Selection | `2`, `3`, `4` |
| `srid` | Integer | Spatial Reference System ID |
| `is_geo_field` | Boolean (computed) | `ttype in GEO_FIELD_TTYPES`; gates `readonly=` on the three fields above in `ir_model_fields_views.xml` |

**`ttype` is not extended here, and must not be.** It was documented as a
`selection_add` adding the 6 geo types; there is no such override. `ttype`
resolves its vocabulary from `Field._by_type__` at call time (base's
`_selection_field_types`), and the six `GeoField` subclasses enter it just by declaring
`type`. A `selection_add` would not be merely redundant -- the attribute applies
only to a list selection, and this one is a callable, so it raises.

---

## Transient Models (Wizards)

### `wizard.base.view.trail` -- `wizards/wizard_base_view_trail.py`

Trail generation from position records with date range filtering and grouping.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model_id` | Many2one(`ir.model`) | -- | Source model |
| `model_name` | Char (related) | -- | Technical model name |
| `date_field` | Selection (dynamic) | `write_date` | Date field to order and filter positions by |
| `date_from` | Datetime | now - 1 day | Start date |
| `date_to` | Datetime | now | End date |
| `group_by` | Selection | `none` | `none`, `day`, `device_id` |
| `domain` | Char | `[]` | Additional filter |
| `trail_color` | Char | `#0000FF` | Hex trail color |
| `trail_width` | Integer | `3` | Pixels |
| `trail_opacity` | Float | `0.8` | 0.0-1.0 |
| `trail_count` | Integer | -- | Result count |
| `trail_ids` | Many2many(`wizard.base.view.trail.result`) | -- | Generated trails |

`date_field`'s selection is computed by `_selection_date_field`: `create_date`
and `write_date`, plus every stored Datetime field of the model named in
`default_trail_model`. There is no fixed `timestamp` option -- it appears only
when the target model happens to define such a field. The default is
`write_date`, which for GPS data is usually the wrong choice; the field's help
says so.

### `wizard.base.view.trail.result` -- `wizards/wizard_base_view_trail_result.py`

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Trail name |
| `the_trail` | GeoLine (srid=4326) | Trail path geometry |
| `record_count` | Integer | Points in trail |
| `wizard_id` | Many2one(`wizard.base.view.trail`) | Source wizard |
| `trail_color` | Char | Hex color |
| `trail_width` | Integer | Line width |
| `trail_opacity` | Float | Transparency |
| `length_km` | Float (computed) | Geodesic length via PyProj |

---

### `wizard.base.import.geodata` -- `wizards/wizard_base_import_geodata.py`

GeoJSON, Shapefile or GeoPackage import (format auto-detected from content)
with field mapping and CRS detection.

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | Many2one(`ir.model`) | Target model |
| `file_data` | Binary | GeoJSON file, a zipped Shapefile, or a GeoPackage |
| `file_name` | Char | File name |
| `geo_field_id` | Many2one(`ir.model.fields`) | Target geometry field |
| `name_property` | Char | Property to use as record name |
| `mapping_lines` | One2many(`wizard.base.import.geodata.mapping`) | Field mapping |
| `skip_invalid` | Boolean (default True) | Skip invalid geometries |
| `feature_count` | Integer | Preview: features found |
| `preview_properties` | Text | Preview: available properties |
| `imported_count` | Integer | Result count |

Max import: 50,000 features (`MAX_IMPORT_FEATURES`).

### `wizard.base.import.geodata.mapping` -- `wizards/wizard_base_import_geodata_mapping.py`

| Field | Type | Description |
|-------|------|-------------|
| `wizard_id` | Many2one(`wizard.base.import.geodata`) | Parent wizard |
| `property_name` | Char | GeoJSON property, Shapefile DBF column, or GeoPackage column name |
| `field_id` | Many2one(`ir.model.fields`) | Required. Target field the property is written to, domained to the wizard's model, non-readonly, and excluding geo/o2m/m2m ttypes |

### `wizard.base.export.geodata` -- `wizards/wizard_base_export_geodata.py`

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | Many2one(`ir.model`) | Source model |
| `geo_field_id` | Many2one(`ir.model.fields`) | Geometry field |
| `property_field_ids` | Many2many(`ir.model.fields`) | Fields as properties |
| `domain` | Char | Filter domain |
| `output_format` | Selection | `geojson`, `shapefile` or `geopackage` |
| `output_srid` | Selection | `4326` (WGS84) or `3857` (Web Mercator) |
| `output_file` | Binary | Download result |
| `output_filename` | Char | Generated filename |

---

### `res.config.settings` (extended) -- `wizards/res_config_settings.py`

**4** config parameters for GeoEngine -- not 16. Thirteen existed until
19.0.1.3.0 (`geoengine_default_srid`, `display_srid`, `enable_spatial_cache`,
`cache_timeout`, `max_cache_entries`, `spatial_index_buffer`,
`coordinate_precision`, `use_company_country_extent`,
`enable_spatial_indexes`, `vacuum_spatial_indexes`, `log_spatial_operations`,
`monitor_cache_performance`, `geoengine_map_zoom`) and were removed: no line
of Python/JS/XML read them, there is no spatial cache to configure, the GIST
index is created unconditionally by `GeoField.update_db_column` regardless of
`auto_spatial_indexes`, and `_get_default_map_extent` consults the company
country regardless of `use_company_country_extent`. `auto_repair_geometry`
was added. See the comment at the top of `res_config_settings.py`.

| Field | Config Parameter | Default | Description |
|-------|-----------------|---------|-------------|
| `enable_geometry_validation` | `geoengine.validate_geometry` | `True` | Auto validation, read by `GeoField._validate_geometry` |
| `auto_repair_geometry` | `geoengine.auto_repair_geometry` | `True` | Repair invalid geometry with `ST_MakeValid` instead of rejecting it |
| `max_geometry_size` | `geoengine.max_geometry_size` | `1000000` | Max bytes of WKT |
| `geoengine_map_extent` | `geoengine.default_map_extent` | -- | Default extent, read by `Base._get_default_map_extent` |

**Action methods:** `action_rebuild_spatial_indexes()` (drops/recreates every
stored geo field's GIST index, one savepoint per index, not `CONCURRENTLY`
since it runs inside Odoo's own transaction), `action_set_country_extent()`
(fills `geoengine_map_extent` from `COUNTRY_EXTENTS[company.country_id.code]`).

---

## Domain Integration -- `models/geo_domain.py`

Geo operators are registered at module import time:

1. `register_condition_operators(...)` -- makes the operators valid in domains.
   `CONDITION_OPERATORS` is the framework's own frozen vocabulary and geo
   operators are deliberately not in it; the set `checked()` consults is
   `ACCEPTED_CONDITION_OPERATORS`
2. `@operator_optimization(GEO_OPERATORS, OptimizationLevel.DYNAMIC_VALUES)` --
   converts spatial queries to `[('id', 'in', [...])]`. The level is
   `DYNAMIC_VALUES`, not `FULL`: the operand can be a cross-model subquery whose
   result is not knowable at parse time

**Usage in domains:**
```python
# Basic spatial query
records = Model.search([("geo_field", "geo_intersect", polygon_wkt)])

# Distance query
records = Model.search(
    [("geo_field", "geo_dwithin", {"geometry": point_wkt, "distance": 1000})]
)

# Cross-model reference
records = Model.search(
    [("geo_field", "geo_contains", {"other.model.geo_field": [("active", "=", True)]})]
)
```

## JS Architecture Summary

**View type:** `geoengine` (registered via `registry.category("views")`)

**MVC pattern:**
- **Model** (`geoengine_model.js`, 1,536 lines): Record loading, spatial queries, trail data management
- **Controller** (`geoengine_controller.js`, 500 lines): Search/pager/action dispatch
- **Renderer** (`geoengine_renderer.js`, 984 lines): OpenLayers map initialization, delegates to subsystems

**Renderer subsystems** (separate files for maintainability):
- `geoengine_renderer_layers.js` (265 lines): Vector/raster layer creation, data loading, GeoJSON parsing
- `geoengine_renderer_styling.js` (430 lines): 6 styling modes (basic, proportional, colored range, color-from-field, heatmap, cluster)
- `geoengine_renderer_interactions.js` (1,174 lines): Select, draw, modify, snap map interactions
- `geoengine_renderer_trails.js` (263 lines): Live position trails, stored and drawn per model
- `geoengine_renderer_utils.js` (193 lines): Coordinate transforms, geometry helpers
- `geoengine_map_tools.js` (448 lines): Measure, locate, box-select, snap, export PNG
- `render_strategies.js` (556 lines): WebGL/Canvas strategy selection and conversion
- `webgl_style_converter.js` (242 lines): OL style -> WebGL flat style conversion

**UI panels:**
- `features_list.js` (221 lines): Sidebar listing map features
- `layers_panel.js` (401 lines): Layer visibility/opacity control
- `time_slider.js` (204 lines): Trail animation time control

**Service:**
- Layer configuration is state of `GeoengineModel` (`model.layers`), read by the renderer and the panel through the reactive model prop
