import logging
from dataclasses import dataclass

from psycopg import errors as pg_errors

from odoo.exceptions import UserError
from odoo.models import BaseModel
from odoo.tools import SQL, mute_logger

from .fields import GeoField
from .geo_types import POINT_TTYPES

_logger = logging.getLogger(__name__)

WEB_MERCATOR = 3857
WEB_MERCATOR_WIDTH = 40075016.68557849
TILE_EXTENT = 4096
TILE_BUFFER = 64
MAX_TILE_ZOOM = 24
FINE_GRID_MIN_ZOOM = 14
CLUSTER_CELLS = 16
FINE_CELLS = 128
ENVELOPE_SEGMENTS = 16
DEFAULT_TILE_TIMEOUT_MS = 4000
LAYER_NAME = "features"
FEATURE_ID = "fid"
CELL_COUNT = "count"
CELL_KEY = "cell"
HEAT_CELL_PX = 8
MAX_HEAT_CELLS = 40_000


@dataclass(frozen=True)
class HeatView:

    minx: float
    miny: float
    maxx: float
    maxy: float
    cell: float

    @classmethod
    def checked(cls, env, extent, zoom) -> HeatView:
        half = WEB_MERCATOR_WIDTH / 2
        try:
            minx, miny, maxx, maxy = (float(v) for v in extent)
            zoom = float(zoom)
        except TypeError, ValueError:
            raise UserError(env._("A heatmap view is an extent and a zoom.")) from None
        minx, maxx = max(minx, -half), min(maxx, half)
        miny, maxy = max(miny, -half), min(maxy, half)
        if not (minx < maxx and miny < maxy and 0 <= zoom <= MAX_TILE_ZOOM):
            raise UserError(env._("A heatmap view is an extent and a zoom."))
        cell = WEB_MERCATOR_WIDTH / 256 / 2**zoom * HEAT_CELL_PX
        cells = (maxx - minx) * (maxy - miny) / cell**2
        if cells > MAX_HEAT_CELLS:
            cell *= (cells / MAX_HEAT_CELLS) ** 0.5
        return cls(minx, miny, maxx, maxy, cell)

    def envelope_in(self, srid: int) -> SQL:
        envelope = SQL(
            "ST_MakeEnvelope(%s, %s, %s, %s, %s)",
            self.minx,
            self.miny,
            self.maxx,
            self.maxy,
            WEB_MERCATOR,
        )
        if srid == WEB_MERCATOR:
            return envelope
        return SQL(
            "ST_Transform(ST_Segmentize(%s, %s), %s)",
            envelope,
            max(self.maxx - self.minx, self.maxy - self.miny) / ENVELOPE_SEGMENTS,
            srid,
        )


def cell_size(z: int) -> float:
    cells = FINE_CELLS if z >= FINE_GRID_MIN_ZOOM else CLUSTER_CELLS
    return WEB_MERCATOR_WIDTH / 2**z / cells


@dataclass(frozen=True)
class Cell:

    z: int
    i: int
    j: int

    @classmethod
    def checked(cls, env, key: str) -> Cell:
        try:
            z, i, j = (int(part) for part in str(key).split("/"))
        except ValueError:
            z = i = j = None
        half = 2**MAX_TILE_ZOOM * FINE_CELLS
        if (
            z is None
            or not 0 <= z <= MAX_TILE_ZOOM
            or not -half <= min(i, j) <= max(i, j) < half
        ):
            raise UserError(env._("%s is not a map cell.", key))
        return cls(z, i, j)

    def contains(self, point: SQL) -> SQL:
        size = cell_size(self.z)
        return SQL(
            "floor(ST_X(%s) / %s) = %s AND floor(ST_Y(%s) / %s) = %s",
            point,
            size,
            self.i,
            point,
            size,
            self.j,
        )

    def envelope_in(self, srid: int) -> SQL:
        size = cell_size(self.z)
        envelope = SQL(
            "ST_MakeEnvelope(%s, %s, %s, %s, %s)",
            self.i * size,
            self.j * size,
            (self.i + 1) * size,
            (self.j + 1) * size,
            WEB_MERCATOR,
        )
        if srid == WEB_MERCATOR:
            return envelope
        return SQL(
            "ST_Transform(ST_Segmentize(%s, %s), %s)",
            envelope,
            size / ENVELOPE_SEGMENTS,
            srid,
        )


