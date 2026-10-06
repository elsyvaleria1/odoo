import { fileURLToPath } from "node:url";

// ─────────────────────────────────────────────────────────────────────────────
// oxlint configuration for this checkout, and the shared factory the sibling
// repos (../l10n, ../agromarin) build theirs from.
//
// Loaded with an explicit `-c oxlint.config.mjs`: oxlint discovers only
// `.oxlintrc.json` and TypeScript configs on its own, and a TypeScript one
// needs a Node with type stripping. Every `files` and `ignorePatterns` glob
// resolves against the directory of the config file actually loaded, so each
// repo ships a thin config calling `makeConfig` and the paths stay repo-local.
//
// Every .js/.mjs file a repo holds gets the full ruleset below; the lane is a
// hard zero over all of it.
// ─────────────────────────────────────────────────────────────────────────────
// Paths ignored regardless of which repo consumes this config.
const SHARED_IGNORES = [
    // Vendored third-party libraries (not our code) live under
    // <module>/static/lib/ and are ignored wholesale — by convention,
    // vendored code goes in static/lib and nowhere else, so it is
    // excluded structurally rather than via a per-library allowlist
    // (which always drifts). Putting a third-party file anywhere else is
    // the bug; fix it by relocating into static/lib, not by listing it.
    //
    // Written as `/**/*` (files) rather than `/**` (files AND the directory):
    // a pattern that ignores the directory prunes the traversal, and then a
    // negation such as COMMUNITY_IGNORES' `!addons/web/static/lib/hoot/**`
    // cannot re-include anything, because the directory is never descended
    // into. Ignoring only the files keeps those negations effective.
    "**/static/lib/**/*",
    // Vendored oxlint plugin; see JS_PLUGINS.
    "tooling/oxlint/simple_import_sort/**",
    // TypeScript: every rule here is written for the browser JS, and tsc,
    // whose tsconfig include is **/*.ts, owns these files.
    "**/*.{ts,mts,cts}",
];

const COMMUNITY_IGNORES = [
    // hoot is first-party despite living under web/static/lib (historical).
    "!addons/web/static/lib/hoot/**",
    // Vendored bundle that predates the convention. TODO: relocate under
    // static/lib so this special case can go away too.
    "addons/spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js",

    // Generated Store-serialization contract whose body must stay
    // strict JSON (parsed by json.loads in
    // mail/tests/test_mock_server_contract.py). Formatting it produces
    // valid JS but invalid JSON and breaks that test. Mirrored in
    // .oxfmtrc.json.
    "addons/mail/static/tests/mock_server/contract/store_shapes.js",
    // The view IR fixture is generated and frozen (its header says so).
    // Mirrored in .oxfmtrc.json.
    "addons/web/static/tests/views/view_ir_fixture.js",

    // Legacy code (only top-level adapters are linted)
    "addons/web/static/src/legacy/**",
    "!addons/web/static/src/legacy/*.js",
    "addons/base_import/static/src/legacy/**",

    // Legacy tests
    "addons/web/static/tests/**/legacy/*",

    // Asset-bundle fixtures, not code. Each is a single `var x = N;` whose
    // MINIFIED text is asserted byte-for-byte in the concatenated bundle by
    // test_assetsbundle/tests/test_assetsbundle.py (`var a=1;;` etc.), so the
    // declaration is load-bearing: `no-unused-vars` wants it deleted and
    // `no-var` wants `let`, and either "fix" rewrites the expected output of
    // ~10 tests. Ignored at the config level rather than with an inline
    // disable comment because a comment inside the file is minifier-dependent
    // — the bundle these tests assert on is exactly what must not change.
    "odoo/addons/test_assetsbundle/static/src/js/*.js",
];

// Legacy ignores for the advanced addons bundled in this checkout.
const BUNDLED_ENTERPRISE_IGNORES = [
    // Legacy code (only top-level adapters are linted)
    "addons/web_studio/static/src/legacy/**",
    "!addons/web_studio/static/src/legacy/*.js",
    "addons/web_cohort/static/src/legacy/**",
    "addons/web_gantt/static/src/legacy/**",
    "addons/web_map/static/src/legacy/**",

    // Legacy tests
    "addons/web_studio/static/tests/**/legacy/*",
    "addons/web_cohort/static/tests/legacy/**",
    "addons/web_gantt/static/tests/legacy/**",
    "addons/web_map/static/tests/legacy/**",
];

