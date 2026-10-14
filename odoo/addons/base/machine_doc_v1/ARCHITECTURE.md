# Base Module Architecture

High-level structure, data flow, and component organization for `odoo/addons/base/`.

## Module Identity

- **Name:** Base
- **Technical name:** `base`
- **Category:** Hidden (auto-installed, the kernel of Odoo)
- **Role:** Core framework — ORM infrastructure, model registry, access control, user management, partner data, localization, scheduling, templating

## Layer Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  ORM Framework (odoo/orm/)                                           │
│  fields, models, api, commands, environments                         │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ defines/extends
                            v
┌──────────────────────────────────────────────────────────────────────┐
│  Base Module (odoo/addons/base/)                                     │
│                                                                      │
│  ┌─────────────────┐  ┌───────────────────┐  ┌────────────────────┐  │
│  │ Model Registry  │  │ Access Control    │  │ Partner/User       │  │
│  │ ir.model        │  │ ir.access         │  │ res.partner        │  │
│  │ ir.model.fields │  │ res.groups        │  │ res.users          │  │
│  │ ir.model.data   │  │                   │  │ res.company        │  │
│  └────────┬────────┘  └────────┬──────────┘  └────────┬───────────┘  │
│           │                    │                      │              │
│  ┌────────┴────────┐  ┌────────┴──────────┐  ┌─────────┴──────────┐  │
│  │ UI Framework    │  │ Actions           │  │ Infrastructure     │  │
│  │ ir.ui.view      │  │ ir.actions.*      │  │ ir.cron            │  │
│  │ ir.ui.menu      │  │ ir.actions.server │  │ ir.sequence        │  │
│  │ ir.asset        │  │ ir.actions.report │  │ ir.attachment      │  │
│  │ ir.qweb         │  │ ir.embedded.*     │  │ ir.job             │  │
│  └─────────────────┘  └───────────────────┘  └────────────────────┘  │
│                                                                      │
│  ┌─────────────────┐  ┌───────────────────┐  ┌────────────────────┐  │
│  │ Localization    │  │ Module System     │  │ Mixins             │  │
│  │ res.country     │  │ ir.module.module  │  │ mixin.image        │  │
│  │ res.currency    │  │ ir.module.cat.    │  │ mixin.avatar       │  │
│  │ res.lang        │  │ ir.config.param.  │  │ format.address.*   │  │
│  │ res.bank        │  │                   │  │ properties.base.*  │  │
│  └─────────────────┘  └───────────────────┘  └────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Wizards (TransientModel)                                       │  │
│  │ partner merge, language install/export/import, module          │  │
│  │ update/upgrade/uninstall, password change, view reset          │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                            │
                            v
