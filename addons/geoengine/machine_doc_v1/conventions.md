# Geoengine Conventions and Gotchas

## Adding a Geo Field to a Model

1. Add the field to your model class:

```python
from odoo import fields


class MyModel(models.Model):
    _name = "my.model"

    # Point field (most common for locations)
    location = fields.GeoPoint(string="Location", srid=3857)

    # Polygon field (for areas, boundaries)
    boundary = fields.GeoPolygon(string="Boundary", srid=3857)

    # Line field (for routes, trails)
    route = fields.GeoLine(string="Route", srid=3857)
```

2. The field is registered on `odoo.fields` at import time via `fields.GeoPoint = GeoPoint`.
   No additional imports needed beyond `from odoo import fields`.

3. On module install/upgrade, `update_db_column()` automatically:
   - Creates the PostGIS geometry column via `AddGeometryColumn()`
   - Creates a GIST spatial index

Available field classes and their PostGIS types:

| Field Class | `type` attribute | PostGIS type |
|-------------|------------------|--------------|
| `fields.GeoPoint` | `geo_point` | `Point` |
| `fields.GeoLine` | `geo_line` | `LineString` |
| `fields.GeoPolygon` | `geo_polygon` | `Polygon` |
| `fields.GeoMultiPoint` | `geo_multi_point` | `MultiPoint` |
| `fields.GeoMultiLine` | `geo_multi_line` | `MultiLineString` |
| `fields.GeoMultiPolygon` | `geo_multi_polygon` | `MultiPolygon` |

### Field Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `srid` | `3857` | Spatial Reference System ID |
| `dim` | `"2"` | Dimension: `"2"` (2D), `"3"` (3D with Z), `"4"` (4D with ZM) |

---

## Creating a Geoengine View for a Model

### 1. Create the XML view

```xml
<record id="view_my_model_geoengine" model="ir.ui.view">
    <field name="name">my.model.geoengine</field>
    <field name="model">my.model</field>
    <field name="type">geoengine</field>
    <field name="arch" type="xml">
        <geoengine>
            <!-- All fields used in info_box or for coordinates must be declared -->
            <field name="name"/>
            <field name="location"/>
            <field name="status"/>

            <!-- info_box template is REQUIRED for feature popups -->
            <templates>
                <t t-name="info_box">
                    <div>
                        <strong><t t-esc="record.display_name"/></strong>
                        <br/>
                        <span>Status: <t t-esc="record.status"/></span>
                    </div>
                </t>
            </templates>
        </geoengine>
    </field>
</record>
```

### 2. Declare a PostGIS geometry field

A map draws PostGIS geometry and nothing else; the arch must declare at least
one `geo_*` field, and `ir.ui.view` refuses an arch without one:
```xml
<geoengine>
    <field name="location"/>  <!-- geo_point field detected automatically -->
</geoengine>
```

### 3. Add raster layer (required -- provides map background)

```xml
<record id="raster_osm_my_model" model="geoengine.raster.layer">
    <field name="view_id" ref="view_my_model_geoengine"/>
    <field name="name">OpenStreetMap</field>
    <field name="raster_type">osm</field>
    <field name="sequence">1</field>
</record>
```

### 4. Add vector layer (required -- displays model data)

```xml
<record id="vector_my_model_location" model="geoengine.vector.layer">
    <field name="view_id" ref="view_my_model_geoengine"/>
    <field name="name">Locations</field>
    <field name="geo_field_id" ref="field_my_model__location"/>
    <field name="geo_repr">basic</field>
    <field name="active_on_startup" eval="True"/>
    <field name="sequence">1</field>
</record>
```

For colored classification:
```xml
<record id="vector_my_model_colored" model="geoengine.vector.layer">
    <field name="view_id" ref="view_my_model_geoengine"/>
    <field name="name">By Revenue</field>
    <field name="geo_field_id" ref="field_my_model__location"/>
    <field name="attribute_field_id" ref="field_my_model__revenue"/>
    <field name="geo_repr">colored</field>
    <field name="classification">quantile</field>
    <field name="nb_class">5</field>
    <field name="begin_color">#FFFFFF</field>
    <field name="end_color">#FF0000</field>
    <field name="active_on_startup" eval="True"/>
    <field name="sequence">2</field>
</record>
```

### 5. Add view mode to action