@dataclass(frozen=True)
class Tile:
    z: int
    x: int
    y: int

    @classmethod
    def checked(cls, env, z: int, x: int, y: int) -> Tile:
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (z, x, y)):
            raise UserError(env._("A tile is addressed by integer z, x and y."))
        if not 0 <= z <= MAX_TILE_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
            raise UserError(
                env._("Tile %(z)s/%(x)s/%(y)s does not exist.", z=z, x=x, y=y)
            )
        return cls(z, x, y)

    def envelope(self, margin: float = 0.0) -> SQL:
        if margin:
            return SQL(
                "ST_TileEnvelope(%s, %s, %s, margin => %s)",
                self.z,
                self.x,
                self.y,
                margin,
            )
        return SQL("ST_TileEnvelope(%s, %s, %s)", self.z, self.x, self.y)

    def envelope_in(self, srid: int, margin: float = 0.0) -> SQL:
        envelope = self.envelope(margin)
        if srid == WEB_MERCATOR:
            return envelope
        tile_width = WEB_MERCATOR_WIDTH / 2**self.z
        return SQL(
            "ST_Transform(ST_Segmentize(%s, %s), %s)",
            envelope,
            tile_width / ENVELOPE_SEGMENTS,
            srid,
        )


def tile_timeout_ms(env) -> int:
    raw = env.registry.settings.get(
        env, "geoengine.tile_timeout_ms", str(DEFAULT_TILE_TIMEOUT_MS)
    )
    try:
        return max(int(raw), 1)
    except TypeError, ValueError:
        _logger.warning(
            "geoengine.tile_timeout_ms is %r, not milliseconds; using %d",
            raw,
            DEFAULT_TILE_TIMEOUT_MS,
        )
        return DEFAULT_TILE_TIMEOUT_MS


def _property_sql(model: BaseModel, alias: str, field_name: str, query) -> SQL:
    field = model._fields[field_name]
    column = model._field_to_sql(alias, field_name, query)
    if field.type in ("integer", "many2one", "boolean"):
        return column
    if field.type in ("float", "monetary"):
        return SQL("%s::float8", column)
    return SQL("%s::text", column)


def _in_web_mercator(column: SQL, srid: int) -> SQL:
    if srid == WEB_MERCATOR:
        return column
    return SQL("ST_Transform(%s, %s)", column, WEB_MERCATOR)


def tile_sql(
    model: BaseModel,
    field: GeoField,
    domain,
    tile: Tile,
    property_names: list[str],
) -> SQL:
    query = model._search(domain)
    query.order = None
    alias = query.table
    column = model._field_to_sql(alias, field.name, query)
    clustered = field.type in POINT_TTYPES
    margin = 0.0 if clustered else TILE_BUFFER / TILE_EXTENT
    query.add_where(SQL("%s && %s", column, tile.envelope_in(field.srid, margin)))
    properties = [
        (name, _property_sql(model, alias, name, query)) for name in property_names
    ]
    geometry = _in_web_mercator(column, field.srid)

    if not clustered:
        rows = query.select(
            SQL("%s AS %s", SQL.identifier(alias, "id"), SQL.identifier(FEATURE_ID)),
            *(SQL("%s AS %s", sql, SQL.identifier(name)) for name, sql in properties),
            SQL(
                "ST_AsMVTGeom(%s, %s, %s, %s, true) AS geom",
                geometry,
                tile.envelope(),
                TILE_EXTENT,
                TILE_BUFFER,
            ),
        )
        return SQL(
            "SELECT ST_AsMVT(rows, %s, %s, 'geom', %s) FROM (%s) AS rows",
            LAYER_NAME,
            TILE_EXTENT,
            FEATURE_ID,
            rows,
        )

    members = query.select(
        SQL("%s AS fid", SQL.identifier(alias, "id")),
        *(SQL("%s AS %s", sql, SQL.identifier(name)) for name, sql in properties),
        SQL("%s AS point", point_in_web_mercator(field, geometry)),
    )
    single = [
        SQL(
            "CASE WHEN count(*) = 1 THEN (array_agg(placed.%s))[1] END AS %s",
            SQL.identifier(name),
            SQL.identifier(name),
        )
        for name, _sql in properties
    ]
    size = cell_size(tile.z)
    cells = SQL(
        """SELECT count(*) AS %(count)s,
                  CASE WHEN count(*) = 1 THEN min(placed.fid) END AS %(fid)s,
                  %(address)s
                  %(single)s
                  ST_AsMVTGeom(ST_Centroid(ST_Collect(placed.point)), %(envelope)s,
                               %(extent)s, 0, true) AS geom
             FROM (SELECT members.*,
                          floor(ST_X(members.point) / %(size)s)::bigint AS ci,
                          floor(ST_Y(members.point) / %(size)s)::bigint AS cj
                     FROM (%(members)s) AS members) AS placed
         GROUP BY placed.ci, placed.cj""",
        count=SQL.identifier(CELL_COUNT),
        fid=SQL.identifier(FEATURE_ID),
        address=SQL(
            "CASE WHEN count(*) > 1 THEN concat_ws('/', %s, placed.ci, placed.cj) END AS %s,",
            tile.z,
            SQL.identifier(CELL_KEY),
        )
        if tile.z >= FINE_GRID_MIN_ZOOM
        else SQL(""),
        single=SQL("").join(SQL("%s,", s) for s in single),
        envelope=tile.envelope(),
        extent=TILE_EXTENT,
        members=members,
        size=size,
    )
    return SQL(
        "SELECT ST_AsMVT(cells, %s, %s, 'geom', %s) FROM (%s) AS cells",
        LAYER_NAME,
        TILE_EXTENT,
        FEATURE_ID,
        cells,
    )