┌──────────────────────────────────────────────────────────────────────┐
│  PostgreSQL                                                          │
│  Tables, sequences, constraints, record rules, indexes               │
└──────────────────────────────────────────────────────────────────────┘
```

## No HTTP Controllers

The base module has **no controllers**. It is pure infrastructure/data — all HTTP
endpoints live in other modules (`web`, `website`, etc.). Base provides the models,
access control, and ORM extensions that those controllers depend on.

## Directory Structure

```
odoo/addons/base/
├── __manifest__.py              # Module metadata + asset/data file declarations
├── __init__.py                  # Imports models, report, wizard + post_init hook
├── models/                      # 157 Python model files (core ORM infrastructure)
│   ├── assetsbundle/            #   Asset compilation package (bundle, JS/CSS/XML pipelines, store)
│   ├── decimal_precision.py         #   Configurable decimal precision
│   ├── uom_uom.py                   #   Units of measure and conversion
│   ├── ir_access.py                 #   ir.access: permissions and guards with domains, the decision of every model
│   ├── ir_access_obligation.py      #   ir.access.obligation: what a declared verb obliges beyond holding it (abstract; approval extends it)
│   ├── ir_access_predicate.py       #   ir.access.predicate: a named, validated reach no anchor states
│   ├── ir_access_legacy.py          #   a stock module's ir.model.access lines and ir.rule records, loaded as ir.access rows
│   ├── ir_access_reach.py           #   the recognizer: a stored domain proven equal to reach parts
│   ├── ir_access_class.py           #   ir.access.class: a field sensitivity class rows grant, and ir.access's class target
│   ├── ir_access_log.py             #   ir.access.log: the append-only authorization log
│   ├── access_link.py               #   access.link / .use: bearer links stored as hashes, the one resolver, their use log
│   ├── access_review.py             #   access.review.campaign / .item: certify or revoke access, by a deadline
│   ├── ir_access_exception.py       #   ir.access.exception: one named, dated, logged way past a strict rule
│   ├── ir_access_sod.py             #   ir.access.sod.rule / .function: two duties one person must not hold
│   ├── ir_access_drift.py           #   ir.access.drift: rows that part from their modules' files, scanned nightly
│   ├── ir_access_audit.py           #   mixin.access.audit: security-row changes and refusals in the log
│   ├── ir_access_explain.py         #   explain one record for one principal, row by row; who can
│   ├── ir_access_changeset.py       #   ir.access.changeset: a person's security edit waits, with its impact, for activation
│   ├── ir_access_matrix.py          #   ir.access.matrix: what each group may do on each model, the console's matrix
│   ├── ir_access_convert.py         #   access lines + rules to ir.access rows (pure)
│   ├── ir_actions_act_url.py        #   URL action
│   ├── ir_actions_act_window.py     #   Window actions (open views on a model)
│   ├── ir_actions_act_window_close.py #   Close-window action
│   ├── ir_actions_act_window_view.py #   View ordering inside a window action
│   ├── ir_actions_actions.py        #   Base action model: bindings, path, type dispatch
│   ├── ir_actions_client.py         #   Client-side (JS component) action
│   ├── ir_actions_embedded.py       #   Actions embedded inside views
│   ├── ir_actions_path.py           #   Side table keeping an action path unique
│   ├── ir_actions_report.py         #   Report actions (action type, HTML/text render; PDF is web's inherit)
│   ├── ir_actions_server.py         #   Server actions (code, CRUD, webhook)
│   ├── ir_actions_server_history.py #   Code history of a server action
│   ├── ir_actions_todo.py           #   Configuration wizard queue
│   ├── ir_asset.py                  #   Asset bundle management (directives, paths, sorting)
│   ├── ir_asset_build.py            #   Published ESM builds: current per variant, superseded, swept
│   ├── ir_asset_paths.py            #   Asset directive walk: paths, anchors, insert/remove/replace
│   ├── ir_attachment.py             #   File storage (DB or filestore), GC, MIME detection
│   ├── ir_attachment_assets.py      #   ir.attachment extension: generated-asset GC and regeneration
│   ├── ir_attachment_reading.py     #   Kept readings of a file's bytes (text, cues, barcodes, data, rows)
│   ├── ir_attachment_storage.py     #   Storage backends (DB, filestore, registry of schemes)
│   ├── ir_autovacuum.py             #   Garbage collection framework (@api.autovacuum)
│   ├── ir_binary.py                 #   File streaming helpers (images, downloads)
│   ├── ir_egress.py                 #   Outbound HTTP: address policy, pinned sessions, caps
│   ├── ir_config_parameter.py       #   System parameters (key-value config store)
│   ├── ir_cron.py                   #   Scheduled jobs + triggers + progress tracking
│   ├── ir_default.py                #   Default field values (per-user, per-company)
│   ├── ir_demo_failure.py           #   Demo data failure tracking
│   ├── ir_fields.py                 #   Import field type converters
│   ├── ir_filters.py                #   Saved search filters
│   ├── ir_http.py                   #   HTTP routing, auth, dispatch, translations
│   ├── ir_job.py                    #   Background job queue + channels
│   ├── ir_logging.py                #   Server/client log storage
│   ├── ir_model.py                  #   Model registry + ir.model.inherit
│   ├── ir_model_common.py           #   Shared helpers for the ir.model family (xmlids, upserts, access errors)
│   ├── ir_model_data.py             #   XML ID registry (external identifiers)
│   ├── ir_model_fields.py           #   Field metadata registry
│   ├── ir_model_fields_selection.py #   Selection option management
│   ├── ir_model_reflection.py       #   ir.model.constraint + ir.model.relation (uninstall bookkeeping)
│   ├── ir_module.py                 #   Module system (install, upgrade, dependencies)
│   ├── ir_module_module_dependency.py #   Manifest `depends` entries
│   ├── ir_module_module_exclusion.py #   Manifest `excludes` entries
│   ├── ir_profile.py                #   Code profiling (speedscope output)
│   ├── ir_qweb.py                   #   QWeb template engine (compile + render)
│   ├── ir_qweb_assets.py            #   ir.qweb extension: asset nodes, ESM bundles
│   ├── ir_qweb_assets_esbuild.py    #   ir.qweb extension: esbuild circuit, advisory lock, compile
│   ├── ir_qweb_assets_esbuild_circuit.py #   esbuild failure circuit breaker
│   ├── ir_qweb_assets_import_map.py #   ir.qweb extension: the page's ESM import map
│   ├── ir_qweb_assets_precompile.py #   OWL templates of a bundle compiled ahead of time, per language (node)
│   ├── ir_qweb_assets_served_libs.py #   ir.qweb extension: vendored libraries served to the page
│   ├── ir_qweb_fields.py            #   QWeb field widgets (~20 type formatters)
│   ├── ir_sequence.py               #   Auto-incrementing sequences (standard/no-gap)
│   ├── ir_ui_menu.py                #   Menu tree (hierarchy, visibility, icons)
│   ├── ir_ui_view.py                #   View definitions (arch, inheritance, validation)
│   ├── ir_ui_view_arch.py           #   Arch element handlers (validation, postprocessing, editability)
│   ├── ir_ui_view_authoring.py      #   ir.ui.view as a mixin.template.trust model: a qweb arch is one template field
│   ├── ir_ui_view_base.py           #   Default view generators (form/list/kanban/etc.)
│   ├── ir_ui_view_context.py        #   What an authored extension may not change: how a trusted arch of the combined template evaluates
│   ├── ir_ui_view_custom.py         #   User-specific view customizations (COW)
│   ├── ir_ui_view_name_manager.py   #   View XML structure validator
│   ├── kpi_provider.py              #   KPI aggregation hook (abstract)
│   ├── mixin_access_graph.py        #   Grants inherited live down a tree; grant rows (abstract)
│   ├── mixin_access_graph_reach.py  #   The reach table: every way a principal reaches a node, kept by triggers
│   ├── mixin_avatar.py              #   SVG avatar generation from initials
│   ├── mixin_band.py                #   Numeric band / range mixin
│   ├── mixin_bearer_token.py        #   Bearer token kept as its hash and sealed value
│   ├── mixin_catalog.py             #   Unique translated name, archivable
│   ├── mixin_lifecycle.py           #   Declared state transitions, locking, confirm/cancel checks
│   ├── mixin_color.py               #   Shared defaults, hex validation and palette conversion
│   ├── mixin_format_address.py      #   Address form customization
│   ├── mixin_hierarchy.py           #   Parent/child tree on a materialized path (`parent_path`)
│   ├── mixin_image.py               #   Multi-resolution image fields
│   ├── mixin_merge.py               #   Record merge engine (reference repointing)
│   ├── mixin_module_link.py         #   Manifest-named module link (abstract)
│   ├── mixin_owner_access.py        #   Access following an owner record (abstract)
│   ├── mixin_properties_base_definition.py #   Properties support mixin
│   ├── mixin_recurrence_interval.py #   Every N units: repeat_interval, repeat_unit, next occurrence
│   ├── mixin_company_config.py      #   One configuration record per company per application
│   ├── mixin_recurrence_rule.py     #   Interval plus end policy (forever/until)
│   ├── mixin_tag.py                 #   Coloured label with a stable code
│   ├── mixin_tag_nested.py          #   Tag with a parent/child hierarchy
│   ├── mixin_template_authoring.py  #   What an author below Settings may save in a stored template
│   ├── mixin_template_trust.py      #   Loader-recorded digests that trust a module's template text
│   ├── mixin_user_favorite.py       #   Per-user favourite flag
│   ├── phone_number.py              #   Shared phone number records
│   ├── properties_base_definition.py #   Properties field definitions
│   ├── report_config.py             #   A company's report layout, on mixin.company.config
│   ├── report_paperformat.py        #   Paper format configuration
│   ├── res_bank.py                  #   Banks, parties of res.partner
│   ├── res_company.py               #   Company hierarchy (parent_store)
│   ├── res_config.py                #   Settings wizard framework
│   ├── res_country.py               #   Countries, states, country groups
│   ├── res_currency.py              #   Currencies + exchange rates
│   ├── auth_event.py             #   Durable authentication security actions
│   ├── auth_user_client.py       #   Authentication binding, observations and revocation
│   ├── auth_user_client_session.py #  Session-family lifecycle
│   ├── auth_user_client_address.py #  Aggregated network-address observations
│   ├── res_groups.py                #   Security groups + implications + privileges
│   ├── res_groups_privilege.py      #   Group privilege categories
│   ├── res_lang.py                  #   Language management + formatting
│   ├── res_partner.py               #   Contacts/companies (core business entity)
│   ├── res_partner_bank_account.py          #   Partner bank accounts
│   ├── res_partner_identifier.py    #   One contact's identifier value
│   ├── res_partner_identifier_type.py #   Identifier kinds (RFC, CURP, SIREN...)
│   ├── res_partner_industry.py      #   Industry classification
│   ├── res_partner_tag.py           #   Partner tags (hierarchical)
│   ├── res_users.py                 #   Users (inherits res.partner)
│   ├── res_users_apikeys.py         #   API key management
│   ├── res_users_apikeys_scope.py   #   API key scopes: what a door lets a key do
│   ├── res_users_auth.py            #   Password store: hashing and checks under _get_crypt_context
│   ├── res_users_deletion.py        #   User deletion queue
│   ├── res_users_grant.py           #   res.users.grant: a membership with a cause, a window and a company scope
│   ├── res_users_eligibility.py     #   res.users.eligibility: a group activated for a few hours, break-glass
│   ├── res_users_log.py             #   Login tracking
│   ├── res_users_login_cooldown.py  #   Login-failure cooldown counter
│   ├── res_users_settings.py        #   Per-user settings
│   ├── mixin_resource.py            #   A business record that is a resource (owner or reference)
│   ├── mixin_resource_allocation.py #   Hosts allocating resources over time
│   ├── mixin_resource_kind.py       #   Kind-gated asset fields on a resource host
│   ├── mixin_resource_ledger.py     #   Ledger hooks of a resource host
│   ├── mixin_resource_scheduling.py #   Hosts scheduled against resource calendars
│   ├── mixin_resource_scheduling_tools.py#   Interval arithmetic for scheduling hosts
│   ├── resource_assignment.py       #   Custody: who holds a resource, when
│   ├── resource_calendar.py         #   Working schedules
│   ├── resource_calendar_attendance.py#   A schedule's attendance lines
│   ├── resource_config.py           #   A company's resource settings, on mixin.company.config
│   ├── resource_identifier.py       #   One identifier value of a resource
│   ├── resource_identifier_type.py  #   Identifier kinds (plate, VIN, serial...)
│   ├── resource_kind.py             #   Asset kinds, optionally gated by a group
│   ├── resource_meter.py            #   A resource's meters (odometer, hours...)
│   ├── resource_meter_reading.py    #   Meter readings, monotonic per meter
│   ├── resource_nationality.py      #   A person's nationalities
│   ├── resource_relation.py         #   Composition: a resource inside another
│   ├── resource_reservation.py      #   Bookings of a resource's time
│   ├── resource_resource.py         #   The resource: a person, a thing or a capacity (resource/index.md)
│   ├── resource_role.py             #   Roles a resource can play
│   ├── resource_schedule_exception.py#   Time off and other schedule exceptions
│   ├── resource_time_type.py        #   Kinds of time (work, leave)
│   ├── resource_utils.py            #   Pure interval and context helpers (non-ORM)
│   └── tag_tag.py                   #   Generic tag records
├── wizards/                      # 22 transient model files
│   ├── common.py                #   Base test classes (demo user, portal user)
│   ├── test_*.py                #   Test modules -- counts in TEST_TAGS.md, derived by factcheck.sh
│   ├── wizard_base_explain_access.py #   Why can I see this? explain and who can, as a wizard
│   ├── wizard_ir_actions_server_restore_revision.py #   Server-action run history (diff + restore)
│   ├── wizard_ir_model_create_menu.py #   Create menu item for custom model
│   ├── wizard_ir_module_module_apply_scheduled.py #   Upgrade module with dependency validation
│   ├── wizard_ir_module_module_load_demo.py #   Demo data installation
│   ├── wizard_ir_module_module_uninstall.py #   Module uninstall with dependency analysis
│   ├── wizard_ir_module_module_update_list.py #   Scan for new/updated modules
│   ├── wizard_ir_module_module_view_demo_failure.py #   Show demo data installation failures
│   ├── wizard_ir_profile_enable.py  #   Enable profiling for a bounded window
│   ├── wizard_ir_ui_view_reset_arch.py #   Reset view to original arch (soft/hard)
│   ├── wizard_res_lang_export_translation.py #   Export translations (PO/CSV/TGZ)
│   ├── wizard_res_lang_import_translation.py #   Import translation files
│   ├── wizard_res_lang_install.py   #   Install/activate languages
│   ├── wizard_res_partner_merge.py  #   Deduplicate partners (manual/automatic)
│   ├── wizard_res_partner_merge_line.py #   One candidate group of duplicates
│   ├── wizard_res_users_apikeys_create.py #   API key creation (name, scope, expiry)
│   ├── wizard_res_users_check_identity.py #   Password verification wizard
│   ├── wizard_res_users_eligibility_activate.py #   Activate an eligibility for a few hours, with a justification
│   ├── wizard_res_users_simulate_access.py #   Simulate someone's reach: counts, and only what both read shown
│   ├── wizard_res_users_update_password.py #   Password change, admin form (one line per user)
│   ├── wizard_res_users_update_password_line.py #   One user and their new password
│   └── wizard_res_users_update_password_own.py #   Password change, self-service
├── tests/                       # 212 Python test files + test assets
├── views/                       # 57 XML view definition files
├── data/                        # 28 data files (XML, CSV, SQL, JSON)
├── security/                    # ir.access.csv + groups and access-row XML
├── rng/                         # RelaxNG schemas (view validation)
├── static/                      # CSS, JS, images, test assets
├── i18n/                        # Translations (.po)
└── machine_doc_v1/              # Machine-consumable documentation (this directory)
```

## Model Categories

### Infrastructure Models (ir.*)

The `ir.*` namespace contains all framework-level models. These implement the ORM
registry, access control, UI framework, scheduling, and module system.

| Category | Models | Purpose |
|----------|--------|---------|
| Model Registry | ir.model, ir.model.inherit, ir.model.fields, ir.model.fields.selection | Schema introspection, custom model/field creation |
| Access Control | ir.access, ir.model.constraint, ir.model.relation | Permissions and guards, DB constraints |
| Data Registry | ir.model.data | XML ID ↔ record ID mapping |
| UI Framework | ir.ui.view, ir.ui.view.custom, ir.ui.menu, ir.asset | Views, menus, asset bundles |
| Actions | ir.actions.actions, ir.actions.act_window, ir.actions.act_url, ir.actions.client, ir.actions.act_window_close, ir.actions.todo | All action types for navigation |
| Server Actions | ir.actions.server, ir.actions.server.history | Automated actions (code, CRUD, webhook) |
| Reports | ir.actions.report | PDF/HTML report rendering (WeasyPrint) |
| Embedded Actions | ir.embedded.actions | Actions embedded within views |
| Templating | ir.qweb, ir.qweb.field (+ ~20 subclasses) | QWeb compile/render, field formatting |
| Scheduling | ir.cron, ir.cron.trigger, ir.cron.progress | Scheduled jobs with trigger system |
| Storage | ir.attachment | File storage (DB or filestore) |
| Streaming | ir.binary | File/image download helpers |
| Sequences | ir.sequence, ir.sequence.date_range | Auto-incrementing sequences |
| Configuration | ir.config_parameter, ir.default, ir.filters | System params, defaults, saved filters |
| Module System | ir.module.module, ir.module.category | Module lifecycle management |
| HTTP | ir.http | Routing, auth dispatch, translations |
| Logging | ir.logging, ir.profile | Server logs, code profiling |
| Import | ir.fields.converter | Data import type conversion |
| Autovacuum | ir.autovacuum | Garbage collection framework |
| Demo | wizard.ir.module.module.load.demo, ir.demo_failure, wizard.ir.module.module.view.demo.failure | Demo data management |

### Resource Models (res.*)

The `res.*` namespace contains all business entity models — the core data that
every Odoo module depends on.

| Category | Models | Purpose |
|----------|--------|---------|
| Partners | res.partner, res.partner.tag, res.partner.industry | Contacts, companies, tags, industries |
| Users | res.users, res.users.log, res.users.settings, res.users.deletion | User accounts, preferences, audit |
| Auth | res.users.apikeys, res.users.apikeys.scope, wizard.res.users.check.identity | API keys, their scopes, password verification |
| Security | res.groups, res.groups.privilege | Group hierarchy, privilege categories |
| Companies | res.company | Multi-company hierarchy (parent_store) |
| Localization | res.country, res.country.state, res.country.group, res.lang | Geography, languages |
| Finance | res.currency, res.currency.rate, res.bank, res.partner.bank.account | Currencies, exchange rates, banking |
| Config | res.config, res.config.settings | Settings wizard framework |
| Authentication | auth.user.client, auth.user.client.session, auth.user.client.address, auth.event | Session authority, recognition, observations and security actions |

### Mixins and Utilities

| Model | Purpose |
|-------|---------|
| mixin.image | Multi-resolution image fields (1920/1024/512/256/128) |
| mixin.avatar | SVG avatar generation from name initials |
| mixin.format.address | Country-specific address form layout |
| properties.base.definition | Properties field definition storage |
| mixin.properties.base.definition | Properties support for models |
| decimal.precision | Configurable decimal precision per usage |
| report.paperformat | Paper format configuration (A4, Letter, etc.) |

### Non-ORM Classes

| Class | File | Purpose |
|-------|------|---------|
| AssetsBundle | assetsbundle.py | Asset compilation engine (JS/CSS/SCSS minification) |
| NameManager | ir_ui_view_name_manager.py | View XML structure validation |
| RecordSnapshot | (in web module) | Form state diffing for onchange |
| AssetPaths | ir_asset.py | Asset path collection and ordering |

## File Counts

Derived by `factcheck.sh`, which re-measures every row against the tree.

| Category | Count |
|----------|-------|
| Python (models) | 157 |
| Python (wizards) | 22 |
| Python (tests) | 212 |
| XML (views) | 57 |
| Data files | 28 |
| XML (reports) | 0 |
| XML (wizard views) | 11 |
| Security files | 6 |
| RNG (schemas) | 7 |
| i18n (translations) | 64 |
| Static assets | 349 |