```xml
<record id="action_my_model" model="ir.actions.act_window">
    <field name="name">My Model</field>
    <field name="res_model">my.model</field>
    <field name="view_mode">list,form,geoengine</field>
</record>
```

### 6. Draw a trail (optional)

A trail stored on a record is a line geometry, so it is drawn the way any other
geometry is: add a vector layer whose `geo_field_id` is the GeoLine field. The
`trails="True" trail_field="..."` attribute pair was removed in 19.0.1.5.0 -- it
was parsed, validated with a raising `ValidationError`, added to `activeFields`,
and never rendered by anything.

```xml
<record id="my_trail_layer" model="geoengine.vector.layer">
    <field name="name">Route history</field>
    <field name="view_id" ref="my_geoengine_view"/>
    <field name="geo_field_id" ref="field_my_model__route_history"/>
    <field name="geo_repr">basic</field>
    <field name="active_on_startup">True</field>
</record>
```

For a time-animated GPS trail, `webgl_trail="True"` is a different feature and
does render: it reads a JSON timestamp array per vertex and drives the time
slider.

```xml
<geoengine webgl_trail="True" trail_timestamps_field="trail_timestamps">
    <field name="route_history"/>
    <field name="trail_timestamps"/>
</geoengine>
```

---

## PostGIS Requirements

| Requirement | Version | Purpose |
|-------------|---------|---------|
| PostgreSQL | 18+ | Database engine |
| PostGIS | 3.6+ | Spatial extension |

The `pre_init_hook` (`_pre_init_postgis`) runs
`CREATE EXTENSION IF NOT EXISTS postgis` during module installation. If the
database user lacks superuser rights, the extension must be created manually
first.

### Python Dependencies

Per `__manifest__.py`'s `external_dependencies.python`:

| Package | Purpose |
|---------|---------|
| `shapely` | Geometry parsing, validation, make_valid, WKB/WKT conversion |
| `pyproj` | Geodesic distance calculations, CRS reprojection |
| `pyshp` (imported as `shapefile`) | Shapefile import/export in `wizard_base_import_geodata.py` and `wizard_base_export_geodata.py` -- pure Python, no GDAL |

There is no `geojson` package dependency; GeoJSON is built/parsed with plain
`dict`/`json`, not a dedicated library.

---

## SRID Conventions

| SRID | Name | When to use |
|------|------|-------------|
| `3857` | Web Mercator | **Default for storage**. Compatible with web map tiles (OSM, Google). Units: meters (approximate). |
| `4326` | WGS84 | GPS data, GeoJSON standard (RFC 7946). Units: degrees. Used by `wizard.base.view.trail.result.the_trail`. |

**Rule:** Store in the SRID that matches your data source. The default `srid=3857`
works for most web mapping use cases. Use `srid=4326` when working directly with
GPS coordinates or when GeoJSON interoperability is important.

### What the browser can and cannot resolve

OpenLayers resolves only a fixed set of CRS without proj4, measured against the
bundled `ol` 10.10.0: **EPSG:4326, EPSG:3857, EPSG:900913 and the UTM zones**
(32601-32660, 32701-32760). It does **not** know national grids -- EPSG:6372 and
EPSG:6362 (Mexico), 21781 (Switzerland), 2154 (France), 27700 (UK).

For an unknown code, `ol.format.GeoJSON.readGeometry` does not raise: it uses the
coordinates **untransformed**. A CH1903 point near Bern then draws in the Gulf of
Guinea, and a Mexican ITRF2008 point draws in Nigeria.

`GeoField.convert_to_read()` therefore reprojects with pyproj to WGS84 whenever the
field's SRID is outside that set, and labels the output with the SRID it actually
emitted. Storage is unaffected -- the column keeps its own SRID. The set lives in
`geo_types.CLIENT_RENDERABLE_SRIDS`.

A **map** may nonetheless be drawn in any CRS PostGIS describes. The view's
projection and each raster layer's projection pass their constraints when
`spatial_ref_sys` has an EPSG proj4 text for them (`projections.is_drawable_projection`).
`get_layers` sends those definitions with their area of use as the extent, and
`geo_libs.registerProjections` hands them to `ol.proj.register` through proj4,
which is imported only then. Do not widen `CLIENT_RENDERABLE_SRIDS` for this:
field values are read by form and list widgets too, which register no
definitions, so a field outside the built-in set keeps being sent in WGS84 and
the map transforms it.

---

## Coordinate System Patterns

### Writing geometry values (Python)