// Globals a page defines before the module runs: a provider SDK loaded by a
// <script> tag, an importScripts() in a service worker, the POS app's
// window.posmodel. oxlint reads no `/* global */` comment, so each is
// declared here against the files that may read it.
const COMMUNITY_PAGE_GLOBALS = {
    Accept: ["addons/payment_authorize/static/src/**"],
    arrayBufferToBase64Url: ["addons/mail/static/src/service_worker.js"],
    chrome: ["addons/mail/push-to-talk-extension/**"],
    discussUrlRegexes: ["addons/mail/static/src/service_worker.js"],
    google: ["addons/website/static/src/snippets/s_google_map/**"],
    idbKeyval: [
        "addons/mail/static/src/service_worker.js",
        "addons/website_event_track/static/src/js/service_worker.js",
    ],
    IminPrinter: ["addons/pos_imin/static/src/**"],
    MarkerClusterer: ["addons/website_google_map/static/src/**"],
    MercadoPago: ["addons/payment_mercado_pago/static/src/**"],
    notificationTargetPath: ["addons/mail/static/src/service_worker.js"],
    OdooDeviceUtility: ["addons/web_mobile/static/src/**"],
    OdooFin: ["addons/account_online_synchronization/static/src/**"],
    paypal: ["addons/payment_paypal/static/src/**"],
    pickTargetClient: ["addons/mail/static/src/service_worker.js"],
    planPushNotification: ["addons/mail/static/src/service_worker.js"],
    posmodel: [
        "addons/point_of_sale/static/tests/**",
        "addons/pos_*/static/tests/**",
        "addons/pos_appointment/static/src/app/**",
        "addons/pos_iot/static/src/app/services/iot_longpolling/**",
        "addons/pos_restaurant_appointment/static/src/backend/**",
    ],
    process: ["addons/point_of_sale/static/src/app/utils/html-to-image.js"],
    PUSH_NOTIFICATION_ACTION: ["addons/mail/static/src/service_worker.js"],
    QRCode: ["addons/point_of_sale/static/src/utils.js"],
    Razorpay: ["addons/payment_razorpay/static/src/**"],
    Sha1: ["addons/pos_hr/static/src/**"],
    SIP: ["addons/voip/static/src/core/**"],
    Stripe: [
        "addons/hr_expense_stripe/static/src/**",
        "addons/payment_stripe/static/src/**",
    ],
    StripeTerminal: [
        "addons/pos_self_order_stripe/static/src/**",
        "addons/pos_stripe/static/src/**",
    ],
    sw: ["addons/mail/static/src/service_worker.js"],
    TYRO: ["addons/pos_tyro/static/src/**"],
    Vimeo: ["addons/website_slides/static/src/**"],
    waitForWebfonts: ["addons/point_of_sale/static/src/app/services/pos_store.js"],
    Xendit: ["addons/payment_xendit/static/src/**"],
    YT: [
        "addons/website_event_track_live/static/src/**",
        "addons/website_slides/static/src/**",
    ],
};

// Files that run in an environment other than the one their location implies.
const COMMUNITY_ENVS = [
    // The fleet driver is a standalone page with its own service worker, served
    // outside any asset bundle, so neither static/src block reaches it.
    { files: ["addons/stock_fleet_trace/static/driver/**"], env: { browser: true } },
    {
        files: ["addons/stock_fleet_trace/static/driver/sw.js"],
        env: { serviceworker: true },
    },
    { files: ["addons/stock_fleet_trace/tests/js/**"], env: { node: true } },
    // The Telegram mini app is a page of its own, without jQuery: its `$` is a
    // local getElementById helper.
    { files: ["addons/mail_telegram/static/src/mini_app/**"], globals: { $: "off" } },
];

const BASE64_RESTRICTED = [
    ...["atob", "btoa"].map((name) => ({
        name,
        message:
            "Use Uint8Array.fromBase64 / bytes.toBase64() (textToBase64 for text): atob/btoa carry one byte per character and throw past U+00FF.",
    })),
];