def heat_cells_sql(
    model: BaseModel,
    field: GeoField,
    domain,
    view: HeatView,
    weight_name: str | None,
) -> SQL:
    query = model._search(domain)
    query.order = None
    column = model._field_to_sql(query.table, field.name, query)
    query.add_where(SQL("%s && %s", column, view.envelope_in(field.srid)))
    weight = (
        SQL(
            "coalesce(%s, 0)::float8",
            model._field_to_sql(query.table, weight_name, query),
        )
        if weight_name
        else SQL("1::float8")
    )
    members = query.select(
        SQL("%s AS point", point_in_web_mercator(field, column)),
        SQL("%s AS weight", weight),
    )
    return SQL(
        """SELECT coalesce(json_agg(json_build_array(cells.x, cells.y, cells.w)), '[]')
             FROM (SELECT avg(ST_X(members.point)) AS x, avg(ST_Y(members.point)) AS y,
                          sum(members.weight) AS w
                     FROM (%s) AS members
                 GROUP BY floor(ST_X(members.point) / %s),
                          floor(ST_Y(members.point) / %s)) AS cells
            WHERE cells.w > 0""",
        members,
        view.cell,
        view.cell,
    )


def point_in_web_mercator(field: GeoField, column: SQL) -> SQL:
    point = column if field.type == "geo_point" else SQL("ST_Centroid(%s)", column)
    return _in_web_mercator(point, field.srid)


def cell_records_query(model: BaseModel, field: GeoField, domain, cell: Cell):
    query = model._search(domain, order=model._order)
    column = model._field_to_sql(query.table, field.name, query)
    query.add_where(SQL("%s && %s", column, cell.envelope_in(field.srid)))
    query.add_where(cell.contains(point_in_web_mercator(field, column)))
    return query


def fetch_within_budget(env, sql: SQL, timeout_ms: int | None = None) -> tuple | None:
    timeout = timeout_ms or tile_timeout_ms(env)
    env.flush_query(sql)
    try:
        with mute_logger("odoo.db.cursor"), env.cr.savepoint(flush=False):
            [[previous, _]] = env.execute_query(
                SQL(
                    "SELECT current_setting('statement_timeout'), "
                    "set_config('statement_timeout', %s, true)",
                    str(timeout),
                )
            )
            [row] = env.execute_query(sql)
            env.execute_query(
                SQL("SELECT set_config('statement_timeout', %s, true)", previous)
            )
    except pg_errors.QueryCanceled:
        _logger.info("Map query exceeded its %d ms budget", timeout)
        return None
    return row


def render_tile(env, sql: SQL) -> bytes | None:
    row = fetch_within_budget(env, sql)
    if row is None:
        return None
    return bytes(row[0] or b"")


def extent_sql(model: BaseModel, field: GeoField, domain) -> SQL:
    query = model._search(domain)
    query.order = None
    column = model._field_to_sql(query.table, field.name, query)
    extent = SQL("ST_SetSRID(ST_Extent(%s)::geometry, %s)", column, field.srid)
    return SQL(
        "SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) FROM (%s) AS x(e)",
        query.select(_in_web_mercator(extent, field.srid)),
    )