```python
# From WKT
record.location = "POINT(948695.5 6002729.5)"

# From Shapely
from shapely.geometry import Point

record.location = Point(948695.5, 6002729.5)

# With explicit SRID (must match field's srid)
record.location = "SRID=3857;POINT(948695.5 6002729.5)"
```

### Reading geometry values (Python)

```python
# Returns Shapely BaseGeometry
geom = record.location  # e.g., Point(948695.5, 6002729.5)
geom.x  # 948695.5
geom.y  # 6002729.5
geom.wkt  # "POINT (948695.5 6002729.5)"
```

### Spatial queries in domains

```python
# Basic spatial query
records = Model.search([("location", "geo_intersect", polygon_wkt)])

# Distance query (within 1000 meters, SRID=3857)
records = Model.search(
    [("location", "geo_dwithin", {"geometry": point_wkt, "distance": 1000})]
)

# Cross-model reference
records = Model.search(
    [("location", "geo_contains", {"other.model.geo_field": [("active", "=", True)]})]
)
```

### Spatial aggregates in read_group

```python
results = self.env["farm"]._read_group(
    domain=[],
    groupby=["owner_id"],
    aggregates=["boundary:geo_union", "boundary:geo_centroid"],
)
```

---

## Test Commands

Run from the workspace root (`~/Odoo`), with the venv interpreter:

```bash
# All geoengine tests
p314o19m/bin/python odoo/odoo-bin -c p314o19m.conf -d <db> \
    --test-enable --test-tags '/geoengine' -u geoengine --stop-after-init

# One class, or one method
... --test-tags '/geoengine:TestGeoFields'
... --test-tags '/geoengine:TestGeoFields.test_wkt_to_wkb_conversion'

# Just the spatial-domain suite (SQL vs in-memory, error contract)
... --test-tags 'geoengine_domain'

# Fresh database. Create it THROUGH Odoo, not with createdb: p314o19m.conf sets
# db_template = tpl_p314o19marin, which already carries postgis, pg_trgm,
# unaccent and vector. A bare createdb gets none of them.
dropdb --if-exists <db>
p314o19m/bin/python odoo/odoo-bin -c p314o19m.conf -d <db> \
    -i geoengine --test-enable --test-tags '/geoengine' --stop-after-init
```

JavaScript (needs the HTTP server and Chrome, so never `--no-http`):

```bash
p314o19m/bin/python odoo/odoo-bin -c p314o19m.conf -d <db> -i geoengine --test-enable \
    --test-tags '/web:AddonSuite.test_geoengine[@geoengine/geoengine_arch_parser]' \
    --http-port <free port> --stop-after-init
```

### Test Base Class

```python
from odoo.addons.geoengine.tests.common import GeoEngineTestCase


class TestMyGeoModel(GeoEngineTestCase):
    def test_something(self):
        # Fixtures available: zurich_point, geneva_point, swiss_bbox,
        # test_highway, zurich_area, paris_point (all EPSG:3857)
        # Helper: self.assertGeometryEqual(geom1, geom2, tolerance=1.0)
        pass
```

---

## Common Pitfalls

### SRID Mismatches

**Problem:** Storing 4326 (lat/lon) coordinates in a field defined as `srid=3857`.
The values will be stored without error but will appear in the wrong location
(tiny cluster near the equator/prime meridian intersection instead of actual location).

**Prevention:** none of it is caught for you, because *declaring* the wrong SRID
is indistinguishable from meaning it. What the module does do:

- A value that arrives with its **own** SRID (`"SRID=4326;POINT(8.54 47.38)"`, a
  GeoJSON with `crs`) is reprojected into the field's SRID on write --
  `GeoField._normalize_for_storage`. The mismatch above only bites when bare
  coordinates arrive with no SRID to reproject from, which the module cannot
  distinguish from correct input.
- `_sync_geometry_column()` compares the column against the field at upgrade
  time: a different SRID is transformed in place, any other mismatch is logged
  and the column left as it is -- nothing raises to the caller. See *Column Type
  Changes* below.
- Always verify the SRID matches your data source before defining the field.

### Geometry Validation Failures

**Problem:** Self-intersecting polygons, duplicate vertices, or invalid ring orientations
cause PostGIS errors.

**Mitigation:** Auto-repair is enabled by default via `geoengine.validate_geometry=True`
and `geoengine.auto_repair_geometry=True`. Invalid geometries are silently repaired
using `shapely.make_valid()` (equivalent to PostGIS `ST_MakeValid()`).