// A relative import with no extension resolves nowhere under native ESM: the
// browser fetches the raw path, which a per-file bundle serves as a 404 and the
// module graph fails silently. `./map_model` took the whole settings page down.
const EXTENSIONLESS_RELATIVE_IMPORT = {
    regex: "^\\.\\.?/(?!.*\\.(?:js|xml|scss|json)$)",
    message:
        "Relative import without an extension: under native ESM the browser fetches the raw path and a per-file bundle 404s it. Use the bare '@addon/...' specifier.",
};

// Plugins are passed as absolute paths so a sibling repo loads them from this
// checkout. simple-import-sort is vendored (12.1.1, MIT) rather than installed:
// as a package it declares eslint a peer dependency, and npm would install all
// of eslint beside oxlint to satisfy a declaration the plugin never imports.
const JS_PLUGINS = [
    fileURLToPath(
        new URL("./tooling/oxlint/simple_import_sort/index.js", import.meta.url),
    ),
    fileURLToPath(new URL("./tooling/oxlint/plugin.mjs", import.meta.url)),
];

const ODOO_GLOBALS = {
    odoo: "readonly",
    $: "readonly",
    jQuery: "readonly",
    Chart: "readonly",
    fuzzy: "readonly",
    StackTrace: "readonly",
    QUnit: "readonly",
    py: "readonly",
    FullCalendar: "readonly",
    ScrollSpy: "readonly",
    module: "readonly",
    // Test frameworks
    chai: "readonly",
    describe: "readonly",
    it: "readonly",
    mocha: "readonly",
    // Libraries
    DOMPurify: "readonly",
    Prism: "readonly",
    // Bootstrap components
    Alert: "readonly",
    Collapse: "readonly",
    Dropdown: "readonly",
    Modal: "readonly",
    Offcanvas: "readonly",
    Popover: "readonly",
    Tooltip: "readonly",
};

// ESLint's `recommended` set, rule for rule, on top of the correctness category
// of the plugins `makeConfig` enables (eslint, unicorn, oxc, promise). The
// category is what catches a listener that is never removed, an `await await`,
// a spread that copies nothing; the set pins eslint's own rules either way.
const RECOMMENDED = {
    "constructor-super": "error",
    "for-direction": "error",
    "getter-return": "error",
    "no-async-promise-executor": "error",
    "no-case-declarations": "error",
    "no-class-assign": "error",
    "no-compare-neg-zero": "error",
    "no-cond-assign": "error",
    "no-const-assign": "error",
    "no-constant-binary-expression": "error",
    "no-constant-condition": "error",
    "no-control-regex": "error",
    "no-debugger": "error",
    "no-delete-var": "error",
    "no-dupe-class-members": "error",
    "no-dupe-else-if": "error",
    "no-dupe-keys": "error",
    "no-duplicate-case": "error",
    "no-empty": "error",
    "no-empty-character-class": "error",
    "no-empty-pattern": "error",
    "no-empty-static-block": "error",
    "no-ex-assign": "error",
    "no-extra-boolean-cast": "error",
    "no-fallthrough": "error",
    "no-func-assign": "error",
    "no-global-assign": "error",
    "no-import-assign": "error",
    "no-invalid-regexp": "error",
    "no-irregular-whitespace": "error",
    "no-loss-of-precision": "error",
    "no-misleading-character-class": "error",
    "no-new-native-nonconstructor": "error",
    "no-nonoctal-decimal-escape": "error",
    "no-obj-calls": "error",
    "no-prototype-builtins": "error",
    "no-redeclare": "error",
    "no-regex-spaces": "error",
    "no-self-assign": "error",
    "no-setter-return": "error",
    "no-shadow-restricted-names": "error",
    "no-sparse-arrays": "error",
    "no-this-before-super": "error",
    "no-unassigned-vars": "error",
    "no-undef": "error",
    "no-unreachable": "error",
    "no-unsafe-finally": "error",
    "no-unsafe-negation": "error",
    "no-unsafe-optional-chaining": "error",
    "no-unused-labels": "error",
    "no-unused-private-class-members": "error",
    "no-unused-vars": "error",
    "no-useless-assignment": "error",
    "no-useless-backreference": "error",
    "no-useless-catch": "error",
    "no-useless-escape": "error",
    "no-with": "error",
    "preserve-caught-error": "error",
    "require-yield": "error",
    "use-isnan": "error",
    "valid-typeof": "error",
    // `/** @type {T} */ this.x;` declares a property's type for tsc, and a bare
    // `el.offsetHeight;` forces a reflow: both are statements on purpose.
    "no-unused-expressions": "off",
    // Every `new Array(n)` here passes a length, the one reading the rule
    // guards against confusing with a one-element array.
    "unicorn/no-new-array": "off",
    // Its "useless" copies are mostly `for (const x of [...live])`: the snapshot
    // a loop takes of childNodes or a listener set before it removes from it.
    // The autofix deletes the copy and breaks the loop.
    "unicorn/no-useless-spread": "off",
    // `promise.then(callback)` is how the services hand a result on.
    "promise/no-callback-in-promise": "off",
};

