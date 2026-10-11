import { fileURLToPath } from "node:url";

// oxlint configuration for this checkout, and the shared factory the sibling
const SHARED_IGNORES = [
    "**/static/lib/**/*",
    "tooling/oxlint/simple_import_sort/**",
    "**/*.{ts,mts,cts}",
];

const COMMUNITY_IGNORES = [
    "!addons/web/static/lib/hoot/**",
    "addons/spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js",

    "addons/mail/static/tests/mock_server/contract/store_shapes.js",
    "addons/web/static/tests/views/view_ir_fixture.js",

    "addons/web/static/src/legacy/**",
    "!addons/web/static/src/legacy/*.js",
    "addons/base_import/static/src/legacy/**",

    "addons/web/static/tests/**/legacy/*",

    "odoo/addons/test_assetsbundle/static/src/js/*.js",
];

const BUNDLED_ENTERPRISE_IGNORES = [
    "addons/web_studio/static/src/legacy/**",
    "!addons/web_studio/static/src/legacy/*.js",
    "addons/web_cohort/static/src/legacy/**",
    "addons/web_gantt/static/src/legacy/**",
    "addons/web_map/static/src/legacy/**",

    "addons/web_studio/static/tests/**/legacy/*",
    "addons/web_cohort/static/tests/legacy/**",
    "addons/web_gantt/static/tests/legacy/**",
    "addons/web_map/static/tests/legacy/**",
];

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

const COMMUNITY_ENVS = [
    { files: ["addons/stock_fleet_trace/static/driver/**"], env: { browser: true } },
    {
        files: ["addons/stock_fleet_trace/static/driver/sw.js"],
        env: { serviceworker: true },
    },
    { files: ["addons/stock_fleet_trace/tests/js/**"], env: { node: true } },
    { files: ["addons/mail_telegram/static/src/mini_app/**"], globals: { $: "off" } },
];

const BASE64_RESTRICTED = [
    ...["atob", "btoa"].map((name) => ({
        name,
        message:
            "Use Uint8Array.fromBase64 / bytes.toBase64() (textToBase64 for text): atob/btoa carry one byte per character and throw past U+00FF.",
    })),
];

const EXTENSIONLESS_RELATIVE_IMPORT = {
    regex: "^\\.\\.?/(?!.*\\.(?:js|xml|scss|json)$)",
    message:
        "Relative import without an extension: under native ESM the browser fetches the raw path and a per-file bundle 404s it. Use the bare '@addon/...' specifier.",
};

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
    chai: "readonly",
    describe: "readonly",
    it: "readonly",
    mocha: "readonly",
    DOMPurify: "readonly",
    Prism: "readonly",
    Alert: "readonly",
    Collapse: "readonly",
    Dropdown: "readonly",
    Modal: "readonly",
    Offcanvas: "readonly",
    Popover: "readonly",
    Tooltip: "readonly",
};

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
    "no-unused-expressions": "off",
    "unicorn/no-new-array": "off",
    "unicorn/no-useless-spread": "off",
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
                    "no-empty": ["error", { allowEmptyCatch: true }],
                    "simple-import-sort/imports": [
                        "error",
                        {
                            groups: [["^\\u0000"], ["^@\\w"], ["^\\."]],
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
                    "no-console": ["error", { allow: ["warn", "error"] }],
                },
            },

            {
                files: ["**/static/tests/**/*.js"],
                env: { browser: true },
                globals: { odoo: "readonly", QUnit: "readonly" },
                rules: {
                    "no-console": "off",
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

            {
                files: ["**/static/src/**/*.js"],
                env: { browser: true },
                globals: { odoo: "readonly" },
                rules: layerImports(),
            },

            {
                files: ["**/website_google_map/static/src/**/*.js"],
                globals: { google: "readonly" },
            },

            {
                files: ["**/*service_worker.js", "**/sw.js"],
                env: { serviceworker: true },
                rules: {
                    "no-restricted-globals": ["error", "event", ...BASE64_RESTRICTED],
                },
            },

            {
                files: ["**/*_worker.js", "**/worker/*.js"],
                env: { worker: true },
            },

            {
                files: ["**/static/src/**/worklets/**/*.js"],
                env: { audioworklet: true },
            },

            {
                files: [
                    "**/tooling/**/*.{js,mjs,cjs}",
                    "**/tools/assets/js/**/*.{js,mjs,cjs}",
                    "oxlint.config.mjs",
                ],
                env: { node: true },
                rules: {
                    "no-console": "off",
                },
            },

            {
                files: [
                    "**/website/static/src/js/user_custom_javascript.js",
                    "odoo/tests/dummy.js",
                    "odoo/addons/test_assetsbundle/tests/security_dummy.js",
                ],
                rules: { "unicorn/no-empty-file": "off" },
            },
            {
                files: ["**/web/static/tests/views/view_compiler.test.js"],
                rules: { "no-eval": "off" },
            },

            ...Object.entries(pageGlobals).map(([name, files]) => ({
                files,
                globals: { [name]: "readonly" },
            })),
            ...envs,

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
                            selector:
                                "CallExpression[callee.property.name='toBeCloseTo'] > ObjectExpression > Property[key.name=/^(digits|precision|numDigits)$/]",
                            message:
                                "hoot's toBeCloseTo takes { margin } (an absolute tolerance, default 1), not { digits }. `{ digits: n }` is silently ignored, so the assertion holds to +/-1 — vacuous for any quantity smaller than that. Spell the margin you mean.",
                        },
                        {
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
