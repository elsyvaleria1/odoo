# ESM Bundling — End-to-End Pipeline

Code path an asset travels from a `.js` file on disk to an executing module
in the browser, with observability hooks, failure modes, and tunable knobs.

## Pipeline diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│ File on disk                                                         │
│   /addons/<addon>/static/src/**/*.js                                 │
│   Pragma: /** @odoo-module native */                                 │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  is_native_module() / is_odoo_module()
                                │  odoo/tools/assets/esm_graph.py
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ AssetsBundle.__init__()   assetsbundle/bundle.py                     │
│   files partitioned into:                                            │
│     • self.javascripts         (classic JS; legacy bundle)           │
│     • self.native_modules      (@odoo-module [native]; esbuild fuel) │
│     • self.templates           (XML for QWeb)                        │
│     • self.stylesheets         (SCSS/CSS)                            │
│   Only when bundle name ∈ esm_registry().bundles                     │
│   (assetsbundle/bundle.py sets self._is_esm_bundle).                 │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ HTTP GET /odoo                                                       │
│   ir_qweb._get_asset_nodes(bundle, debug)  ir_qweb_assets.py         │
└──────────┬────────────────────────────────┬──────────────────────────┘
           │  debug mode                    │  production
           ▼                                ▼
┌───────────────────────────┐   ┌───────────────────────────────────────┐
│ Per-file serve            │   │ Admin override? (config param)        │
│   get_native_module_data  │   │ Circuit open? (_esbuild_cooldowns)    │
│   → import_map per spec   │   │ Wait for pg_advisory_xact_lock        │
│   → <link modulepreload>  │   └─────────────────┬─────────────────────┘
│   → <script type=module>  │                     │  all green
│       /<addon>/static/... │                     ▼
└────────────┬──────────────┘   ┌────────────────────────────────────────┐
             │                  │ esbuild_native_bundle()                │
             │                  │   assetsbundle/bundle.py               │
             │                  │                                        │
             │                  │ 1. Generate entry.js (piped on STDIN — │
             │                  │    nothing written to the code tree):  │
             │                  │      import * as __owl from "@odoo/owl";│
             │                  │      import * as __m0 from "./path0";   │
             │                  │      ...                               │
             │                  │      odoo.loader.registerNativeModules(│
             │                  │        {"@odoo/owl":__owl,"@spec/0":..})│
             │                  │      (+ hoot-family modules.set aliases)│
             │                  │                                        │
             │                  │ 2. subprocess(esbuild, cwd=odoo_root,  │
             │                  │      --bundle --format=esm --minify    │
             │                  │      --keep-names --target=<target>    │
             │                  │      --external:@odoo/*                │
             │                  │      --external:/web/static/lib/*      │
             │                  │      --external:<EXTERNAL_BARE_SPEC>...│
             │                  │      --alias:<lib/header/stub>         │
             │                  │      NODE_PATH=<@addon symlink root>   │
             │                  │      --resolve-extensions=.js,.mjs,... │
             │                  │      --outfile --metafile [--sourcemap]│
             │                  │      timeout=<timeout_s>)              │
             │                  │                                        │
             │                  │ 3. Read output.js + metafile.json      │
             │                  │ 4. Write attachment (+ .meta.json,     │
             │                  │    .esm.js.map siblings):              │
             │                  │  /web/assets/esm/<hash>/<bundle>.esm.js│
             │                  └─────────────────┬──────────────────────┘
             │                                    │
             └───────────────────┬────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Rendered HTML                                                             │
│   pre_nodes:                                                              │
│     <script>/* module_loader.js shim */</script>    (inline)              │
│     <script type="importmap">{imports:{@odoo/*: ...,}}</script>           │
│     <link rel="modulepreload" href="/web/assets/lib/..."> (prod only:   │
│       each library the bundle imports statically, e.g. owl)              │
│   [legacy bundle, if any]                                                 │
│   post_nodes:                                                             │
│     <script type="module" src=".../esm/<hash>/<bundle>.esm.js"            │
│             data-bridge="<bundle>"></script>                              │
│     <script type="module">import { templates } from @web/core/...</script>│
└───────────────────────────────┬───────────────────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Browser                                                                   │
│   1. Shim executes (sync): globalThis.odoo.loader = new OdooModuleLoader()│
│   2. Import map resolves @odoo/owl etc. to vendored ESM                   │
│   3. Bundle <script type=module> fetches, parses, executes                │
│   4. Bundle entry calls odoo.loader.registerNativeModules({...})          │
│   5. Template module calls odoo.loader.modules.get("@web/core/templates") │
│   6. boot/main.js → boot/start.js → mountComponent(WebClient)             │
└───────────────────────────────────────────────────────────────────────────┘
```

### A page bundle registers only what something outside it names

The entry esbuild compiles for a page bundle imports every member as a
namespace and hands the whole map to `odoo.loader.registerNativeModules`, which
keeps every export of every member alive. Since 2026-09-06 a member is a
namespace import only when something outside the bundle names it
(`_get_exported_specs`, `ir_qweb_assets_esbuild.py`; `EsbuildCompiler`'s
`exported_specs`): a bare or relative import from a declared consumer — its
dynamic children, its secondary and import-map satellites, and the children of
any declared parent whose members include all of this bundle's (the
`web.assets_frontend_minimal` / `web.assets_frontend_lazy` family) — or a
string literal equal to a member specifier that is not the target of a static
import, anywhere in the bundle or a consumer (`odoo.loader.modules.get("…")`,
the `html_editor_upgrade` registry values `html_upgrade_manager` reads).
`@web/core/templates` and `@web/core/assets` (the lazy-loading entry point a
tour or an embedding script reads off the loader) are always in. Every other member is `import "./path"`:
evaluated for its side effects, its unused exports shaken. Satellites
(`secondary_import_map_includes`, `import_map_includes` children) register
everything, because their consumers are the runtime children of the pages
they ride on. Measured on `web.assets_web` with website and mass_mailing
installed: 203 of 1,667 members registered, 5.6 % fewer bytes raw and 6.1 %
gzipped. `TestPageBundleExportSurface` pins the rule: the surface is a strict
subset, every child import and every literal stays in, and the compiled code
registers exactly the surface.

## Declarative ESM registry (`odoo.tools.assets.esm_registry`)

ESM bundle membership is **declarative**, not hardcoded: each module declares
its own ESM bundle relationships in its `__manifest__.py` under an
`esm` key; the aggregate is built once per process from
`Manifest.get_all_addon_manifests()` by `esm_registry()`
(odoo/tools/assets/esm_registry.py, returning an `EsmRegistry`
NamedTuple) and invalidated by `invalidate_esm_registry()`,
wired into `AssetsBundle.invalidate_addon_scan_cache` (the canonical
"addons on disk changed" signal from `ir.module.module.update_list()`).

| `esm` manifest key | Purpose |
|-----|---------|
| `bundles` | This module's esbuild-compiled bundles |
| `exports` | Module specifiers (starting with `@`) to expose from a compiled bundle when they belong to that bundle; merged into its exported members by `ir_qweb_assets_esbuild.py` |
| `runtime_bundles` | Bundles fetched at runtime through `/web/bundle` (`loadBundle`). A property of the BUNDLE — no parent page is named. Aggregated into `EsmRegistry.runtime_bundle_names` (together with every `dynamic_children` child), which is the predicate `use_esm` reads in `web/controllers/webclient.py`; without it the route serves the legacy branch and every module-syntax file becomes a `console.error` stub while `loadBundle` still resolves. A runtime bundle with **no** declared parent is served **per file** (there is no page whose modules could be stubbed), so a bare `runtime_bundles` entry is the debug shape in production; declare the parent under `dynamic_children` to get the compiled child. Because such a bundle is fetched into whatever page asks for it, `_get_export_consumers` counts it as a consumer of every page bundle, so a compiled page registers the specifiers it imports; before, `project_gantt.project_sharing_unit_tests` read `undefined` for `@web/views/kanban` and failed at `class … extends` |
| `dynamic_children` | Parent → lazy children. Declaring a parent does three things: the parent's page does not bridge the child's specifiers; the child is a runtime bundle without restating it; and, since 2026-09-06, the child is **compiled** against that parent (`_get_compiled_runtime_payload`, below) instead of being served per file. With several parents the child is compiled against the modules **every** installed parent owns (intersection), so it loads on any of their pages. A parent module that imports a child's specifier gets a bridge, a binding the loader fills when the child registers: it may read it inside a function, never while it is evaluated (`class … extends`, a top-level call, a static field), where it is `undefined`. A compile that meets one logs `bridge_read_at_evaluation` on `odoo.assets.bridge` naming the module, line and binding (`get_evaluation_time_bridge_uses`, the lexer worker's `evaluation_uses` op); move the module into a bundle that includes the child, as `website_forum.assets_forum_editor` does |
| `dynamic_children_from` | Page → the page whose `dynamic_children` it takes, declared by the module that owns the page. For a second page built on the same code as a base page, such as `knowledge.webclient` and `document.webclient`, which include `web.assets_backend` as `web.assets_web` does: children are keyed on the page name, so without it every child another module declares on `web.assets_web` (`spreadsheet.o_spreadsheet`, the `web_tour` runtimes, `html_editor`'s) is missing from the variant, whose import map then cannot resolve `@odoo/o-spreadsheet`. Expanded once in `_prepare_esm_registry`, so every reader sees an ordinary parent. The base must be a registered bundle that takes its children from nobody, one page names one base, and restating an inherited child is refused |
| `import_map_includes` | Parent → satellites reusing the parent's import map, skipping esbuild; used for test-runner bundles |
| `classic_pages` | Page bundles delivered as one classic script instead of a module script, so that the browser keeps their compiled code across loads (*The web client's page bundle is a classic script*, below). Aggregated into `EsmRegistry.classic_page_bundles`. Only a bundle a document loads with a script tag: `_prepare_esm_registry` refuses a dynamic child, a runtime bundle, a standalone bundle and a name that is not a registered bundle, since nothing can import a classic script |
| `external_libs` | Bare specifier → root-relative URL for a library this module ships (`@odoo/owl`, `chartjs-chart-geo`, …). One specifier resolves to one URL and the owning module declares it; a second module declaring it differently is an error |
| `exports` | Module specifiers (`@web/core/registry`, …) that must stay reachable **by name** from outside the bundle graph — a test's `browser_js`, a tour started from Python — which no scan of JavaScript sources can discover, so the module that owns them declares them. Aggregated into `EsmRegistry.exports`; `_get_exported_specs` (`ir_qweb_assets_esbuild.py`) adds them to a compiled page's exports beside the specifiers its consumers import. Anything not starting with `@` is rejected at registry build |
| `secondary_import_map_includes` | Parent → satellites loaded as a separate later `<script>`; only the satellite's NEW import-map specifiers merge into the parent's map. **Gated**: the merge runs only when the satellites are actually rendered (`'tests' in debug or test_mode_enabled`), the same condition `web.conditional_assets_tests` uses. A child that is itself declared a parent (`EsmRegistry.page_secondaries`: `web.assets_frontend_lazy` under `web.assets_frontend_minimal`) is the second half of a split page, not a satellite: it keeps a page bundle's export surface, and neither it nor the satellites it declares are merged into the first half's map |

Choosing between the last two, since both silence the "module-syntax file in a
non-ESM bundle" stub and neither raises when it is the wrong one:

- `import_map_includes` — the child is **never compiled**: `EsbuildCompiler.compile`
  returns an empty result when `_import_map_included` is set
  (fed from `registry.import_map_included_bundles` in `AssetsBundle._prepare_esbuild_compiler`). Its specifiers
  ride the parent's map and resolve to individual source URLs, which is what a test
  runner loading files on demand wants.
- `secondary_import_map_includes` — the child **is** compiled, and this is the only
  key that populates `secondary_parents`, the mapping that makes esbuild `--alias`
  the child's shared specifiers onto `odoo.loader.modules` shims
  (`esbuild_stubs.mirror_aliases`).
  Required whenever the satellite must drive the parent's *live* instances, e.g. a
  tour calling `patchWithCleanup(browser, …)` against an already-running app.

Example:

```python
# web/__manifest__.py — the only manifest using all four keys:
'esm': {
    'bundles': [...14 bundles...],
    'dynamic_children': {'web.assets_web': ['web.assets_clickbot',
                                            'web.assets_emoji']},
    'import_map_includes': {'web.assets_unit_tests_setup':
                            ['web.assets_unit_tests']},
    'secondary_import_map_includes': {'web.assets_web': ['web.assets_tests'],
                                      'web.assets_frontend': ['web.assets_tests'],
                                      'web.assets_frontend_lazy': ['web.assets_tests'],
                                      'web.assets_frontend_minimal': ['web.assets_tests',
                                                                      'web.assets_frontend_lazy']},
}
# web_tour/__manifest__.py — the CHILD declares its lazy bundles under the parent:
'esm': {
    'bundles': ['web_tour.automatic', 'web_tour.interactive', 'web_tour.recorder'],
    'dynamic_children': {'web.assets_web': ['web_tour.automatic',
                                            'web_tour.interactive',
                                            'web_tour.recorder']},
}
# point_of_sale/__manifest__.py — bundles-only (no children/includes).
```

### A dynamic child is compiled against the page that loads it

`/web/bundle/<child>?page=<page bundle>` in production answers `{"is_esm": true,
"esm_url": "/web/assets/esm/<group hash>/<child>.esm.js", ...}` and the client
`import()`s that one URL (`assets.loadESMModule`, `core/assets.js`). The client
reads `page` off the `data-bundle` attribute of the import map the server
stamped on the document (`pageBundleOf`), so a cross-document load names the
target document's page, and the descriptor cache is keyed by bundle and page.

The server compiles every child declared under that page **together**
(`_get_runtime_group_urls_cached`, `ir_qweb_assets.py`;
`_compile_runtime_group`, `ir_qweb_assets_esbuild.py`; `EsbuildCompiler.compile_group`):

1. the page's member specifiers are the "parent-owned" set
   (`_get_runtime_parent_specs`). Every child member the page already owns is
   **dropped from the child's entry** — a child manifest may list parent files
   to feed the debug import map, and they must never be evaluated twice — and
   so is every member whose URL is a declared `esm.external_libs` file, which
   the browser resolves through the import map and dedups by URL;
2. each addon a child touches is mirrored into a temp tree (`esbuild_stubs.mirror_aliases`,
   one symlink per real file) where every parent-owned module any child reaches
   — by bare specifier or by relative import — is replaced by a **strict stub**
   (`_strict_stub_source`: `odoo.loader.modules.get(spec)` or throw; a child
   evaluates after its parent registered, so it reads once instead of
   listening); `@addon` is aliased to the mirror and esbuild runs with
   `--preserve-symlinks`, so relative imports stay inside the mirror. Under
   that flag a file's real path and its mirror path are two modules, so every
   other alias naming a file in a mirrored addon's static tree is rewritten to
   the mirror's copy (`esbuild_stubs.alias_into_mirror`): until 2026-09-27 the
   `@odoo/o-spreadsheet` header alias kept the real path while
   `@spreadsheet/…` reached the mirror, and `spreadsheet.o_spreadsheet`
   evaluated `o_spreadsheet.js` twice;
3. esbuild runs once with one entry per child, `--splitting`, `--entry-names=[name].esm`
   and `--chunk-names=chunk-[hash].esm`: a module two siblings share (the three
   `web_tour` bundles share `tour_step`) becomes a chunk both entries import by
   relative URL, so the browser evaluates it once, as URL identity did on the
   per-file path;
4. each entry gets its templates appended exactly as a page bundle does, and
   the whole output set is persisted under one content-addressed directory
   `/web/assets/esm/<group hash>/` (`_save_esm_group`: immutable, one year, the
   404 self-heal applies) with the esbuild metafile as a sidecar named group.meta.json. The directory
   is one build of the group (kind `group`, §Build lifecycle), so every chunk
   in it is kept and collected with the group rather than by its own name.

A page stamps the bundle it rendered first, which may be one member of the
family a child declares (the website frontend stamps `web.assets_frontend_lazy`,
built by including `web.assets_frontend`); the declared parent that contributes
to that page is the one used (`_get_runtime_group_parents`). In test mode the
page also renders its secondary satellites (`web.assets_tests`), whose members
the child stubs as well, so a test-mode group is a separate cache entry
(`runtime:<parents>:tests`). With no `page` at all (a caller outside the web
client) the group is the children sharing the child's exact set of installed
declared parents, compiled against the modules **all** of them own.
Anything a child imports that neither it nor the page owns is bundled from
disk and logged as `event=runtime_child_inlines` — on a page that also owns it,
that is a singleton split, and the log line is the only warning. The circuit
breaker, advisory lock and admin override apply per group (`runtime:<parents>`);
a declined compile falls back to the per-file payload below; a read-only test
cursor propagates `ReadOnlySqlTransaction` so the route retries read-write, as a
page bundle does. The debug payload (`?debug=assets`) is per-file, unchanged.
Pregeneration warms one group per installed parent.

`TestDynamicBundleIntegrity.test_a_runtime_bundle_resolves_every_parent_module_through_a_stub`
reads a group directory back and checks every parent-owned module a child
reaches is a loader read and none is re-registered;
`TestRuntimeBundlesInTheBrowser` loads every compiled child of `web.assets_web`
in Chrome and fails on the first `rebind` event. Measured on the spreadsheet
bundle before/after: 244 requests and 4.8 MB (raw, uncompressed, 7-day cached
sources) with 7 rebinds per open, against 7 requests, one immutable file
(497 KB gzip) and none.

### A page bundle is one file, and a dynamic child is declared on every page that reaches it

A dynamic `import()` in page code resolves one of two ways: to a stub, when
the page declares a child that owns the module (`_get_esbuild_child_externals`
aliases every child member to a loader stub), or to the module inlined from
disk. `web.assets_emoji` declared under `web.assets_web` alone gave every
backend page the stub and every frontend page the 461 KB table; it is declared
under `web.assets_frontend` too, and
`TestDynamicBundleIntegrity.test_a_page_never_inlines_what_a_dynamic_child_owns`
reads each page's metafile and fails on the next such case.

Compiling page bundles with `--splitting` instead was measured and rejected
on 2026-09-06: with the stubs in place the backend page has nothing left to
split (its dynamic imports are a few hundred bytes each), it would fetch
fifteen shared chunks (213 KB) at boot beside the entry, and every module in
a shared chunk evaluates before every module left in the entry — the HOOT
page bound `window.fetch` in `browser.js` before hoot installed its mocks and
twelve tests failed. Member order is load-bearing; one file keeps it.

### The web client's page bundle is a classic script

Chrome keeps the compiled form of a script it has run (V8's code cache) and
skips the parse on the next load. It never does for a module script, because
it streams every module script and a streamed module does not look its cache
up; and it never does for a script a service worker answers. `web.assets_web`
was both, so its 8 MB were parsed and compiled on every boot.

A page a manifest names under `esm.classic_pages` is delivered as one classic
script. The sources stay ES modules and so do the lazy children; what changes
is the format of that one file:

| Step | What | Where |
|---|---|---|
| Second pass | The ESM output of the page compile goes through esbuild again as `--format=iife`. Each library the page imports statically is aliased to a stub, `module.exports = odoo.loader.external("<specifier>")`; a dynamic `import()` of a bare specifier or of a served library is left to the import map | `classic_script` (`odoo/tools/assets/esbuild.py`), `_as_classic_page` |
| Libraries | An inline module script in front of the bundle (`data-externals`) imports those libraries and hands their namespaces to the loader, with `import.meta.resolve`, which a classic script has no access to | `externals_module_node`, `provideExternals` |
| Script tag | `<script defer fetchpriority="high" src>` in place of `<script type="module" src>`. Deferred scripts and module scripts run from one list, in document order: the libraries are provided before the bundle runs, and the satellites run after it. A deferred script is fetched at low priority, a module script at high (*What a first boot waits for*, below) | `_prepare_esm_script_node` |
| Templates | The compiled templates appended to the bundle sit in a block of their own: the constants they bind would be globals of a classic script | `combine_bundle_with_templates` |
| Source key | The format is hashed into the key (`script_format`), so a module build is never reused as a classic one. An empty format leaves the key as it was | `esm_index.source_key` |

The URL keeps its shape, `/web/assets/esm/<hash>/<bundle>.esm.js`: the index,
the collector and the 404 self-heal key on it. A classic script is told by
its first bytes, the `"use strict";` banner (`is_classic_script`); esbuild does
not carry a module's strictness into an IIFE, so the banner is also what keeps
the code strict.

**The module form is the fallback, never an error.** The page is served as
before, `type="module"` and no libraries node, when the second pass cannot be
done: source maps are on (the first pass's map does not describe the second's
output), the first pass left no metafile to say which libraries the page has
to provide, the bundle holds a top-level `await` or an import nothing
provides, a static import names a path esbuild cannot alias, or esbuild is
missing or fails. An import nothing provides is read from the second pass's
own metafile: esbuild exits 0 on a static import it was told to leave external
and emits a `require()` that throws at boot. `odoo.assets.esbuild` logs `event=classic_declined` (INFO) or
`event=classic_failed` (WARNING); a success logs `event=classic`. Inlined in
the document (no writable cursor), the same code is a module script again,
which it is valid as.

A build whose second pass failed is published as it is, under the key of the
classic format, and reused: the page stays a module until its sources change or
the assets are regenerated. Retrying on every render would compile the page
again on every render; the WARNING is the signal.

Readings FROZEN at `ddcb00f3ace6` (module script) and `d11c1514bf7b` (classic
script), a database of 340 modules, Chrome 154 headless, one browser process
per load on a persistent profile, the service worker active, **no debugger
attached while the page loads**; milliseconds read from the page itself for
`/odoo/action-base.action_partner_form`, loads 4 to 7 of three rounds, the two
variants interleaved:

| | Largest contentful paint | `DOMContentLoaded` | The bundle's code cache |
|---|---|---|---|
| Module script, through the service worker | 632–696 | 331–362 | never produced |
| Classic script, left to the browser | 476–540 | 220–251 | used (8.8 MB) |
| Either, caches emptied before the load | 980–1036 | 382–410 | — |

A new build pays for it twice: the cache is written the second time a script
runs, so the third load is the first fast one. A load with nothing cached
costs what it did.

**A debugger attached during the load measures something else.** The first
readings of this change were taken with tracing on, and read 920–976 ms against
646–717 ms: the same direction, nearly twice the gain. Tracing the compiler
slows the parse it measures (`V8.ParseProgram` 117 → 13 ms and `V8.PreParse`
122 → 9 ms under it). And an attached network domain, which Playwright always
enables, records an initiator stack for every request; V8 then collects the
source positions of every function on those stacks, and for a bundle that is
one function that is a second parse of all of it: 216 ms of
`V8.CollectSourcePositions` in a traced cold load of the classic script, which
made it look 130 ms slower than the module, and none without the debugger. The
instrument is m_bare.py, beside the research note on the boot's code cache in
the knowledge vault (2026-10-02): Chrome started bare on the URL, the DevTools connection made once
the page has settled, to read resource timing and the largest contentful paint
the page recorded itself.

| Reading | Held by |
|---|---|
| the second pass: static imports become reads of what the page provides, default and named imports, strictness, a dynamic import left alone, the declines | **not held** |
| the nodes, the templates block, the registry's refusals, the key | **not held** |
| the real page: one deferred script behind exactly the libraries it reads, and a module again under source maps or a failed second pass | `TestClassicPageBundle` (`web/tests/test_esm_pipeline.py`) |
| what the loader hands over, and that a library is registered as itself | `tests/modules/module_loader.test.js`; through esbuild and the loader file, under node, `test_what_the_bundle_registers_for_a_library_is_the_library` |

**The page registers the library, not the bundler's copy of it.** esbuild's
interop hands the bundle a copy of each library's namespace, and the bundle's
entry registers that copy under `@odoo/owl`. Every lazy child registers the
library itself, so the first one loaded would report a singleton split
(`rebind`, and a `module_rebind` beacon). `registerNativeModules` therefore
stores the provided namespace when what it is given under a provided specifier
has, export for export, the provided values (`_providedNamespace`); another
instance of the library still rebinds. `TestRuntimeBundlesInTheBrowser` cannot
see this: the test page's satellites register the library after the bundle,
before the test listens.

Not pursued: the lazy children are still modules, and compiled on every load
that fetches them (`web.assets_emoji` writes a 772 kB cache nothing reads).
The frontend pages are not declared: nobody measured them. Firefox and Safari
have their own bytecode caches and rules, not measured either.

### `--keep-names` stays

Dropping `--keep-names` is worth 3.7 % raw and 4 % gzipped on `web.assets_web`
(measured 2026-09-06: 4,195,650 → 4,039,172 bytes, 1,124,001 → 1,079,983
gzipped) and is not taken: `mail/static/src/model/record.js` registers a model
under `this._name || this.name`, so a minified class name would rename every
mail model that does not declare `_name`. The flag goes when the models do.

### A bundle made of libraries only is served classic

Three declared bundles (`html_editor.assets_history_diff`,
`html_editor.assets_image_cropper`, `spreadsheet.assets_print`) carry no native module: their members are classic
library scripts. The route serves them in the classic list envelope — the
scripts load through `loadJS` — instead of an ESM envelope with an empty
specifier list and a 26-entry import map the client would inject for nothing.
`TestBundleDescriptorFormat.test_a_library_only_bundle_is_served_classic` pins it.

### Not every ESM bundle can be served per file

A runtime bundle with no declared parent, and every runtime bundle under
`?debug=assets`, is served **per file**, and a bundle built for esbuild is not
automatically servable that way. esbuild walks the import graph from disk, so a
member's relative `./sibling.js` resolves whether or not the sibling is in the
bundle's file list; served per-file there is no such walk, and the specifier
would fetch a second copy of a module some other bundle on the page already
owns. `_check_lazy_bundle_relative_imports` refuses that, and
`TestDynamicBundleIntegrity` sweeps every bundle in `runtime_bundle_names` so
the refusal lands in CI rather than as an HTTP 500.

Five declared bundles currently fail that check, and **all five are correct as
they are** — do not "fix" them by adding the escaping files to the bundle:

| Bundle | Why the escape is right |
|---|---|
| `web.assets_frontend_lazy` | It is `web.assets_frontend` **minus** the five files `web.assets_frontend_minimal` owns (`session`, `cookie`, `dom/ui`, `minimal_dom`, `lazyloader`). Removing them from the member list is what stops this bundle re-registering specifiers the minimal bundle already registered. Adding them back would create the singleton split the removal exists to prevent |
| `web.assets_inside_builder_iframe` | Rendered into the builder iframe — a separate document with its own module graph |
| `api_doc.assets` | Its own page, which does not render `web.assets_frontend` |
| `im_livechat.embed_assets_unit_tests_setup` | A test-setup bundle that removes `im_livechat/static/**` and re-adds a chosen few |
| `im_livechat.assets_embed_core` | Include-only. Its first entry removes `web/static/src/core/browser/title_service.js`, which only exists in the parents that include it (`web.assets_frontend`, `im_livechat.assets_embed_external`) — an exact-path `remove` is strict, so standalone it raises. Note the side effect: installing `im_livechat` drops `title_service.js` from `web.assets_frontend`. Verified harmless — nothing on the frontend calls `useService("title")`, and `mail.assets_public`, whose `discuss_patch.js` does, keeps both |

The rule is not "close every bundle under its relative imports". It is: a bundle
is servable per-file only if it is closed, and `esm.runtime_bundles` is the
declaration that says it must be.

Invariants are enforced by `check_esm_config` (`esm_registry.py`) when the
registry is built —
loud by design, so a bad manifest fails the first render/bundle that touches
the registry.  For ALL THREE mappings (`dynamic_children`,
`import_map_includes`, AND `secondary_import_map_includes`):
- Every parent is a registered ESM bundle (in `bundles`)
- Every child is a registered ESM bundle (in `bundles`)
- No duplicate name within a parent's merged children list
Plus: every `runtime_bundles` and `standalone_bundles` entry is a registered
bundle, and, cross-mapping: no bundle is both a dynamic child AND an
import-map-include of the same parent.  Unknown keys under `esm` are rejected
(`_ESM_MANIFEST_KEYS`); a non-Mapping `esm`, a bare-string `bundles`, or a
non-dict mapping value raise `TypeError` earlier in the build.

External libs are **declared per manifest** under `esm.external_libs` (bare
specifier → root-relative URL) and aggregated by `esm_registry.external_libs()`;
a specifier is owned by exactly one module, and two modules declaring it
differently is an error. That table is the only source of specifier
resolution: esbuild leaves every `@odoo/*` specifier and every declared bare
specifier external (`external_bare_specifiers()`) and the page's import map
resolves them, a standalone bundle aliases each of them to its declared file
(`_standalone_alias_flags`), and a bundle whose member is a declared library
file (`web.assets_unit_tests_setup` carries hoot) also registers the library
under its declared specifier — `external_lib_aliases()` reads each URL as a
specifier, so `@odoo/hoot` is `@web/../lib/hoot/hoot` without a second table
saying so. The former `_LIB_CANDIDATES` alias table (bundled copies of
`@popperjs/core`, `@odoo/hoot-dom`, `@odoo/o-spreadsheet`) is gone: nothing
bundled imported the first, the second was external anyway, and the third is
the `@odoo-module alias=` header of `o_spreadsheet.js`, which `_esbuild_flags`
already turns into an alias.
Cross-file invariants are checked once per process by
`AssetsBundle._check_external_libs(external_libs())`, reached through
`_check_external_libs_once()` in `AssetsBundle.__init__`:
- Every `esm.external_libs` specifier resolves for esbuild —
  `external_bare_specifiers()` membership or `--external:@odoo/*` coverage
- Every `esm.external_libs` URL exists on disk (URLs under addons absent from
  `addons_path` are skipped)

In production the import map does not name the vendored file: every
`esm.external_libs` URL is rewritten by `esm_libs.served_external_libs()` to
`/web/assets/lib/<unique>/<declared path>`, where `<unique>` hashes the
library's relative-import closure (`lib_closure`: the declared file plus every
`./` and `../` import it reaches inside the addon's `static/`), and the render
that builds the map persists a minified copy (`minify_js` with `--keep-names`)
of each file of that closure at those URLs (`IrQweb._create_served_libs`); the
whole set is one build of kind `lib`.
The route serves them immutable for a year, and a sibling imported by relative
URL resolves under the same `<unique>` prefix to the same instance. A page
under `debug=assets` keeps the declared URLs, readable and uncached; the two
tables never mix on one page, since a library reached by two URLs would be two
instances. A `<link rel="modulepreload">` precedes the page bundle for
each library the bundle imports statically (owl, dompurify), read off
the esbuild metafile's external `import-statement` entries, so the browser
fetches them beside the bundle instead of after parsing it; a library behind
`import()` gets none. Measured 2026-09-06, gzip: owl 50 → 27 KB, luxon 60 → 22 KB,
fullcalendar 162 → 88 KB, three.js 406 → 186 KB.

A heavy library is reached through **one facade**: a module under
`static/src/core/lib/` or `static/src/lib/` that owns the `import("<spec>")`
(`makeLazyLib` in `core/lib/lazy_lib.js`; `chartjs.js`, `fullcalendar.js`,
`geoengine/static/src/lib/geo_libs.js`, `web_threed/static/src/lib/three.js`).
The view code stays eager and small; the library is fetched on first use
through the import map, once. `TestLibraryFacades` (`test_esm_pipeline.py`)
reads every facade of every installed addon, refuses a facade importing its
library statically, and fails when a member of `web.assets_web` or
`web.assets_frontend` outside those directories imports a facaded library
statically. Bundles a single page or a lazy child owns may still take a
library eagerly (survey's live session page, the spreadsheet child).

Bridge export surfaces and import discovery are primarily computed by a
persistent `es-module-lexer` node worker (`odoo/tools/assets/esm_lexer.py` +
`odoo/tools/assets/js/esm_lexer_worker.mjs`, installed by the same
`npm install` that provides esbuild); a regex extractor in `esm_graph.py` is the
automatic fallback when the worker is unavailable or a source doesn't lex.

Worker robustness contract (`esm_lexer.py`):
- **POSIX-only.** The worker uses `select` on pipes; on non-POSIX the regex
  path is always used.
- **Hard per-request deadline** (`_REQUEST_TIMEOUT_S`, 10s). The pipes are
  binary + non-blocking and BOTH the request write and the response read are
  gated by a wall-clock deadline (`_write_all` / `_read_line`), so a worker
  that stopped reading (full ~64 KB pipe) or emitted a partial line can never
  block a caller past the budget — a plain `stdin.write` / `readline` could.
- **A worker that cannot start is unavailable, not failing.** The worker
  writes `{"ready": true}` once es-module-lexer has loaded, and `_spawn` reads
  that line before any request. No `node`, or a worker that dies before its
  greeting (`npm install` never run, so the package is missing), is a spawn
  failure: no request is sent, the worker pauses for `_UNAVAILABLE_COOLDOWN_S`
  (600s), and `worker_unavailable` is logged at INFO once per process (DEBUG
  after, until `close_lexer_worker`).
- **Respawn-once, then pause.** A worker that started and then fails a request
  (timeout, EOF, desynchronised reply) is respawned and the request retried
  once; `_MAX_CONSECUTIVE_FAILURES` (2) consecutive failures pause it for
  `_DISABLE_COOLDOWN_S` (60s). That is not free: one caller per pause spends up
  to two `_REQUEST_TIMEOUT_S` deadlines (20s) on a worker that never answers
  before the pause starts, and a WARNING marks each pause. Callers queued on
  the worker's lock meanwhile re-read the pause once they hold it and return
  `None` without spawning, so the cost is one caller's, not one per thread.
  A single slow reply under load does not blind the process for its lifetime.
  An outage is never memoised: only the worker's answers are cached (a
  refusal, `ok: false`, included), keyed on a blake2b digest of the source.
- **Discovery parity.** The regex fallback (`_TRANSITIVE_IMPORT_RE`, and
  `_DYNAMIC_IMPORT_RE` where a literal `import()` counts) covers named /
  default / namespace / mixed (`import D, { y } from …`) / bindingless
  side-effect imports and `export … from`, matching the worker's specifier
  discovery; both are read through `esm_graph._get_import_specifiers`, the one
  extractor bridge discovery, the reach walk and the source key share. It reads
  the source through `odoo/tools/assets/js_scan.py`, which blanks comments,
  template literals, regex literals and every string that is not a specifier
  (an `import()` argument is one), so a
  backtick in a comment or an import spelled inside a string moves nothing;
  array-destructured exports and `export { x as default }` are read as the
  worker reads them.

## OWL templates compiled ahead of time

A bundle's template code (`XmlTemplatePipeline.generate_xml_bundle`, the
`registerTemplate` / `registerTemplateExtension` calls) is announced outside
debug assets and `--dev=xml`: it becomes the callback of
`registerTemplateBundle(<bundle>, <checksum>, <params>, () => { … })`. The checksum covers that code and the compiler's own inputs
(`odoo/tools/assets/owl_precompile.py`, `compiler_fingerprint`: OWL, the
template registry, the inheritance engine, `env.js`, the node side and its
packages), so a new OWL or a changed engine is a new URL.

The `precompiled_templates` service (`core/precompiled_templates.js`) asks
`/web/assets/owl/<checksum>/<lang>/<translations hash>/<bundle>.js` for each
announced bundle once the translations are known (the web client's document
preloads the page bundle's, see *What a first boot waits for*): OWL inlines each
translation into the code it generates, so the artifact is per language and
per payload of translations. The first request compiles it
(`ir.qweb._get_or_create_precompiled_template_attachment`): the server rebuilds the bundle, refuses
a checksum or a translations hash it would not produce itself (404), and runs
`odoo/tools/assets/js/owl_precompile.mjs` under node. That script executes the
bundle's own registration calls against the real `TemplateRegistry`,
`template_inheritance.js` and OWL `TemplateSet` in jsdom, with the options
`makeAppConfig` gives an app outside dev mode. Two jsdom departures are
corrected there, not in the shared code: its XPath engine (replaced by the
`xpath` package — jsdom matches `[@a='']` on an element without `a`) and its
`innerHTML`, which refuses an attribute named `xml:space` Chrome serializes as
written. `TestPrecompiledTemplatesInTheBrowser` compares every shipped function
with what the page's own OWL compiles from the page's own registry.

Each template ships as `[signature, inheritance chain, function]`. The
signature is a digest of the registrations `_getTemplate` reads, in reading
order (`TemplateRegistry.resolutionSignature`); `getCompiledTemplate` serves the
function only while the page's registry yields the same digest, so an
extension from another bundle, a URL filter or a template processor sends the
template back to the browser compiler. A template the node side cannot compile
is logged (`odoo.assets.owl_precompile`) and left out.

A dynamic child (`portal.assets_chatter` under `web.assets_frontend`) is loaded
into a page whose bundles registered first, and a template both extend
(`mail.Composer`: mail's typing patch in the page, portal_rating's in the
chatter) resolves there to a chain neither artifact alone compiled.
`XmlTemplatePipeline.page_registrations` hands the node side each declared
parent's registration calls; the child is compiled once after each of them,
one `registerCompiledTemplates` call per parent, keeping only the templates
whose chain passes through a name the child registers or extends. Those
registrations enter the child's checksum. The registry keeps every artifact's
version of a name (`compiled.<variant>.candidates`) and serves the one whose
signature matches, whichever artifact landed last.

Inline `xml` templates ship too, keyed by content (`inlineTemplateKey`: length
and cyrb53 of the text), because `xml` names them `__template__<n>` in the
order modules happen to evaluate. The node side parses with `acorn` every
source `XmlTemplatePipeline.inline_template_sources` hands it — the bundle's
modules plus every module they import that the bundle does not list, since
esbuild builds those into the bundle on a page that lacks them — and OWL's own
`owl.es.js`; a tagged template with a substitution is left to the browser. A
bundle without xml files still announces itself when its code holds one. OWL's
dev mode generates other code, so `<bundle>.dev.js` is a second artifact. A
bundle built with assets params (a website's) announces them too, and the
artifact URL carries them as `?assets_params=`: the route rebuilds the bundle
with them, since a checksum only that website's assets yield would 404.

A page an editor opens keeps `'unsafe-eval'`: website notes the builder's
`website.assets_inside_builder_iframe`, which the builder loads into it.

A page whose session carries `await_precompiled_templates` (every frontend
layout, the livechat support page) waits for every artifact, dev included,
without the bound, `loadBundle` awaits a lazy bundle's, and the IndexedDB
compile cache stays off: such a page may run without `'unsafe-eval'`. There
the registry holds a lazy bundle's registrations until its artifact has
arrived or failed: `portal.assets_chatter` extends `mail.Message`, and the
livechat already running on a portal page resolved it in the meantime to a
chain no artifact it held was compiled from, so compiled it in the browser. The
policy is decided where a page renders `t-call-assets`
(`ir.qweb._note_page_script_bundle`): a page drops `'unsafe-eval'` while every
bundle it loads is in `_get_eval_free_script_bundles` and precompiled (not
debug assets, not `--dev=xml`, node available). What stays in the browser:
view archs compiled by the view compilers, and on the backend client dev and
test mode and a page whose artifact is not there within the service's bound.

Such a page waits, so its artifacts are not left to its first request:
`_pregenerate_assets_bundles` (before an `HttpCase` run, `odoo-bin warm_assets`)
compiles those of every eval-free page bundle and of every runtime child its
pages load (`_get_awaited_template_bundles`), per installed language and per
translations hash, dev included when test satellites are rendered, the node
jobs side by side. Left to the request, `portal.assets_chatter`'s two variants
compiled one after the other on the test cursor inside a tour step's 10 s
budget, and under load the chatter mounted after the step had failed. The
backend and the frontend translate with module lists of their own
(`_get_webclient_translation_modules`), so a bundle both load holds an
artifact per list: storing one replaces only an older build under the same
list, or one under a hash no list yields any more.

## Logger taxonomy (Python ↔ JS)

Both sides use the same category names so `grep event=bundled` works across
the whole stack when logs are merged.

| Category | Python logger | JS logger | Emitted at |
|----------|---------------|-----------|-----------|
| `bundle` | `odoo.assets.bundle` | — | AssetsBundle lifecycle (init, asset partitioning) |
| `bridge` | `odoo.assets.bridge` | — | Native-to-legacy data-URI bridge construction; `bridge_read_at_evaluation` (ERROR) for a parent module that reads a lazy child's binding while it is evaluated |
| `esbuild` | `odoo.assets.esbuild` | — | subprocess invoke / success / timeout / fail |
| `loader` | `odoo.assets.loader` | inline `[asset.loader]` | `module_loader.js` shim — idempotent install check and `registerNativeModules` entry counts |
| `attach` | `odoo.assets.attach` | — | ir.attachment writes/reuse for bundle output |
| `fallback` | `odoo.assets.fallback` | — | Prod→debug degradation, circuit open, admin override |
| `lock` | `odoo.assets.lock` | — | PG advisory-lock acquire/release |
| `esm` | `odoo.assets.esm` | `makeAssetLog("esm")` | Import-map + bundle-node generation |
| `env` | — | `makeAssetLog("env")` | Service launcher, wave resolution |
| `js` | — | `makeAssetLog("js")` | Lazy bundle fetch (core/assets.js) |
| `templates` | — | `makeAssetLog("templates")` | registerTemplate / getTemplate |
| `registry` | — | `makeAssetLog("registry")` | Sub-registry creation |

> No `boot` category exists on either side — boot events surface through
> `loader` (Python shim + JS inline) and `env` (JS service launcher).

Event format (Python `log_event`): `event=<name> k1=v1 k2=v2`, formatted as the
debug log formats its events: a string that is empty or holds whitespace is
written as its repr, a float with three decimals, a recordset as its model and ids.
Event format (JS `assetLog`): `[asset.<category>] <...parts>` via `console.debug`.

## Debug toggles

### Python side
```bash
odoo-bin --log-handler=odoo.assets:DEBUG              # full trace
odoo-bin --log-handler=odoo.assets.esbuild:INFO       # esbuild only
odoo-bin --log-handler=odoo.assets.fallback:WARNING   # alerting
```

### JS side (any of)
- URL: `?debug=assets` (or any debug mode containing "assets")
- DevTools: `localStorage.setItem("debug.assets", "1")`
- DevTools: `window.__ODOO_ASSET_TRACE__ = true`

Then enable the DevTools "Verbose" log level so `console.debug` lines
become visible.

## Tunable parameters (ir.config_parameter)

All names are `web.esbuild.<key>`.  Defaults come from the hardcoded
class constants listed in the table and apply when the parameter is
unset or unparseable.

| Key | Default | Class constant (file:line) | Effect |
|-----|---------|---------------------------|--------|
| `timeout_s` | `30` | `EsbuildCompiler._ESBUILD_TIMEOUT_S` (odoo/tools/assets/esbuild.py) | subprocess timeout (seconds) |
| `target` | `"chrome154,firefox157,safari27"` | `EsbuildCompiler._ESBUILD_TARGET` (esbuild.py) | esbuild `--target=`. The browser floor (`coding_guidelines.rst` §5.3): the stable Chrome, Firefox and Safari of 2026-09-30; Safari holds only public and portal bundles, but modules are shared, so the one target covers all three and esbuild lowers what any of them lacks (Safari 27 has no `using`). |
| `source_maps` | `""` | `EsbuildCompiler._ESBUILD_SOURCE_MAPS` (esbuild.py) | esbuild `--sourcemap=<mode>`. `""` (off), `"linked"` (sidecar `.js.map` + `sourceMappingURL` comment — DevTools fetches only when opened), `"external"` (sidecar without comment), `"inline"` (base64 data URL appended — ~2x bundle size). Unknown modes silently fall back to `""`. |
| `cooldown_s` | `60.0` | `IrQweb._ESBUILD_COOLDOWN_S` (ir_qweb_assets.py) | Circuit-breaker cooldown after 1st failure |
| `extended_cooldown_s` | `600.0` | `IrQweb._ESBUILD_EXTENDED_COOLDOWN_S` (ir_qweb_assets.py) | Cooldown after 2nd consecutive failure |
| `force_fallback_bundles` | `""` | — | Comma-separated bundle names to force into debug path |

Compilation waits for the transaction-scoped advisory lock. Contention must not
switch an individual bundle to the debug layout: that can instantiate dependencies
twice alongside already bundled code. The former `lock_retries` and
`lock_retry_sleep_s` parameters are no longer read. Database lock/statement timeouts
propagate as errors; they do not select a different module layout. The lock covers
compilation, not subsequent attachment publication, so a waiting request can still
compile again if the preceding result has not been published yet.

Dedicated attachment-writing transactions serialize the URL existence check and
insertion under a separate publication lock. They use READ COMMITTED so a waiter
sees the preceding writer's commit. The request transaction keeps its original
isolation level. This prevents concurrent cold requests from persisting duplicate
library and compiled-asset URLs through that path.

A secondary bundle that explicitly lists a parent-owned module uses the parent's
module just like a transitive dependency. It does not import and register that
module again as an entry. External libraries retain their separate serving path.
Parent stubs also replace relative imports through a source mirror with symlink
preservation. Each addon retains separate static sibling directories (`tests`,
`lib`, etc.). The source key a build carries includes a compiler-semantics version;
increment it when changed compilation semantics could otherwise reuse an old artifact.
It also hashes what esbuild reads without being handed it -- every module the
entries reach through an alias, statically or by a literal `import()`, that no
stub or external replaces (`_inlined_module_sources`) -- and the esbuild
version and external specifiers, for a bundle and a runtime group alike: an
edited unlisted helper, another esbuild or another external library is another
key, not a reuse of the old build.

Operators set these via the UI (Settings → Technical → System Parameters)
or programmatically:

```python
env["ir.config_parameter"].sudo().set_param("web.esbuild.timeout_s", "60")
```

## Failure modes

| Symptom | Cause | Signal |
|---------|-------|--------|
| `Failed to resolve module specifier` in browser | import map missing a spec | `odoo.assets.esm DEBUG event=no_native_modules` or validator error at startup |
| esbuild subprocess non-zero exit | Syntax error in an ESM source | `odoo.assets.esbuild WARNING event=failed bundle=<name> exit=<code>` + stderr on next line |
| A page declared under `esm.classic_pages` is served as a module script | The second pass was declined or failed, and the module form is the fallback | `odoo.assets.esbuild INFO event=classic_declined reason=…` or `WARNING event=classic_failed`; `odoo.debug` `classic_page_declined reason=source_map` |
| Requests serve un-minified bundles | Circuit open after failure | `odoo.assets.fallback WARNING event=circuit_open` (at trip) then `DEBUG event=circuit_blocked` (per request) |
| Cold request waits before compilation | Another worker holds the bundle lock | `odoo.assets.lock DEBUG event=waiting`, then `event=acquired wait_s=…` |
| A dynamic child is served per file in production and stays so | The runtime group compiled but persisting it failed after both the read-write escalation and the request cursor (a database-level fault); `_get_runtime_group_urls_uncached` caches the empty result on purpose, so the group is not re-compiled on every request while the database faults | `odoo.assets.attach WARNING event=runtime_group_save_failed` once, then `odoo.assets.fallback INFO event=runtime_child_per_file` per request; any `assets` cache clear (attachment unlink, *Clear cache*, restart) retries the compile |
| `Failed to resolve module specifier "@html_editor/components/switch/switch"` on `/?debug=tests`, only on the first read-only render of a changed `web.assets_tests` | The satellite was declined (no build its snapshot can read) and served per file beside the compiled page. A per-file module that imports a page-carried module **relatively** (`video_plugin.js` → `./media_dialog/video_selector.js`) resolves to the file's url, which the specifier key of its bridge never matched: the page module was evaluated a second time from source, and its own imports, which nothing had reason to map, failed. Since 2026-10-04 the per-file branch also keys every page-provided bridge by the module's url (`_get_bridge_url_aliases`), and a later map drops a url key whose url an earlier map already loads as a module (`import_map_names`), so a per-file provider keeps its own copy | `TestPerFileSecondaryOnAPage.test_a_relative_import_of_a_page_carried_module_reaches_its_bridge` walks the per-file map as the browser does |
| A read-only test cursor keeps declining a bundle after the cause is gone | `_get_esm_variant_nodes_cached` remembers a readonly decline per (bundle, params, satellites, page scope) in the `assets` LRU so the same test run does not retry a compile it cannot persist | `odoo.debug` `readonly_decline_remembered`; `clear_cache("assets")` drops the memo with everything else, which is the intended retry |
| `[registry] Duplicate add for key "…" … (first registration wins)` console.warn in debug | Module loaded twice (separate instances) — `registry.add` is first-wins and warns rather than throwing | Missing bridge shim (happy path is an attachment URL; `data:` URI only as the read-only-cursor fallback); check `_prepare_native_to_legacy_bridge` |
| Test `patchWithCleanup(Klass.prototype, …)` has no effect; production code keeps using unpatched method | Parent + satellite each load their own copy of the same `@web/*` module → `Klass` in test bundle is a different class than the one the production controller instantiates | Add fingerprint logger to module body — two distinct `MODULE LOADED` events means two evaluations. Root cause is usually a sibling manifest (e.g. `spreadsheet/__manifest__.py` pulls `web/static/src/views/graph/graph_model.js` into `spreadsheet.o_spreadsheet`, which is then `('include',)`'d by the satellite test bundle). Fix wires the satellite import through the parent's self-bridge via the `prod_import_map[alias] = shim` override in `_get_esm_nodes_prod` (`ir_qweb_assets.py`). |

### A split page evaluates each module once (`bundle_double_eval_<addon>` floors)

`web.assets_frontend_lazy` is `web.assets_frontend` minus the modules
`web.assets_frontend_minimal` owns, and every frontend page renders both. Until
2026-09-26 the lazy half imported those modules by relative or bare specifier,
so esbuild inlined them again and each website page evaluated eight modules
twice (`@web/session`, `@web/core/browser/cookie`, `@web/core/utils/dom/ui`,
`@web/public/lazyloader`, `@web/public/minimal_dom`,
`@website/js/content/generate_video_iframe`, `@website/utils/misc`,
`@website/utils/video_urls`), each copy with its own state: `lazyloader`'s
readiness promise and delay list existed twice. Three pieces close it:

- `web.assets_frontend_minimal` declares `web.assets_frontend_lazy` a secondary
  under `esm.secondary_import_map_includes`, so the lazy half's imports of the
  minimal half's modules compile to strict loader stubs
  (`_get_secondary_parent_stubs`) and the minimal half registers what the lazy
  half imports (`_get_export_consumers`).
- `web.frontend_layout` (and `room`'s booking page, `web.webclient_scoped_app`)
  render the minimal half **first**: module scripts run in document order, and
  a stub throws when its provider has not registered.
- One import map per document: `IrQweb._render` folds every map the document
  emitted into the first one's place (`_merge_page_import_maps`), stamped with
  the first rendered bundle declaring dynamic children
  (`_get_page_import_map_stamp`), so `pageBundleOf` still names
  `web.assets_frontend_lazy` and the `web_tour.*` entries resolve although the
  minimal half's map comes first. The merge runs only when a document emitted
  more than one map, and leaves the page alone when the maps it finds are not
  the ones it emitted.

The lazy half keeps a page bundle's export surface (`page_secondaries`), not a
satellite's register-everything one. Measured 2026-09-26 with website_sale,
survey, room and portal installed: `web.assets_frontend_lazy` 1,344,319 →
1,341,382 bytes raw (415,781 → 413,911 gzipped), `web.assets_frontend_minimal`
29,616 → 29,851 (11,661 → 11,737).

`test_bundle_double_evaluation` ratchets the modules a bundle removes by name
and an importer re-inlines, subtracting what the secondary-parent mechanism
stubs; its `bundle_double_eval_<addon>` floors are keyed by the addon owning
the module, exact, and zero. `TestSplitFrontendPage` (`web/tests`) reads each
page's compiled scripts back through their metafiles and fails when a module of
the minimal half is evaluated by any other script, when the page carries more
than one import map, or when the page does not boot in Chrome.

- **Not every re-appearance is a double evaluation.** A module that one addon
  removes and another adds back is a bundle *member*, not an import, and is
  ignored; import-map bundles such as `web.assets_unit_tests` are never bundled
  and are skipped.

## Cache invalidation on source change — no manual flush needed

**Dev mode rebuilds a bundle on a source-file mtime change; you do NOT need
to `DELETE FROM ir_attachment WHERE name LIKE '%assets_unit%'` before a run.**

The bundle's served URL carries a 7-hex *version* segment
(`/web/assets/<version>/web.assets_unit_tests.min.js`), which is
`AssetsBundle.get_checksum()[0:7]` — a SHA256 over each member's
`unique_descriptor`. That descriptor is `"{url},{last_modified}"`
(`assetsbundle/assets.py`), and `last_modified` is the file's `st_mtime`,
freshly `stat()`'d by `ir_asset._glob_static_file`. So editing any JS source
changes its mtime → changes the checksum → changes the version → the render
path looks up a version with no attachment → **rebuilds** (esbuild for the
ESM bundle, concatenation for the legacy `.min.js`) and writes the new row.
Stale content is impossible once the version differs; the old build is
superseded, served through its grace, then swept (§Build lifecycle).

The one caveat is the `cache="assets"` **ormcache** on
`ir_qweb._get_asset_links_cached` / `ir_asset._get_asset_paths`: its key
does NOT include mtime (it's `bundle`/`assets_params`/`rtl`/…), and it's only
bypassed when `dev_mode` contains `"xml"` (`@tools.conditional`,
`ir_qweb_assets.py`). But that ormcache is **in-memory, per-process**, so:

- **`--stop-after-init` test loop** (a fresh process per run, the workflow
  used here): the ormcache starts cold every run, recomputes from fresh
  mtimes, and always reflects edits. No flush, ever.
- **A long-lived server** (`config/p314o19marin.conf`, no `--dev`): the
  ormcache persists in-process, so an edit made while the server is up is
  invisible until the `"assets"` cache clears (server restart,
  Settings → Technical → *Clear cache*, or any asset-attachment unlink). If
  you want live reload against a running server, start it with
  `--dev=xml,reload` — `xml` disables the conditional ormcache and `reload`
  restarts on `.py` change; JS is then picked up on the next request. This is
  a server-lifecycle choice, not a bug, and still needs no manual SQL flush.

## Browser baseline

A server-rendered page carries one `<script type="importmap">`, however many ESM
bundles it renders (`_merge_page_import_maps`). What the client appends at runtime —
every per-file load (`?debug=assets` children, the compile-declined or circuit-open
fallback, cross-document loads) — is a second `<script type="importmap">`. Only browsers that merge import maps honour it:
**Chrome/Edge 133+ and Safari 18.4+**. Firefox stable drops it (support sits behind
`dom.multiple_import_maps.enabled`), so the bare specifiers it carries fail to resolve —
on exactly the resilience paths. The compiled production path for dynamic children is
unaffected: the page map and the child descriptor both carry every served external lib.

That is the supported baseline. Below it there is a hard floor: every compiled
bundle leaves the external libs as bare specifiers that only an import map
resolves, so a browser without import maps (Chrome/Edge < 89, Safari < 16.4)
cannot run any ESM page. `web.layout` carries a classic inline check
(`web.layout.browser_check`) that replaces such a page with a translated
"update your browser" notice instead of leaving it blank. It fails open:
`HTMLScriptElement.supports` arrived in Chrome 96, after import maps (89), so
it shows the notice only when that API says import maps are missing, or, where
the API is absent, when a bundle under `/web/assets/` fails to load before the
page's `load` event (a `SyntaxError` or an unresolved module specifier).
Chrome/Edge 89-95 therefore keep a page that works. Lowering the esbuild
target would not help: the libraries are served untranspiled and still need
the map.

Above the floor, the baseline holds. `addFreshImportMapEntries` (`core/assets.js`) checks the
first specifier of each map it appends with `import.meta.resolve` (in a classic
page bundle, with the resolver the page provided to the loader); when the browser
dropped the map it logs one `[assets] This browser ignores import maps added after the
first one` error per page, so an unsupported browser shows up in the JS error reports
instead of as an unexplained resolution failure.

## Serving & caching

ESM artifacts are served by a dedicated route
(`web/controllers/binary.py::content_esm_assets`,
`/web/assets/esm/<unique>/<filename>`) with `Cache-Control: immutable` +
one-year `max-age` — safe because every URL is content-addressed (the
`<unique>` segment is a hash of the bytes, or `bridges` with the hash in
the filename). There is deliberately no on-the-fly rebuild on this route:
a missing row is a hard 404, and regeneration happens through the render
path after `ir.attachment.unlink`'s assets-cache clear.

Persistence is decoupled from the request transaction:
`IrQweb._save_esm_attachment_rows` (bundle/templates/sourcemap) and
`BridgeShimManager._persist_bridges_via_rw_cursor` (loader bridges) create
attachment rows through a dedicated read-write registry cursor that commits
independently, so a request rollback can never orphan an ormcached bundle
URL, and read-only replica renders persist + reference by URL instead of
inlining the bundle. Inlining survives only as the degradation path when no
writable cursor exists at all (read-only test cursors, primary down). A content
revert (A → B → A) publishes the earlier build again, which makes it current.

**Current-cursor guard (deadlock avoidance).** The out-of-band cursor exists
ONLY to survive an HTTP-request rollback. When there is no request — registry
preload / asset pregeneration (`lifecycle._run_post_install_tests` →
`_pregenerate_assets_bundles`), cron, CLI — the current cursor is already the
durable one, and opening a SECOND real `registry.cursor()` on the same thread
self-deadlocks: this thread holds `ir_attachment` locks on the current cursor,
so the second cursor's INSERT waits on a lock only the now-suspended thread can
release (a one-thread/two-cursor cycle Postgres cannot break). Both savers
therefore persist on the current cursor when there is no request. **The two
guards are intentionally NOT identical:**

- `_save_esm_attachment_rows`: under a test, the rows and the build commit
  through a connection of their own (`_save_esm_attachment_rows_in_test`), so
  what one test class compiled serves the next; a writable test cursor also
  keeps a copy of the rows, not of the build, which the snapshot could not see
  conflicting with the committed one. With no request, the current cursor.
- `_persist_bridge_shims`: `if not request:` → current cursor, else the rw
  cursor **even under a test**. A bare `current_test` branch here would break
  HttpCase tours: the browser fetches loader-bridge URLs on SEPARATE
  TestCursors, and only the `registry.cursor()` path publishes rows visible to
  them; persisting on the render's own cursor left dynamic-child bridges
  unfetchable (`Failed to fetch dynamically imported module`). Do not "unify"
  these guards.

### Warming a deploy

After a deploy, the first request per bundle, variant and worker builds cold:
lexing, hashing, esbuild, and the classic bundles' SCSS. Run
`odoo-bin warm_assets -c <conf> -d <db>` once per database after the restart
and before traffic returns. It pregenerates every bundle and lazy group without
a website and then once per website, so the workers of every instance find
published builds and reuse them instead of each compiling its own.

### Build lifecycle

Every published artifact belongs to an `ir.asset.build` row: its `kind`
(bundle, templates, standalone, group, lib), its `bundle`, its `variant` -- what
selects another build of the same bundle besides its sources, computed by
`variant_key` from the assets params, the page scope and the standalone flag --
the url `directories` it owns, and the `source_key` a process that has not
compiled yet reuses it by (`_find_reusable`). `_publish` makes a build current
and supersedes the previous current build of the same kind, bundle and variant in
one transaction, on the cursor that wrote its rows; `_one_current_build_per_variant`
is a partial unique index. Two variants never supersede each other, so the
page-scoped build of a secondary and its plain build are served side by side.

A file is served while a build that is current, or superseded less than
`web.esm.gc_grace_days` ago, owns its directory: pages rendered before a rebuild
keep loading the previous build through that grace. `_sweep` deletes the builds
past it and the files no remaining build owns, at publish time for the variant
just published and in the autovacuum `_gc_asset_builds` for all, which also
retires the current builds of bundles no installed addon declares
(`_retire_uninstalled`) and deletes files no build owns past the grace
(`_sweep_orphan_rows`). Bridge shims own no build: reuse refreshes them and
`_gc_esm_bridges` collects them by age.

Only a fresh compile changes which build is current. A worker still on older
sources that reuses a superseded build extends its grace (`superseded_at`)
without making it current again, and publishing flushes no cache: superseded
urls stay served through the grace, and the sweep's deletion of their rows
flushes the assets caches when they go. **Invariant: the grace must outlive
any worker**, because a worker may keep handing out a superseded page build
from its cache until it recycles; a grace shorter than a worker's life would
sweep files that pages are still told to load.

## What a first boot waits for

A browser with nothing cached (a new device, the first boot after a deploy)
runs a chain where each step waits for the one before: the document, the page
bundle, its evaluation, the compiled templates, `/web/action/load`,
`get_views`, the first read. A warm boot blocks on none of them.

What the document starts while the bundle downloads, because the server knows
it when it writes the page:

| Request | How | Since |
|---|---|---|
| Menus | the inline script's `odoo.loadMenusPromise`, with the stored copy's hash | — |
| Translations | the inline script's `odoo.loadTranslationsPromise`, when the browser holds none for this registry and language | — |
| The compiled templates of the page bundle | `<link rel="preload" as="script">` on the artifact's URL (`ir.qweb._get_page_templates_url`: the bundle's precompile checksum, the user's language, the hash of its translations) | 2026-10-02 |

The templates artifact was requested by the `precompiled_templates` service
once the bundle had run and the translations were in: one round trip in front
of the first action, for a URL the server can write. A page in debug or under
test compiles its templates itself and is named none; neither is a bundle the
page asks for under a query string (`js_rebuild_params`, a website's), which
the client serializes itself.

**The link carries the script nonce.** The page's policy is
`script-src 'nonce-…' 'strict-dynamic'`, and a script preload without the
nonce is refused, with a console error on every boot.
`TestTemplatesPreload` holds it.

**The first wave is larger than six connections.** Over HTTP/1.1 a browser
opens six connections to a host, and the document starts nine requests at once:
two stylesheets, the two libraries, the legacy script, the page bundle, menus,
translations, the templates. Those left out wait a whole round trip, and
Chrome orders them by priority: a `defer` script is low, a module script was
high. So the classic page bundle, the one request everything else waits for,
was sent a round trip late on a first boot, until its tag said
`fetchpriority="high"`. Over HTTP/2 there is no such queue.

Readings FROZEN at `f7fc640b5463`, without and with the two changes, a database
of 340 modules, Chrome 154 started bare with an empty profile for each load, a
proxy holding every request for the latency (m_bare.py and delay_proxy.py,
beside the research note on the boot's code cache in the knowledge vault);
milliseconds, five loads:

| Held per request | `DOMContentLoaded` | Largest contentful paint |
|---|---|---|
| 0 ms | 381–419 → 379–408 | 1004–1060 → 896–968 |
| 100 ms | 689–697 → 589–608 | 1764–1840 → 1572–1668 |
| 300 ms | 1304–1326 → 982–1003 | 3540–3620 → 2784–2860 (one load at 3132) |

A warm boot reads the same as before (468–480 ms to the largest contentful
paint). Still serial on a first boot: `/web/action/load`, `get_views` and the
first read, each needing the answer of the one before.

## Service worker

`/web/static/src/service_worker.js` is NOT an `@odoo-module native` file —
it uses `@odoo-module ignore` so the bundler treats it as a classic script,
served via the `/service-worker.js` controller as a plain script (service
workers have limited ESM support — no import maps in some browsers). Do not
convert it without first verifying import-map + module-worker support across the
browser-support matrix.

**A hashed asset is not answered by the worker while the server is reachable.**
A script that reaches the page through `respondWith()` is compiled from source
on every load, whatever the worker's strategy: cache-first, stale-while-revalidate,
precached at install and a plain `respondWith(fetch(request))` all read the
same. So for `/web/assets/<hash>/…` and `/web/assets/esm/<hash>/…` the handler
returns without answering, the browser's HTTP cache serves the immutable
response, and `keepHashedAsset` stores a copy in CacheStorage on the side, once
per URL. The copy is what answers (`keptHashedAsset`) when the browser reports
it is offline, or when the last request the worker itself sent found no server
(`fetchFromServer`: a navigation, an image, a copy being kept); the next one
that is answered hands hashed assets back to the browser. Images with a
`unique=` token are still served stale-while-revalidate.

`respondWith()` has to be called while the event is dispatched, so the worker
cannot try the network first and fall back. What it knows of the server is in
memory: a worker restarted while the server is still out of reach, with the
browser reporting it is online, leaves a hashed asset to the browser until one
of its own requests fails, and the HTTP cache (the responses are immutable for
a year) is then what serves it.

| Reading | Held by |
|---|---|
| left to the browser and kept once, an error answer not kept; answered from the copy offline and after a request that found no server, left to the browser again after one that found it; an error response, never `undefined` | `tests/core/service_worker.test.js`, *a hashed asset* |

Two things changed with it. A hashed asset used to be fetched again and written
over its cached entry on every load (8 MB for the page bundle); it is now
written once. And the 30-day retention of an asset the cached shell no longer
references (`collectSupersededAssets`) counts from the first fetch, not the
last: a lazy bundle still in use is collected at the next worker activation
after 30 days and kept again on its next load.

## Loader contract (`module_loader.js`)

The shim installs `globalThis.odoo.loader` as an instance of
`OdooModuleLoader`, a real ES class: `web/static/tests/modules/module_loader.test.js`
instantiates `odoo.loader.constructor` to get fresh loaders, and Hoot reads
`odoo.loader.modules` directly. The esbuild-generated
entry exercises exactly one method (`registerNativeModules`), passing its bundle name last. Current surface:

### Public API

| Member | Kind | Purpose |
|--------|------|---------|
| `modules: Map<string, any>` | field | Shared map of specifier → module namespace.  Populated by `registerNativeModules`; consulted by bridge shims so sibling bundles see the SAME object for `@web/core/registry` etc. |
| `bus: EventTarget` | field | Loader lifecycle events.  `registered` (CustomEvent, `detail.specifiers`, `detail.bundle`) after every `registerNativeModules`, which bridge shims wait on; `rebind` (`detail.specifiers`), fired when `registerNativeModules` re-binds a known specifier to a DIFFERENT namespace object — a singleton-split signal in production, the expected signal under dev hot-reload.  Subscribe via `odoo.loader.bus.addEventListener("rebind", …)`. |
| `settledBundles: Set<string>` | field | The page bundles whose entry has finished evaluating (or whose script failed to load). |
| `externals: Map<string, object>` | field | The libraries the document handed to a classic page bundle, by specifier: the namespaces themselves. |
| `resolve?: (specifier) => string` | field | `import.meta.resolve` of the document's module script, for code of a classic bundle that has no `import.meta`. Unset on a page whose bundle is a module. |
| `provideExternals(namespaces, resolve)` | method | Called once by the inline `data-externals` module script in front of a classic page bundle. |
| `external(specifier)` | method | What a static import of a library compiles to in a classic page bundle: a copy of the library's namespace carrying `__esModule`, so that the bundler's interop reads its `default` export instead of wrapping the whole namespace as CommonJS. Throws, naming the specifier, when the document did not provide it. |
| `registerNativeModules(map, bundle?)` | method | Bulk-assign `specifier → namespace` into `modules`.  Last-write-wins on duplicate keys; same-object re-binds stay silent, different-object re-binds dispatch `rebind` + a debug-gated `[asset.loader]` log (never a throw — it runs at bundle top level).  Called by the esbuild-generated entry and the debug bridge, both last and both naming their bundle (which settles it), and by `@web/core/assets.loadESMBundle`, which names none: a lazy load is bracketed by `runInBundleTransaction` instead. |
| `pendingBundles()` | method | The `data-bridge` names of the document's page-bundle scripts whose entry has not registered yet. A bridge that waits for another bundle's module awaits across tasks, so a script's `load` event, `DOMContentLoaded` and window `load` can all fire before its bundle has registered every service. |
| `whenBundlesEvaluated(callback)` | method | Runs the callback once `pendingBundles()` is empty, at once if it already is. `whenBundlesSettled` (`@web/core/utils/bundle_transaction`) chains it with the lazy-bundle transaction; the service container reports a dependency no module registers only then. |
| `settleFailedBundle(target)` | method | Settles a page-bundle script that failed to load, so nothing waits on it forever. Called by the capture-phase resource `error` listener. |
| `handleAssetLoadError(target)` | method | One-shot, rate-limited (60 s via `sessionStorage`) `location.reload()` that self-heals a 404'd content-addressed bundle/bridge URL — e.g. a client holding an old page after a GC sweep or `clear_cache("assets")`. Invoked by the capture-phase resource-load `error` listener in the inline reporter. |

### Error reporting

Build-time errors (missing specifier, cycle, syntax) surface from
**esbuild**: the bundle step fails, the circuit breaker trips (see
`ir_qweb._esbuild_cooldowns`), and the request falls back to the
debug per-file serve path — where the browser's native module
resolver surfaces the error directly in DevTools.

The shim additionally inlines a **pre-bundle error reporter**: it
installs `error` / `unhandledrejection` listeners before any module
evaluates and `sendBeacon`s to `/web/observability/js_error`
(throttled to one beacon per (message, line, col, hash(stack+cause))
per page — the stack and cause discriminate, since OWL reports every
lifecycle failure with one generic message at 0:0).  This
covers the window where the bundle itself fails to parse/evaluate and
`@web/core/errors/error_service` is unreachable; it is the pre-ESM
mirror of `@web/core/errors/error_beacon` — keep payload fields and
endpoint in sync with that module and
`observability.py::js_error`.

The reporter installs three listeners: bubble-phase `error` (runtime
errors, `kind:"error"`), capture-phase `error` (resource-load failures —
a 404'd module/link — which beacon `kind:"asset_load_error"` AND call
`odoo.loader.handleAssetLoadError(target)` for the one-shot self-heal
reload above), and `unhandledrejection`. Each payload carries a
`phase` of `pre_boot` / `post_boot` (from `odoo.isReady`), so a beacon
tells you whether the failure happened before or after the web client
mounted.

## See also

- `FLOW_DIAGRAM.md` — 14 end-to-end sequence diagrams
- `ARCHITECTURE.md` — module-wide architecture (boot flow, services, views)
- `CONVENTIONS.md` — coding patterns and gotchas