To disable: set `geoengine.validate_geometry` config parameter to `"False"`.

### Geometry Size Limits

**Problem:** Extremely large geometries (complex polygons with thousands of vertices)
can cause performance issues.

**Limit:** `geoengine.max_geometry_size` config parameter (default: 1,000,000 bytes WKT).
Geometries exceeding this are rejected with `ValueError`.

### Classification nb_class vs Data

**Problem:** Setting `nb_class=5` on a vector layer when the data has only 3 distinct
values causes `geostats.js` to throw "N classes are defined for only M values".

**Prevention:** the classifier asks geostats for at most `values - 1` quantile
classes, counting **values, not distinct values**: geostats tests
`nbClass >= serie.length` in `_classificationCheck`, which only
`getClassQuantile` calls. Fewer than two values leave the layer unclassified.
Until 2026-10-01 a save-time constraint (`_check_nb_class_vs_data`) checked this
against the rows present when the layer was saved -- data that changes after the
save, and that the user saving may not see -- while the client still allowed
`nb_class == values` and threw. `interval` and `unique` are unconstrained.

The `nb_class_recommended` computed field is the one that counts distinct values
-- `min(max(1, distinct - 1), 10)`. It is advisory and caps at 10.

### Missing info_box Template

**Problem:** `_check_info_box_template()` raises `ValidationError` if the geoengine
view XML does not contain `<templates><t t-name="info_box">...</t></templates>`.

**Fix:** Always include an info_box template in your geoengine view, even if minimal.

### Missing Raster or Vector Layers

**Problem:** A geoengine view without raster layers has no map background (blank canvas).
A view without vector layers shows no data.

**Prevention:** none at save time, and there cannot be any: layers point at the
view by FK, so they can only exist after the view is saved. The check runs at
render time instead -- `Base._validate_geo_view_configuration()`, called from
`get_layers()`, returns `{valid, errors, warnings}`, which is logged as a warning
server-side and shipped to the client under the `validation` key. It does not
raise.

There is no save-time `ValidationError` for missing layers; the check that once
claimed to be one was removed as dead code.

### Distance Units in geo_dwithin

**Problem:** `ST_DWithin` distance units depend on the SRID:
- EPSG:3857: meters (approximate, distorted near poles)
- EPSG:4326: degrees (not meters!)
- UTM zones: meters (accurate within zone)

**Rule:** pass a unit. `geo_dwithin` accepts `{'geometry': g, 'distance': d,
'unit': 'm'}`; on a WGS84 field that casts both operands to `geography` so PostGIS
measures true metres on the ellipsoid, and the in-memory path measures the same
geodesic distance. Without `unit` (or with `unit='srid'`) the distance is in the
SRID's own units, which on EPSG:4326 is **degrees** -- `distance: 1000` there
matches Zurich and Geneva, 250 km apart.

### Column Type Changes: SRID Migrates, Type Does Not

Changing a field's `srid` or `geo_type` against an existing column is caught by
`update_db_column`, whose `_sync_geometry_column` reads `geometry_columns` once
and splits the two cases:

- **SRID only** (same geometry type and dimension, known SRID): migrated in place
  with `ALTER TABLE ... TYPE geometry(T[Z], new) USING ST_Transform(col, new)`,
  the field's full type, so a 3D column stays 3D. Existing
  rows are reprojected. It logs `odoo.schema: Migrated geometry column
  <table>.<col> SRID <old> -> <new>` -- watch for that line on upgrade.
- **Type or dimension change** (`GeoPoint` -> `GeoPolygon`, `dim` 2 -> 3), or
  missing `geometry_columns` metadata: **not** migrated. It logs a warning
  ("cannot be auto-migrated") and continues, leaving the column as it was, so
  later writes of the new type fail against the old column constraint.

**Workaround for the second case only:** drop and recreate the column in a
migration script.

### Related GeoField SRID Inheritance

GeoField defines `_related_srid` and `_related_dim` properties to ensure that
related geo fields inherit SRID and dimension from the source field. Without these,
a `related="partner_id.location"` field would silently use the default SRID (3857)
even if the source field uses 4326.

### Test Database Requires PostGIS

The `pre_init_hook` creates PostGIS extensions. If using a fresh test database,
ensure the PostgreSQL user has `CREATE EXTENSION` privileges, or pre-create the
extensions manually before running tests.
