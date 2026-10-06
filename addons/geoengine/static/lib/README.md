# Vendored libraries

Third-party libraries shipped inside the `geoengine` module. The conventions here are
`web/static/lib/README.md`'s — read that one first; this file records only what is
specific to these three.

All three are **ES modules resolved through the browser import map**, not scripts that
install a global. Each answers to a bare specifier declared by **this module's own
`__manifest__.py`**, under the `esm.external_libs` key — a mapping of bare specifier to
root-relative URL:

| Specifier | Resolves to |
|---|---|
| `ol` | `/geoengine/static/lib/ol/ol.esm.js` |
| `chroma-js` | `/geoengine/static/lib/chroma-js/chroma.esm.js` |
| `geostats` | `/geoengine/static/lib/geostats/geostats.js` |
| `proj4` | `/geoengine/static/lib/proj4/proj4.esm.js` |

Three things read that one declaration, which is why nothing else needs editing to add a
library:

* odoo's esm_registry.py merges every module's `external_libs` into one table. A specifier
  declared twice with different URLs is a `ValueError` naming both modules — one
  specifier resolves to one URL, and the module that ships the file owns it.
* `external_bare_specifiers()` derives from that table, and esbuild.py turns each entry
  into an `--external:<specifier>` flag. That is what makes esbuild leave the import
  alone instead of trying to bundle it.
* `import_map_for()` (odoo/tools/assets/import_map.py) builds the browser import map
  from the same table, and raises `KeyError` telling you which manifest key to declare
  when a specifier was never registered.

Registration used to be two hardcoded lists in the framework — `ODOO_EXTERNAL_LIBS` in
odoo/tools/assets/constants.py and `EXTERNAL_BARE_SPECIFIERS` in
odoo/tools/assets/esbuild.py. Odoo `491b6c0f3bb` (2026-08-16) replaced both with the
manifest key, so **neither name exists anywhere in the tree today**; a search that finds
one is reading history. The 19.0.1.6.0 entry in `../../ARCHITECTURE.md` names them
because they were real on 2026-08-09 — leave that entry alone.

They are **not** imported statically. A top-level `import` in `web.assets_backend`
would resolve when that bundle loads, pulling ~770 KB into every backend page for the
majority of users who never open a map. `@geoengine/lib/geo_libs` performs one
dynamic `import()` instead, so the cost is paid when a map view opens — the same
laziness the previous `loadJS()` arrangement had, without the globals.

Getting static named imports (and with them real eslint/tsc checking at each call
site) means moving the renderer into its own lazy bundle, the way
`web.assets_emoji` works (a dynamic child of the page bundles). That is a
worthwhile follow-up and a larger change than this one.

## Inventory

`versions.json` is the authority; this table is a reading aid.

| Directory | Version | Upstream | Notes |
|---|---|---|---|
| `ol/` | 10.10.0 | `ol` | **Locally built, not pristine.** `entry.js` names the 62 symbols the fork uses; `build.sh` tree-shakes the rest away. |
| `chroma-js/` | 3.2.0 | `chroma-js` | Single-file ESM build of the package's default entry. |
| `geostats/` | 2.1.0 | `geostats` | Upstream source, readable, 4 `AgroMarin:` markers. **Fork-modified.** |
| `proj4/` | 2.22.0 | `proj4` | Single-file ESM build; imported only by a map whose projection OpenLayers does not resolve itself. |

### Libraries needing extra care

**`ol/`** is the one library here whose shipped size is a decision rather than a fact.
`entry.js` is the inventory: esbuild includes what it reaches and drops everything
else, so a single added export can pull in a large subsystem. Check the byte count
`build.sh` prints before and after when you add one. Never edit `ol.esm.js` by hand —
it is generated, and `build.sh` overwrites it.

Measured, so the trade is not re-argued from scratch each time:

| Addition | Bundle |
|---|---|
| baseline, the 62 symbols shipped today | 692 KB |
| single-image WMS + MVT vector tiles | +35 KB |
| COG/GeoTIFF (`ol/source/GeoTIFF`, pulls in `geotiff`) | **+600 KB — rejected** |

`tests/test_ol_inventory_contract.py` gates all of this, three ways: no call site
may name a symbol the entry does not export (the miss `507409de` had to fix by
hand); the built bundle must contain every symbol the entry exports, so an entry
edited without re-running `build.sh` fails rather than shipping a stale file; and
the entry must not export a symbol nothing mentions. Four exports are JSDoc-only
(`Collection`, `color.asArray`, `geom.Geometry`, `layer.Layer`) and are kept
deliberately — dropping all four was measured at **328 bytes**, because esbuild
pulls the base classes in transitively anyway.

`ol.d.ts` from the npm package is deliberately **not** vendored. It describes the full
library, not this subset, so it would type-check symbols the bundle does not ship.

**`geostats/`** is unmaintained upstream (2.1.0 is the last release) and its source
predates strict mode, which is the whole reason it carries markers: implicit globals
that were harmless under a `<script>` tag are `ReferenceError`s inside a module. Two of
the four markers are exactly that, one of them on the live choropleth legend path. If a
fifth turns up, prefer replacing the library over patching again — geoengine uses only
quantile/equal-interval/unique classification, `min`/`max` and the HTML legend, and
`static/src/geoengine/classification.js` already owns the classification contract.

Its `geostats.css` is **not** vendored: geoengine styles the `geostats-legend-*` classes
itself, in `static/src/css/style.scss` and `static/src/geoengine/geoengine_renderer.scss`.

## Update procedure

1. Confirm the upgrade is needed — an advisory, a required feature, a license change.
2. For `ol`, `chroma-js` and `proj4`, run the directory's `build.sh`. For `geostats`, replace the
   file and re-apply every `AgroMarin:` marker (`grep -n "AgroMarin:" geostats/` on the
   outgoing file is the complete list).
3. Update `versions.json` and the table above in the same commit.
4. Re-run the JS suites: `odoo-bin … -i geoengine --test-enable --test-tags
   '/web:AddonSuite.test_geoengine' --http-port <free port> --stop-after-init`.
5. Open a map view and confirm the layers, choropleth legend and draw/modify tools still
   work — none of the suites exercise the renderer against a real OpenLayers.
6. Check the LICENSE. If it changed upstream, surface that in the PR description.