const layerImports = (...patterns) => ({
    "no-restricted-imports": [
        "error",
        { patterns: [...patterns, EXTENSIONLESS_RELATIVE_IMPORT] },
    ],
});

/**
 * Build the shared Odoo oxlint ruleset for one repo.
 *
 * @param {object}   options
 * @param {string[]} [options.ignores]          Extra ignore globs, repo-relative.
 * @param {Record<string, string[]>} [options.pageGlobals] Global name -> the files a page defines it for.
 * @param {object[]} [options.envs]             Per-path environment overrides.
 * @returns {import("oxlint").OxlintConfig}
 */
export function makeConfig({ ignores = [], pageGlobals = {}, envs = [] }) {
    return {
        plugins: ["unicorn", "oxc", "promise"],
        jsPlugins: JS_PLUGINS,
        categories: { correctness: "error" },
        env: { builtin: true, es2026: true },
        ignorePatterns: [...SHARED_IGNORES, ...ignores],
        rules: RECOMMENDED,
        overrides: [
            // =================================================================
            // Main rules — every module
            //
            // `.mjs` is included deliberately: Node-side code in the tree (the
            // asset pipeline's es-module-lexer worker, tooling helpers) is
            // written as `.mjs`, and a bare `*.js` glob left those files
            // matched ONLY by the recommended set — silently exempt from
            // eqeqeq, no-var, prefer-const, curly, arrow-body-style and the
            // import sort while appearing linted.
            // =================================================================
            {
                files: ["**/*.{js,mjs}"],
                env: { browser: true },
                globals: ODOO_GLOBALS,
                rules: {
                    "no-restricted-globals": [
                        "error",
                        "event",
                        "self",
                        ...BASE64_RESTRICTED,
                    ],
                    "no-restricted-properties": [
                        "error",
                        ...["window", "globalThis", "self"].flatMap((object) =>
                            BASE64_RESTRICTED.map(({ name, message }) => ({
                                object,
                                property: name,
                                message,
                            })),
                        ),
                    ],
                    eqeqeq: ["error", "smart"],
                    "no-var": "error",
                    // Intentional error-swallowing is spelled `catch {}`; the
                    // rule otherwise only accepts it when a comment sits inside
                    // the block.
                    "no-empty": ["error", { allowEmptyCatch: true }],
                    "simple-import-sort/imports": [
                        "error",
                        {
                            groups: [
                                // Side effect imports
                                ["^\\u0000"],
                                // @odoo, @web, @mail, @point_of_sale, etc.
                                ["^@\\w"],
                                // Relative imports
                                ["^\\."],
                            ],
                        },
                    ],
                    "simple-import-sort/exports": "error",
                    "no-unused-vars": [
                        "error",
                        {
                            vars: "all",
                            args: "none",
                            ignoreRestSiblings: false,
                            caughtErrors: "all",
                        },
                    ],
                    curly: ["error", "all"],
                    "odoo/no-restricted-syntax": [
                        "error",
                        "PrivateIdentifier",
                        {
                            // H-5 Pattern 4 smell detector — state-management
                            // review 2026-04-19. A setter inside a
                            // ``reactive({...})`` literal conflates state with
                            // effects: the setter runs SIDE effects on other
                            // reactive state when ``obj.foo = x`` is written,
                            // hiding a data-flow edge the signal system can't
                            // reason about. The escape hatch — read-only
                            // caching / pure derivation — only needs a getter,
                            // so this selector only fires on ``set``.
                            selector:
                                "CallExpression[callee.name='reactive'] > ObjectExpression > Property[kind='set']",
                            message:
                                "Pattern 4 smell: setters inside reactive({...}) conflate state with effects. Use plain reactive({foo: null}) + useEffect for side effects, or a SignalStore subclass for computation. See machine_doc_v1/STATE_MANAGEMENT.md §Pattern 4.",
                        },
                    ],
                    "prefer-const": [
                        "error",
                        { destructuring: "all", ignoreReadBeforeAssign: true },
                    ],
                    "arrow-body-style": ["error", "as-needed"],
                    // Keeps stray console.log/debug/info out of shipped code:
                    // warn and error are the genuine diagnostics, and a trace a
                    // developer turns on goes through makeLogger
                    // (@web/core/debug/debug_logger). The test-file and tooling
                    // blocks below turn it back off (they come later, so they
                    // win); a dedicated logging utility opts out with a
                    // file-level disable.
                    "no-console": ["error", { allow: ["warn", "error"] }],
                },
            },

            // =================================================================
            // Test files (Hoot environment)
            //
            // Hoot's primitives (test/expect/describe…) are IMPORTED from
            // "@odoo/hoot", so they never need to be globals; what every test
            // tree needs is the base browser environment.
            // =================================================================
            {
                files: ["**/static/tests/**/*.js"],
                env: { browser: true },
                globals: { odoo: "readonly", QUnit: "readonly" },
                rules: {
                    // Debug logging in tests is fine.
                    "no-console": "off",
                    // Under native ESM, module identity is keyed by resolved
                    // URL, so a relative `../src/...` import and the canonical
                    // `@addon/...` bare specifier for the same file resolve to
                    // TWO distinct module instances: duplicate class
                    // references break `instanceof`/`Array.includes` identity
                    // checks and the un-normalized path 404s.
                    "no-restricted-imports": [
                        "error",
                        {
                            patterns: [
                                {
                                    group: ["**/../src/**", "**/src/*"],
                                    message:
                                        "Do not import addon source from a test via a relative '../src/...' path — under native ESM it resolves to a DUPLICATE module instance (breaks class identity / plugin-set membership and 404s the un-normalized URL). Use the canonical bare specifier, e.g. `@html_editor/...` or `@web/...`.",
                                },
                                EXTENSIONLESS_RELATIVE_IMPORT,
                            ],
                        },
                    ],
                },
            },

            // =================================================================
            // Source files
            //
            // Browser code gets the browser environment.
            // =================================================================
            {
                files: ["**/static/src/**/*.js"],
                env: { browser: true },
                globals: { odoo: "readonly" },
                rules: layerImports(),
            },

            // Google Maps arrives through a <script> tag on the page, so
            // `google` is a real global there and nowhere else.
            {
                files: ["**/website_google_map/static/src/**/*.js"],
                globals: { google: "readonly" },
            },

            // =================================================================
            // Service Worker override — `self` is the standard global
            //
            // `*service_worker.js` and not `service_worker.js`:
            // `push_service_worker.js` is one too, and matched only the
            // dedicated-worker block below, which carries the wrong globals.
            // =================================================================
            {
                files: ["**/*service_worker.js", "**/sw.js"],
                env: { serviceworker: true },
                rules: {
                    "no-restricted-globals": ["error", "event", ...BASE64_RESTRICTED],
                },
            },

            // Web/dedicated workers (e.g. discuss tick_worker.js).
            {
                files: ["**/*_worker.js", "**/worker/*.js"],
                env: { worker: true },
            },

            // AudioWorklet processors run in their own global scope, where
            // `sampleRate` and `registerProcessor` are predefined.
            {
                files: ["**/static/src/**/worklets/**/*.js"],
                env: { audioworklet: true },
            },

            // =================================================================
            // Node tooling scripts — build/typecheck helpers, not browser code
            //
            // tools/assets/js/ is the same situation outside tooling/: the
            // asset pipeline spawns those files as a real Node child process
            // (see `shutil.which("node")` in odoo/tools/assets/esm_lexer.py),
            // so they talk over process.stdin/stdout.
            // =================================================================
            {
                files: [
                    "**/tooling/**/*.{js,mjs,cjs}",
                    "**/tools/assets/js/**/*.{js,mjs,cjs}",
                    "oxlint.config.mjs",
                ],
                env: { node: true },
                rules: {
                    // CLI tooling prints to stdout/stderr — console is its output.
                    "no-console": "off",
                },
            },

            // Placeholders and fixtures that are empty by design: a file the
            // website editor fills in, and the asset-bundle test doubles.
            {
                files: [
                    "**/website/static/src/js/user_custom_javascript.js",
                    "odoo/tests/dummy.js",
                    "odoo/addons/test_assetsbundle/tests/security_dummy.js",
                ],
                rules: { "unicorn/no-empty-file": "off" },
            },
            // The compiler's output is a JS expression; evaluating it is the test.
            {
                files: ["**/web/static/tests/views/view_compiler.test.js"],
                rules: { "no-eval": "off" },
            },

            ...Object.entries(pageGlobals).map(([name, files]) => ({
                files,
                globals: { [name]: "readonly" },
            })),
            ...envs,

            // =================================================================
            // Layer boundary enforcement (Feature-Sliced Design)
            //
            // Import direction is law — lower layers cannot import higher.
            // =================================================================

            // ── Entity layer: model/ and core/domain.js ──────────────────────
            {
                files: [
                    "**/web/static/src/model/**/*.js",
                    "**/web/static/src/core/domain.js",
                ],
                rules: layerImports(
                    {
                        group: ["@web/views/*", "@web/search/*"],
                        message:
                            "Entity layer cannot import widget layer. Use dependency injection.",
                    },
                    {
                        group: ["@web/webclient/*"],
                        message: "Entity layer cannot import page layer.",
                    },
                ),
            },
            // ── Feature layer: fields/ ───────────────────────────────────────
            {
                files: ["**/web/static/src/fields/**/*.js"],
                rules: layerImports(
                    {
                        group: ["@web/views/*"],
                        message:
                            "Feature layer (fields/) cannot import widget layer (views/). Move shared code to core/ or use registry indirection.",
                    },
                    {
                        group: ["@web/search/*"],
                        message:
                            "Feature layer (fields/) cannot import widget layer (search/).",
                    },
                    {
                        group: ["@web/webclient/*"],
                        message: "Feature layer cannot import page layer.",
                    },
                ),
            },
            // ── Shared layer: core/ ──────────────────────────────────────────
            // The shared tier is ORDERED: core < ui < components. It used to be
            // flat, and that is what let `services/` grow inside it importing
            // freely across all three.
            {
                files: ["**/web/static/src/core/**/*.js"],
                rules: layerImports(
                    {
                        group: ["@web/ui/*", "@web/components/*"],
                        message:
                            "core/ is the floor of the shared tier: it owns no surface, so it cannot import ui/ or components/. File the module with what it serves instead.",
                    },
                    {
                        group: ["@web/model/*"],
                        message: "Shared layer cannot import entity layer.",
                    },
                    {
                        group: ["@web/views/*", "@web/search/*"],
                        message: "Shared layer cannot import widget layer.",
                    },
                    {
                        group: ["@web/webclient/*"],
                        message: "Shared layer cannot import page layer.",
                    },
                    {
                        group: ["@web/fields/*"],
                        message: "Shared layer cannot import feature layer.",
                    },
                ),
            },
            // ── Shared layer: ui/ ────────────────────────────────────────────
            {
                files: ["**/web/static/src/ui/**/*.js"],
                rules: layerImports(
                    {
                        group: ["@web/components/*"],
                        message:
                            "Overlay infrastructure sits BELOW the widgets that use it: a widget opens a popover, a popover does not know what a widget is. A single-purpose service belongs next to the component it renders.",
                    },
                    {
                        group: ["@web/model/*"],
                        message: "Shared layer (ui/) cannot import entity layer.",
                    },
                    {
                        group: ["@web/views/*", "@web/search/*"],
                        message: "Shared layer (ui/) cannot import widget layer.",
                    },
                    {
                        group: ["@web/webclient/*"],
                        message: "Shared layer (ui/) cannot import page layer.",
                    },
                    {
                        group: ["@web/fields/*"],
                        message: "Shared layer (ui/) cannot import feature layer.",
                    },
                ),
            },
            // ── Shared layer: components/ ────────────────────────────────────
            {
                files: ["**/web/static/src/components/**/*.js"],
                rules: layerImports(
                    {
                        group: ["@web/model/*"],
                        message:
                            "Presentational components take their data as props; reaching into model/ binds them to the datapoint instead of the values they render.",
                    },
                    {
                        group: ["@web/views/*", "@web/search/*"],
                        message:
                            "Shared layer (components/) cannot import widget layer.",
                    },
                    {
                        group: ["@web/webclient/*"],
                        message: "Shared layer (components/) cannot import page layer.",
                    },
                    {
                        group: ["@web/fields/*"],
                        message:
                            "Shared layer (components/) cannot import feature layer.",
                    },
                ),
            },

            // =================================================================
            // Component-lifecycle: ban <holder>.env.services.X in web's sources
            //
            // ``this.env.services.X`` bypasses the lifecycle-protection wrapper
            // that ``useService("X")`` installs around every method via
            // ``_protectMethod`` (core/utils/hooks.js). Without it, an in-flight
            // promise that resolves after the component unmounts runs on a
            // destroyed component, causing "this.render is not a function" or
            // stale-state bugs that are hard to reproduce.
            //
            // Bare ``env.services.X`` (no holder) inside registry factories and
            // command providers is intentionally NOT flagged — those are not
            // OWL components.
            //
            // Scope: web's source files only. Other addons (POS, mail,
            // hr_attendance) have many existing call sites that need a
            // per-module audit before this rule can be widened safely.
            // =================================================================
            {
                files: ["**/web/static/src/**/*.js"],
                rules: {
                    "odoo/no-restricted-syntax": [
                        "error",
                        "PrivateIdentifier",
                        {
                            selector:
                                "CallExpression[callee.name='reactive'] > ObjectExpression > Property[kind='set']",
                            message:
                                "Pattern 4 smell: setters inside reactive({...}) conflate state with effects. Use plain reactive({foo: null}) + useEffect for side effects, or a SignalStore subclass for computation. See machine_doc_v1/STATE_MANAGEMENT.md §Pattern 4.",
                        },
                        {
                            // `toBeCloseTo(x, { digits: n })` is the Jest
                            // spelling and hoot has no such option: its matcher
                            // takes an absolute `margin` and DEFAULTS IT TO 1.
                            // So the Jest form does not tighten the comparison,
                            // it loosens it to +/-1 — which on a 0..1 quantity
                            // asserts nothing at all, and is how a bottom sheet
                            // progress test passed against a value of 0.148.
                            selector:
                                "CallExpression[callee.property.name='toBeCloseTo'] > ObjectExpression > Property[key.name=/^(digits|precision|numDigits)$/]",
                            message:
                                "hoot's toBeCloseTo takes { margin } (an absolute tolerance, default 1), not { digits }. `{ digits: n }` is silently ignored, so the assertion holds to +/-1 — vacuous for any quantity smaller than that. Spell the margin you mean.",
                        },
                        {
                            // Any receiver, not just `this`: a hook holds its
                            // component in a local (`const owner =
                            // useComponent()`) and reaches
                            // `owner.env.services.x`, the identical hazard with
                            // none of the lifecycle protection. A bare
                            // `env.services.x` still does not match, and must
                            // not: a registry callback is handed an `env` and
                            // has no component to protect.
                            selector:
                                "MemberExpression[property.name='services'][object.type='MemberExpression'][object.property.name='env']",
                            message:
                                "Use useService('X') instead of <holder>.env.services.X. useService adds component-lifecycle protection that prevents promise-resolution-after-destroy bugs. If you genuinely need the raw service (e.g., the dialog outlives the widget, or there is no component to protect), add `// oxlint-disable-next-line odoo/no-restricted-syntax` with a comment explaining why.",
                        },
                    ],
                },
            },
        ],
    };
}

export default makeConfig({
    ignores: [...COMMUNITY_IGNORES, ...BUNDLED_ENTERPRISE_IGNORES],
    pageGlobals: COMMUNITY_PAGE_GLOBALS,
    envs: COMMUNITY_ENVS,
});
