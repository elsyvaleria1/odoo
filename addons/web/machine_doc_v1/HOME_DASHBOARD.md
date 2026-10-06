# Home dashboard: data tiles, layers, tint

The home menu's board opens with the user's **data tiles**, cards that each show one thing
that needs attention (recent records, activities, transfers…) and open the list or record
behind it; the launcher widgets follow. This page is the map; the plan and its decisions are
in the knowledge vault's iCloud interface plan (2026-09-25), phase P4.

## Server

| Piece | Where | What |
|---|---|---|
| `home.tile` (AbstractModel) | `models/home_tile.py` | `_get_tile_types()` (type → name, sizes, gating model and, for a tile that summarises a screen, that screen's `menu`), `get_tile_types()` (the ones this user may use: internal users, read access on the type's model, and the `menu` visible to them), `get_tile_types()` and `get_tiles(requests)` (both `@api.readonly`; one savepoint per tile; a type the user may not use, a vanished source or an `AccessError` inside one tile reads as `"unavailable"` for that tile alone, any other failure as `{"error": "failed"}`), `get_metric_choices()` (a favourite's domain is evaluated as the web client would, `uid` and `context_today()` included, by `ir.filters._get_domain_evaluated()`), `_get_starter_tiles()`. A type adds `_get_tile_<type>_data(settings)` and, when it has settings, `_normalize_tile_<type>_settings(settings)`. |
| `web.recent.record` | `models/web_recent_record.py` | The records a user opened (`note_opened`, batched and debounced by the form), ordered by an integer `recency`, capped per user by an autovacuum. |
| layout | `models/res_users_settings.py` | `home_tiles` Json `{version, tiles: [{id, type, size, settings?}], background?}`, written only by `update_home_tiles(changes)` (`add`, `remove`, `resize`, `move`, `configure`, `background`, `reset`); `_home_tiles_layers()` lists the layouts below a user's own, most specific first; `_home_tiles_default()` is the first one set, else `home.tile._get_starter_tiles()` (web's Recently opened 2x1, which mail precedes with Activities 1x1), filtered to the types the user may use; a company that sets an empty layout opts out of it. A user's own layout keeps a tile whose type they cannot use for now (it reads as unavailable and returns with the access); only an uninstalled type is dropped. `_home_tints()` names the background tints and their labels. |
| company default | `models/web_config.py` | `home_tiles_default`, set by `set_home_tiles_default()` (write access to `web.config`, i.e. `base.group_system`); it carries the publisher's background. |
| session | `models/ir_http.py` | `session_info.home_tiles_default`: the resolved default for an internal user; `session_info.home_tints`: the tints the customize toolbar offers. |

9 modules extend `home.tile` in this checkout (web, mail, calendar, stock, account, approval,
device, account_credit, wallet); AgroMarin adds its own (low wallet balances).

## Client

| Piece | Where | What |
|---|---|---|
| `HomeTiles` | `webclient/home_menu/home_tiles/home_tiles.js` | Renders the tiles (skeleton, error, component; each component inside an error boundary that shows the tile as not loaded and warns), customize mode (add, resize, remove, move buttons, drag, settings panel), a live announcement of every change. A tile keeps only the answer of its latest load. |
| `HomeTilesModel` | `webclient/home_menu/home_tiles/home_tiles_model.js` | The layout and whether it is the user's own; sends one change at a time; owned by `HomeMenu`, whose toolbar's "Follow company layout" and "Set as company default" cover it and wait while anything saves. |
| `home_tiles` registry | same file as `HomeTiles` | `{ Component, Settings?, title? }` per type; a type's component takes `{ data, size }`, and `title(data)` names one tile when its type's name would not tell two apart. |
| `HomeTileRecordLink` | `webclient/home_menu/home_tiles/home_tile_record_link.js` | A tile's link to one record: a real `/odoo/<model>/<id>` href, the form opened in place on a plain click, a modified click left to the browser. Every tile that lists records uses it; a row that opens a filtered list is a button. |
| `recent_records` service | `core/recent_records_service.js` | Notes what the form opens. |

11 tile types register a component in this checkout. Each type's test pins its
`get_tiles` statement count (the tile test file in each module).

## Tint

The board's background may take one of 7 tints (`$o-home-menu-tints` in
`webclient/home_menu/home_menu.variables.scss`): a gradient over grayscale arcs
(`home_menu_arcs_mono_light.svg` / `_dark`) blended hard-light, one colour pair per tint and scheme.
It is the web client's canvas, not the board's alone: `.o_web_client` paints `--o-canvas-*` behind
every view, and `body[data-home-tint]` is set from the user's layout (or the company default) when
the web client starts and whenever the board changes it. A company's own background image still
wins on the board.

Views share the board's material through the `--o-glass-*` tokens (`scss/primary_variables.scss`,
`scss/palette_dark.scss`) and the `o-glass-surface`, `o-glass-lift`, `o-glass-bar`,
`o-glass-button` and `o-hover-fill` mixins (`scss/utils.scss`): kanban cards, the list table, the
form sheet, the navbar, the control panel and the form's status bar, and every dropdown and navbar
hover.
