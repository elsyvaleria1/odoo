# test_lint — map

The fork's own gates: the rules no general linter knows. 9410 lines and no map
until now, which is why `CLAUDE.md` §10 makes a module's machine doc the first
pre-work step.

Every figure below is derived by `odoo/addons/test_lint/machine_doc_v1/factcheck.sh` from the tree, never restated
here as a literal that can drift.

## Two halves

| | |
|---|---|
| **`_rules.py`** | the vocabulary of the Python rules still run here: what a rule *is* -- name, short code, advice. Those are the two cross-unit unique rules and `unreadable-source`; a per-file AST rule is the ruff fork's (below, *The per-file rules, now the ruff fork's*). |
| **`_py_scan.py`** | the engine: corpus, parallel scan, caching. Per file it parses, tokenises and collects the model classes the cross-unit rules fold; it owns nothing about any individual rule. |

A rule used to be spelled in six places and three tests existed only to keep the
copies agreeing. `test_python_lint.py` iterates the registry.

Three helpers keep a gate from paying for a whole-tree walk on its own:

| | |
|---|---|
| **`_parallel.py`** | the process pool every whole-tree gate shares: `map_items(function, items)` runs a module-level function over the items in workers once there are enough of them (`TEST_LINT_JOBS` overrides the count), falls back to a serial run, and reaps the pool's helpers. A worker sees neither the addons path nor the registry. |
| **`_ast_index.py`** | `nodes(tree)`: the module's nodes in one list, built once by the engine and kept on the tree, so the checkers iterate it instead of each paying an `ast.walk`. |
| **`_production_python.py`** | the production Python files of every addon on the path (no `test_*` module, no tests, migrations, upgrades, populate or static) and `extract(function, paths)`, one parse per file in the pool, of which only what `function` returns comes back: the elevation, return-contract and authority-key gates read it, where they used to share a cache of every tree (1.1 GiB at the narrow scope, 1.9 GiB on the full path). |
| **`_model_classes.py`** | what a model class declares, read from its AST: `is_field_call`, `keywords`, `inherited`, `field_declarations` (plain and annotated), and `collect(tree)`, one `ModelClass` per class with its parents, each field's literal-`True` keywords and its `Constraint`/`UniqueIndex` rows. `fold(classes, keyword)` settles a keyword per model over every declaration and `_inherit`. The unique-constraint checkers read it instead of matching `fields.X(...)` and `_inherit` by hand; the scan collects once per file for both unique checkers, and `_py_scan.cross_unit_violations` folds each repository's classes with only those of the repositories it builds on (`lint_case.visible`), so an l10n or agromarin extension never settles an odoo key. |

A gate that needs the parsed tree of many files writes a module-level function
from a tree (or a path) to the facts it judges, and maps it: never a cache of
trees, never a second walk of the tree the engine already walked.

## Where the floors live

**Not in Python.** `LintCase.assert_ratchet` takes a *gate name* and reads
`tests/floors.json` -- one integer per gate, hand-edited, no entry meaning zero (`test_floors.py` refuses a zero entry, unsorted keys or any other spelling);
handed an integer it raises. The ratchet is exact: above the floor fails, below
it fails until the floor is lowered in the same change.

This module was edited as a shared ledger: 24 of its last 40 commits changed
nothing in it but an integer and the comment above it.

A floor is debt still to pay, and an entry exists only while it is above zero. `lint_docstring` (a one-sided ratchet that reads 32 only on a fuller install) is a registry gate. The Python AST rules scan every repository on the addons path, each source tagged with its repository (`_py_scan.corpus`), and are graded per repository: a rule's gate is `lint_<rule>_<repo>` (`_py_scan.findings_by_repository`), so a narrow-scope run grades odoo alone and the full path grades l10n and agromarin against their own floors. In odoo the rules still carrying one are `lint_stored_related_odoo`, the stored
copies of a related value still to convert, `lint_company_field_outside_config_odoo`, the fields still bolted onto
`res.company` outside base instead of an application's `mixin.company.config` model, `lint_hand_rolled_range_odoo`, the numeric min/max pairs declared outside
`mixin.band`, and `lint_n_plus_one_query_odoo` (below). l10n and agromarin carry those four and their own debts besides: null-exempt composite keys and row counters in tests. Their 72 `noqa` without a rationale are gone: most fixed at the cause, the rest saying why. Their floored gates: `lint_company_field_outside_config_agromarin`, `lint_company_field_outside_config_l10n`, `lint_hand_rolled_range_agromarin`, `lint_hand_rolled_range_l10n`, `lint_n_plus_one_query_agromarin`, `lint_n_plus_one_query_l10n`, `lint_null_exempt_composite_unique_agromarin`, `lint_null_exempt_composite_unique_l10n`, `lint_row_counter_in_test_l10n`, `lint_stored_related_agromarin`, `lint_stored_related_l10n`. The enterprise addons merged into odoo brought both of those debts with them: `lint_null_exempt_composite_unique_odoo`, `lint_row_counter_in_test_odoo`. The bundle gates (`bundle_double_eval_<addon>`, the ESM modules a bundle removes and an import inlines again) and the vault ledger `lint_credential_storage` reached zero and are hard zeros now.

The access gates (`tests/test_access_rows.py`, `tests/test_access_matrix_coverage.py`,
`tests/test_readonly_tiers.py`, the derived-field gate) grade every repository on the path,
keyed `<gate>_<repo>`: a repository's rows are read against the models and predicates of
what it builds on (`_access_index.visible`: odoo; odoo and l10n; odoo, l10n and
agromarin), so odoo's counts are the same at the narrow scope and on the full path.
`access_check_override_odoo` counts
the overrides outside base that still decide access in code instead of in
ir.access rows or `_access_guard` (the owners held by a many2one_reference, until
P4); it only shrinks. `access_scope_anchorless_odoo`, `access_scope_anchorless_l10n`
and `access_scope_anchorless_agromarin` count the models where a group
that can be held in some companies only has a permission and the model has no
company anchor, so such a grant applies to all its records (authorization plan
P2); they only shrink. `access_domain_free_odoo` and
`access_domain_free_agromarin` count the rows that still spell
their reach out as a domain reading the user, where a reach through the
model's anchor or a named predicate could say it (authorization plan P4); a
domain naming records only through `ref('<xmlid>')` is a fixed filter and reads
no one. They only shrink. `field_class_anonymous_odoo`, `field_class_anonymous_l10n`
and `field_class_anonymous_agromarin` count, per repository, the fields whose
only class is the one their `groups=` compiles into, which no row can name
(authorization plan P5); they only shrink. `field_class_derived_odoo`,
`field_class_derived_l10n` and `field_class_derived_agromarin` count the derived fields
(related through a classified hop, stored or compute_sudo over a classified
source) that carry no access of their own and declare no `discloses=`; they
only shrink. The elevation gates of `tests/test_elevation.py` count, per
repository, the bare `sudo()` calls (`bare_sudo_odoo`, `bare_sudo_l10n`,
`bare_sudo_agromarin`) that `with_privilege` replaces where code acts on someone's
behalf, and the `has_group` checks (`has_group_odoo`, `has_group_l10n`,
`has_group_agromarin`) that ir.access rows replace as authority, and among them
the ones deciding authority -- beside a write, an action or a refusal
(`has_group_authority_odoo`, `has_group_authority_l10n`,
`has_group_authority_agromarin`, authorization plan P9);
`tests/test_authority_keys.py` refuses, in every repository, an undeclared context
key whose value -- read in the test or through a local bound to it -- decides a
refusal or a check, which `declare_authority_keys` makes every client door strip;
a key reviewed as the subject of a call (`_SUBJECT_KEYS`), a value its door
validates (`_INPUT_KEYS`) or a client's mode replacing the rule it skips
(`_MODE_KEYS`) is not one. Its floors (`authority_context_key_<repo>`, 34 odoo and
19 enterprise) reached zero on 2026-10-02 when each key was decided: those no
client sends declared, the others reviewed; and the
public model methods -- RPC entry points: no leading underscore, not
`@api.private` in the model's or a parent's class, not a door of a
`models.Verb` -- that write through an elevation (`public_elevation_odoo`,
`public_elevation_l10n`, `public_elevation_agromarin`). An elevation is
`sudo()`, `with_privilege`, the superuser as user or an environment built with
`su`, followed through the method's local names; a write is `write`, `create`,
`unlink`, `copy` or a field assignment on elevated records, or raw DML. Such a
method is guarded when, before its first elevated write in source order, it
tests a role or calls `check_access` (or `check_access_rights`,
`check_access_rule`, `has_access`) for an operation other than `read` on
records that are not themselves elevated, or when it writes the records it was
called on under the caller's own access anywhere in the body (the ORM refuses
that write and the RPC transaction rolls back what the elevation wrote). A
CRUD override that calls its `super()` is guarded the same way. Elevations
rooted at a parameter are not counted, since JSON carries no recordset, and a
helper the method calls is not followed;
`tests/test_access_matrix_coverage.py` counts the modules shipping permission
rows without an access matrix (`access_matrix_missing_odoo`,
`access_matrix_missing_l10n`, `access_matrix_missing_agromarin`, authorization plan P9;
a module with one names every model it grants in a cell, a hard zero);
`grant_membership_write` counts the memberships odoo's modules still write
outside base instead of granting them with a cause. `tests/test_patch_order.py`
scans every addon's `static/src` with `acorn` (`tests/js/patch_scan.mjs`) for
`patch()` calls, names each target by the module exporting it, and pairs the
addons that patch the same key while neither depends on the other, whose order
only the bundle decides: each pair is reviewed, with its reason, in
`tests/patch_order_reviewed.json`, whose unreviewed baseline only shrinks
(`patch_order_baseline`); the calls whose target or keys cannot be named
statically are counted per repository (`patch_unnamed_odoo`). `tests/test_return_contracts.py` counts, per
repository, the methods whose return annotation is a union of different kinds
of value (`return_mixed_value_kinds_odoo`, `return_mixed_value_kinds_l10n`,
`return_mixed_value_kinds_agromarin`), of a value or `Literal[False]`
(`return_false_sentinel_odoo`, `return_false_sentinel_l10n`,
`return_false_sentinel_agromarin`) and `bool | None`
(`return_bool_or_none_odoo`, `return_bool_or_none_l10n`,
`return_bool_or_none_agromarin`), the contracts §2.4.23 retires, and the public
`action_*` methods that answer a bool instead of a client action or `None`
(`return_action_bool_result_odoo`, `return_action_bool_result_l10n`,
`return_action_bool_result_agromarin`); each floor only goes down. `tests/test_style_literals.py`
counts, per repository, the hex and numeric `rgb()`/`hsl()` colours module
stylesheets state outside the palette files -- in a plain `.css` page, outside
its `:root` block -- (`colour_literals_odoo`, `colour_literals_l10n`,
`colour_literals_agromarin`), and the raw `backdrop-filter` declarations
outside web's `o-material()` (`backdrop_filters_odoo`, `backdrop_filters_agromarin`), and the hand-written
transition/animation durations a motion token could carry
(`raw_durations_odoo`, `raw_durations_l10n`, `raw_durations_agromarin`).
`tests/test_statement_counts.py` counts, per repository, the raw reads of
`cr.sql_statement_count` in module tests (`raw_statement_count_<repo>`, zero everywhere): rust_engine
serves a read on its own connection, so a test measures with
`counting_statements`, under which every read is Python's; the cursor's own tests
are exempt. `design-themes` is upstream's repository and is not graded. All of them only
shrink; the
sibling repositories' floors are read on the full addons path, and the narrow
scope grades the odoo ones alone. `lint_receiver_fail_open` carried one
for the six hours between the rule's rewrite and the last family's conversion. Everything else -- every other AST rule,
every XML rule, the manifest and record-order gates -- is a hard zero. `n-plus-one-query` reached
zero on 2026-09-12 by reading each of its 295 sites: a loop over the records
is hoisted, a loop that runs one query per distinct key (company, model,
timezone, merged domain, a single-record wizard) carries `# noqa: E8507 -
<why>` naming the key. The four modules moved in from agromarin on 2026-10-01 (odoo 5a084574d2df)
brought 9 sites back, which `lint_n_plus_one_query_odoo` holds (frozen at that commit). Since 2026-10-02 it also reads, in a loop or a comprehension over records (`self`, a chain from it, `env[...]`, a search on one), a query on a local environment's model and one in a comprehension's element, conditions or inner iterables; a loop over a list or a range and a `while` stay out. The six sites it found were hoisted (stock routes, carriers, the helpdesk hook) or name their key (one EXISTS per device, one per data model, one per company's chart).

## The checkers

The Python checkers left here read what one file cannot show: every model class
of a repository at once, or a manifest, or an annotation's resolution. Pure AST,
stdlib only, no odoo import, so they are unit-testable without a database.

| file | rule(s) |
|---|---|
| `_checker_translated_unique.py` | `unique-over-translated-column` (cross-unit) |
| `_checker_null_unique.py` | `null-exempt-composite-unique` (cross-unit) |
| `_checker_manifest.py` | the manifest value rules behind `lint_manifest_value`; not in `_rules.py`, because a manifest is a dict, not a Python unit |
| `_checker_pep649.py` | annotation resolution, used by `test_pep649` |

### The per-file rules, now the ruff fork's

The per-file AST rules test_lint ran in Python are native rules of the ruff fork
`requirements-dev.txt` pins (Agro-Marin/ruff, the `Odoo` linter, prefix `E85`),
at parity with the checkers they replaced on odoo, l10n and agromarin.
`lint_ruff_gates.py` holds them to `floors.json`, and runs `ruff format --check`
in each repository it grades as a hard zero outside `floors.json`. Their
fixtures, and the 377 snippets these checkers' unit tests parsed, live in the
fork (crates/ruff_linter/resources/test/fixtures/odoo, its `lint_cases` corpus).
A finding is waived with `# noqa: E85xx  <reason>` on the line it starts on: ruff
reads no `pylint: disable`, no rule name and no noqa elsewhere in the statement.
The sites the link classification tables used to exempt carry
`# noqa: E8537  <class>: <why>` (or E8539), and ruff's RUF100 reports one that
goes stale; the doors (`access.link`'s resolver, the bearer-token mixin,
`tools.security`) are left out on `lint_ruff_gates.py`'s command line.

| rule | code |
|---|---|
| `sql-injection` | E8501 |
| `gettext-variable` | E8502 |
| `gettext-placeholders` | E8503 |
| `gettext-repr` | E8504 |
| `missing-gettext` | E8505 |
| `raise-unlink-override` | E8506 |
| `n-plus-one-query` | E8507 |
| `orm-import` | E8508 |
| `onchange-domain` | E8509 |
| `config-chainmap-patch` | E8510 |
| `gettext-developer-error` | E8511 |
| `shadowed-definition` | E8513 |
| `tax-company-singular` | E8514 |
| `http-json-string` | E8515 |
| `row-counter-in-test` | E8516 |
| `raw-egress` | E8518 |
| `secret-in-environ` | E8519 |
| `credential-storage` | E8520 |
| `field-redeclared` | E8521 |
| `default-evaluated-at-import` | E8522 |
| `selection-duplicate-key` | E8523 |
| `field-hook-prefix` | E8524 |
| `field-positional-argument` | E8525 |
| `field-attribute-order` | E8526 |
| `dead-field-attribute` | E8527 |
| `receiver-fail-open` | E8528 |
| `stored-related` | E8529 |
| `company-field-outside-config` | E8530 |
| `auth-method-outside-owner` | E8531 |
| `hand-rolled-range` | E8532 |
| `route-untyped` | E8533 |
| `sql-bound-placeholder` | E8534 |
| `abolished-method-call` | E8535 |
| `token-compare` | E8536 |
| `link-token-compare` | E8537 |
| `markup-preformatted` | E8538 |
| `link-door-declared` | E8539 |
| `user-cache-without-groups` | E8540 |
| `http-exception-returned` | E8541 |
| `wsgi-environ-optional-key` | E8542 |
| `empty-recordset-mutation` | E8543 |
| `noqa-rationale` | E8544 |
| `isdigit-guards-int` | E8545 |

`isdigit-guards-int` (E8545) counts an `x.isdigit()` whose function also converts `int(x)` or `int(x[...])` (through `str(x)` and `str(x or default)` too), with no `x.isascii()` beside it. `isdigit()` is true for 128 characters `int()` rejects (superscripts, circled digits: Unicode category No), so the guard passes and the conversion raises; on a route that is a 500 from one query parameter. Its fix is `isdecimal()`, exactly the characters `int()` accepts. 78 sites were fixed by hand before it landed (odoo 49b3da9fd823, l10n 94d8cbe0, agromarin 44c7f5cda) and the rule found 7 more (odoo 555bae015749, l10n 45803461, agromarin 9a4ea7e59). The floor is zero.

`empty-recordset-mutation` (E8543) counts a call of `unlink`, `write`, `update`, `copy`, `action_archive` or `action_unarchive` whose receiver is a bare model lookup -- `env[...]`, `self.env[...]`, `request.env[...]`, through any `sudo()` / `with_context()` / `with_company()` / `with_user()` / `with_env()` / `with_privilege()` -- with no `search`, `browse`, `create` or `filtered` in between, tests and core included. Such a lookup is the empty recordset, so the call iterates nothing and returns: `website_sale`'s `env["product.pricelist"].action_archive()` archived nothing and the demo Benelux pricelist priced its products (9148d5cd5056). A method that works on the model rather than on records (`ir.default.set`) is not one of the six. A lookup held in a local name first is not followed. When it landed it read 3 in odoo, 2 in enterprise and 4 in agromarin (frozen, 2026-10-01, bases 9148d5cd5056, 90dbfdce26f and 84a0c366b), every one in a test: six `res.config.settings` writes that enabled nothing -- three now `create({...}).execute()`, two dropped because their class's `setUpClass` already applies the setting, and one dropped because applying it would install a module -- and three `hr.attendance` unlinks, now the test employee's own attendances. The floor is zero.

`tax-company-singular` (E8514) catches `.tax_ids.filtered(lambda t: t.company_id)`
and the five other tax field names. `account.tax` carries `company_ids`, a
many2many, so the singular reads `AttributeError` at runtime rather than an empty
recordset — the checker only fires inside a `filtered` lambda over a tax field,
where the parameter is known to be a tax.

`row-counter-in-test` (E8516) catches a read of `cr.sql_log_count` in a test file.
That counter is incremented by the ROW count (`odoo/db/metrics.py`, `count=` from the COPY
path) beside `sql_statement_count += 1`, so a correctly batched insert of N rows scores
N and a per-record budget measured with it carries headroom proportional to the rows
each record writes -- which is the regression the budget exists to catch. The rule is
syntactic on purpose: an AST predicate for "measures a batch write" missed the case that
matters, because the write is usually inside the method under measurement rather than in
the test body. Stores are skipped, so a fake cursor defining the attribute is not a
finding, and the five tests that assert the counter itself carry
`# noqa: E8516`.

`raw-egress` (E8518) counts every call that dials out of Odoo without `ir.egress`,
base's one outbound pipeline: `requests` verbs and sessions, `httpx`,
`urllib.request.urlopen`, zeep's `Transport`, `boto3` clients, and since 2026-09-21
the dials no HTTP session carries -- `xmlrpc.client.ServerProxy`, `http.client`
connections, `socket.create_connection`, websocket-client, paho MQTT, pymodbus's
network clients, paramiko, `smtplib`, `imaplib`, `poplib`, `ftplib` -- with import
aliases followed (`import a.b` binds `a`, and the checker resolves `a.b.x` from
that). It skips tests and nothing else: `integration` builds its sessions on
`ir.egress` like any other addon, and the pipeline's own transport lives in
`odoo/libs/guarded_http.py`, outside every addon. It reached zero on 2026-09-13 and
stayed there when the dial targets were added: an XML-RPC peer goes through
`ir.egress.xmlrpc_proxy`; a dial the pipeline cannot carry checks its host through
`ir.egress.check_host` (or `check_url`, which knows `ws`, `mqtt`, `modbus`, `sftp`
and the mail schemes), then either connects to the checked addresses through
`netguard.dial` -- SMTP, IMAP and POP, whose TLS still names the host -- or, for a
library that dials by name itself, carries `# noqa: E8518 - <checked how, and why it
cannot be pinned>`; a call that cannot take a session at all -- a script run beside the
server, the IoT box, botocore -- carries `# noqa: E8518 - <why>`. A subclass of a
dialing client is egress where it is declared, unless it is pinned: it answers the
client's socket hook (`_get_socket` for `smtplib`, `_create_socket` for `imaplib` and
`poplib`) through `netguard.dial`, or inherits that answer from a pinned class of the
same module and reaches it through `super()` if it overrides the hook.
`secret-in-environ` (E8519) is
held at zero: a secret-named key written into `os.environ`, which every later
subprocess of the worker inherits, instead of into the child's own `env=`.
`putenv` counts under every name it is bound to, `os.putenv` or a
`from os import putenv as set_variable`, and a call is matched by its whole
dotted name, so a method of another object that happens to be called `putenv`
is not one.

`credential-storage` (E8520) is the credential_storage gate that went with
`tooling/`, ported: a stored `Char`/`Text` field whose name reads as a third-party
secret, outside `credential`, with the old per-field judgements for share tokens,
published keys, identifiers, hashes and cursors kept. It adds what the old gate
never saw: a settings field with `config_parameter=`, which keeps its value in
clear in `ir.config_parameter`. The floor is the backlog of fields still to move
into the vault.

`auth-method-outside-owner` (E8531) holds `ir.http`'s `auth=` vocabulary to its two
owners: base defines `user`, `none`, `public`, `bearer` and `link` (a record opened
by an `access.link` token), integration defines
`receiver`, and no other module adds a `_auth_method_<name>` (an override of an owned
one, website's `public`, is not a new scheme). An identity is a scheme on a receiver
row or a resolver's verifier, never a fourth method -- `mail_plugin`'s `outlook` and
`calendar`'s attendee token were the two that went that way before the rule.
`hand-rolled-range` (E8532) counts models that declare a numeric `<x>_min`/`<x>_max` (or `min_<x>`/`max_<x>`) pair without `mixin.band` or a `mixin.score.*` scale. A range that classifies a value belongs on the mixin -- half-open, overlap-checked, scoped -- because a pair rolled by hand is inclusive in one model and half-open in the next, and `credit.grade`'s integer pair over a float score proposed no grade between 79 and 80. Ratcheted: a tolerance, a slider or a filter bound is a pair and not a scale, so the floor names the debt and moving a scale onto the mixin lowers it.
`abolished-method-call` (E8535) counts every call of a method this fork removed, in production code and tests alike, and cannot be suppressed: `ABOLISHED` maps each name to what replaced it (`ensure_one()` to `check_singleton()`, `ir.actions.act_window._for_xml_id` to `ir.actions.actions._get_action_dict_by_xml_id`), and lists only names no surviving API reuses, since the receiver's type is unknown here. The call raises AttributeError the first time its line runs. S7's gate hook shipped an `ensure_one()` and refused every receiver route but the device's with a 403 until a calendar suite ran it; agromarin's 3D plant button carried both names until the rules read agromarin.
`link-token-compare` (E8537) counts a bearer token compared (`consteq`, `compare_digest`) or searched for (`('access_token', '=', t)`) anywhere but its two doors, `access.link`'s resolver (`odoo/addons/base/models/access_link.py`) and `tools.security` (`is_hmac_valid` on a scope declared with `register_signed_scope`, for stateless signed tokens), outside tests, unless the function checking it carries `# noqa: E8537  <class>: <why>` naming it as a device's credential, an inbound signature, a key we present to an outside service, a public identifier, an idempotency key derived from a request already admitted, a checkout's handle to the record it fills, a stateless signature in an older format, or an attachment's content token. A lookup of the rows without a token (`('access_token', '=', False)`) is no token's lookup, and a compare whose stored side is a named non-link credential (`subscription.push_token`) is that credential's. A token checked in its own controller is a capability nobody can list, expire or revoke; P7 moved each family onto `access.link` or `is_hmac_valid` and classified the rest, and the floor, `lint_link_token_compare` (56 when the rule landed, 54 once documents moved, 50 once the portal mixin moved), is zero: a new token check must be a link, a signed scope or a classified site. RUF100 reports such a noqa once its site no longer checks a token. A vendor's credential named `api_`, `oauth_`, `push_` or `csrf_` is not counted.
`link-door-declared` (E8539) counts a route that reads an `access_token` and neither declares `auth="link"` nor reaches a door -- `access.link._open_record` (the entry point of RPC routes and helpers), `_resolve`, a model's `_from_*_token`, document's `_from_access_token`, `tools.is_hmac_valid`, directly or through a function of the same file -- unless it carries `# noqa: E8539  <class>: <why>` (a device's credential, an attachment's own token, a meeting room, a token an outside service hands over, a redirect passing it on, a donation's unchecked token), and every reference to the retired `_document_check_access`. Its floor, `lint_link_door_declared`, is zero from the rule's first day; RUF100 reports such a noqa once its route no longer reads a token.
`user-cache-without-groups` (E8540) counts an `ormcache`, outside tests, whose key reads the user (`uid`, `env.user`) and nothing that moves with what the user holds (`env.access_signature`, `_get_group_ids`, `_get_group_signature`, `.share`), in any bucket but `memberships`: a membership, a grant or an eligibility's activation clears the users' group states and nothing else, so such a value outlives the change. `load_menus`, `load_menus_root`, `_track_get_fields` and ai.agent's menus and models key on the signature; the four values that depend on the user but on no group (the user's language, a credential check, ir.default rows, the branches of the companies in use) carry the noqa and its reason. Its floor, `lint_user_cache_without_groups`, is zero from the rule's first day.
`token-compare` (E8536) counts a `==` or `!=` whose operand is named like a token (`token`, `*_token`) or computes one (`_generate_*token`, `_sign_token`, `_encode_link*`, `hmac`), outside tests: `==` returns at the first differing character, so the answer time tells a guesser how much of the secret is right. `consteq` compares in constant time and refuses a non-string. A literal or a named constant on the other side is not a secret compare (a lexer's token types). mail_group's group and action tokens, sign's request token and two OAuth states were the ones found. A bearer token that opens a record (`link-token-compare`'s `is_link_token`) is left to that rule, which counts its `==` as well: the `consteq` this rule advises would be a finding there, and the fix is `access.link`.
`markup-preformatted` (E8538) counts a `Markup()` whose argument was formatted before the wrap, outside tests: a gettext call handed interpolation arguments (`Markup(env._("...%(x)s", x=v))`), a `%` or `str.format` (`Markup("<b>%s</b>" % v)`), an f-string with a non-literal field, or a concatenation (`Markup("<br/>" + message)`, since 2026-10-01). The values are interpolated into a plain `str` and the result is then vouched for, so none of them is escaped; `Markup(template) % values` escapes each one. A value that is a literal, a conditional between literals, or an `escape()`/`html_escape()`/`Markup()` call is not counted. It read 17 in odoo, 4 in enterprise and 1 in agromarin when it landed (frozen, 2026-09-27; website's runtime theme CSS was one, rewritten by 44967a5754bd), and the sites were rewritten to that form -- the agromarin one, an approval refusal notice, showed its own `<p>` tags as text because a Markup argument makes `_()` escape the translation.
`sql-bound-placeholder` (E8534) counts a bound parameter where PostgreSQL parses syntax -- `IN %s`, `INTERVAL %s` -- in a raw `cr.execute`: psycopg 3 binds server-side, so the statement reaches the server as `IN $1` and never parses. `SQL()` expands a tuple and `SQL.literal` inlines; a `timedelta` is adapted as an interval.
`route-untyped` (E8533) counts a route a program calls -- `type="json2"`, or
`auth in {"bearer", "receiver"}` -- that does not declare its parameters: no
`typed=True`, or `typed=True` over a named parameter with no annotation. The second
half is what makes it worth counting, because `typed=True` on a handler that takes
only `**kwargs` declares nothing and would satisfy a shallower rule. A declared
parameter is coerced by `odoo/http/_params.py` and a malformed call is refused at
the door, and the OpenAPI document states the contract instead of an empty object.
Hard zero, reached in one change across the four repos (126 routes: 77 here, 40 in
agromarin, 9 in enterprise); `_type_machine_routes.py` beside the checker is the
fixer that declared 81 of them from the rule's own converters and the defaults.

`receiver-fail-open` (E8528) counts routes that take calls from machines without
declaring who may make them: `auth="public"` or `"none"` with `csrf=False`. Since
2026-09-21 it is a fact of the routing map, not of the handler: a route that admits
its caller says `auth="receiver", receiver="<model>:<field or _method>"`, and
`ir.http._auth_method_receiver` resolves the subject from the path, runs the gate's
`admit()` and leaves `request.admission` for the handler, before the handler runs.
The checker used to follow the controller's own `self.` calls to one of nine gate
method names, which a superclass, a model method or a refactor could hide from it,
and which said nothing to a reader of the routing map. The backlog that the rewrite
surfaced -- 39 routes admitting in the handler's body: the seventeen payment providers,
five POS terminals, Peppol and Nemhandel, IoT, Gelato, Twilio, ECPay -- was converted the
same day, and the floor is zero. A page or a probe that must stay open carries
`# noqa: E8528 - <why>`.

`http-json-string` (E8515) catches `return json.dumps(...)` inside a route whose
`type` is `"http"` or absent. The string goes out as `text/html`, and the client's
`post()`/`get()` helpers in `@web/core/network` refuse JSON typed that way, so the
route works from Python and fails from every browser -- the website form was one.
`type="jsonrpc"` routes are not its business; the spelling it wants is
`request.prepare_json_response(payload)`.

`http-exception-returned` (E8541) catches a route of any `type` that returns an
HTTP exception (`request.prepare_not_found_error()`, `NotFound()`, any werkzeug
default exception) instead of raising it. `odoo.http` raises a returned one for
the route and logs a warning on every hit; before it did, a `jsonrpc` or `json2`
route answered the exception's text as a successful result. The 76 sites of
odoo, enterprise and agromarin were converted on 2026-09-30, and the floor is
zero.

`wsgi-environ-optional-key` (E8542) catches a subscript read of a WSGI environ key
PEP 3333 does not guarantee, `REMOTE_ADDR`, `QUERY_STRING` and every `HTTP_*`
among them, outside tests and core included. Under a server that omits the key
(a unix-socket server has no `REMOTE_ADDR`) the subscript raised `KeyError`: a
login died in `res.users._login`. Read it with `.get()` or the request's
accessor. `REQUEST_URI` counts as guaranteed because
`Application._apply_request_uri` sets it; `os.environ` is not a WSGI environ.
The 12 sites were converted on 2026-09-30, and the floor is zero.

`shadowed-definition` (E8513) runs `_anywhere` rather than inside addons, because
a member defined twice is dead code wherever it sits: Python keeps the last
definition and the earlier one still reads as live. `stock.product_template` is
the case it was written for — two `_search_variant_quantity`, the live one calling
a `_get_domain_locations` that no longer existed, so every quantity search on a
template raised while a correct implementation sat 60 lines above it, unreachable.
Four repetitions are legitimate and exempt: a `@typing.overload` stack, a
`@property` group with its setter/deleter, a `@singledispatchmethod` and its
`@x.register` implementations, and definitions guarded by `if`/`try` such as
`if TYPE_CHECKING`, which are alternatives rather than overwrites.

The fork's field-declaration rules read every `name = fields.X(...)` in a class
body, outside tests. `field-redeclared` (E8521) is the assignment twin of
`shadowed-definition`: the same name bound twice in one class body, the first
declaration dead. `default-evaluated-at-import` (E8522) is `default=` handed
the *result* of a clock or a random source -- `fields.Date.today()`,
`datetime.now()`, `uuid4()`, `_("...")` -- which ran once when the module was
imported, so every record gets the value the server started with; the enterprise
tree carried five. `selection-duplicate-key` (E8523) is a literal selection
list repeating a key: `Selection.__init__` turns the list into a dict, so the
last label wins and the others are dead (`l10n_co_edi` shipped `"23"` twice,
the second marked inactive and never shown). `field-hook-prefix` (E8524) is
`compute=`, `inverse=`, `search=` or `selection=` naming a method outside the
family §2.4.1 of `doc/coding_guidelines.rst` reserves for it, so a reader --
and the naming gates -- can tell a hook from a helper; the hook exists, the
name does not say so.

`_field_spelling.py` keeps the vocabulary for how a declaration is *written*,
which the fixers share: `POSITIONAL_PARAMETERS` names each field class's positional parameters and
`FIELD_ATTRIBUTE_ORDER` the order its keywords are read in (what the field is,
what it says, its shape, how its value is produced, how it is stored, what it
points at, who tracks it, then `groups=` second to last and `help=` last). `field-positional-argument` (E8525) is any positional
argument -- a bare string that only the signature can tell is a label, a
comodel or a selection; `field-attribute-order` (E8526) is keywords out of
that order, or two or more sharing a line; `dead-field-attribute` (E8527) is
an attribute setup ignores: `index=` where there is no column, `precompute=`
without `store=True`, `compute=` beside `related=`; `stored-related` (E8529) is
`related=` with `store=True` on anything but a Binary or an Image -- the one
floored rule of this checker, since the copies exist and are converted module by
module. The fixer is
`_sort_field_attributes.py`, in the table below. `doc/coding_guidelines.rst` §2.3
states the rule.

**What the AST cannot see, `test_field_declarations.py` reads off the
registry** (post-install): whether the method a hook names exists at all
(`lint_field_hook_missing`; `resolve_mro` finds nothing at setup and the first
read raises `AttributeError`, which is how three fork-made mixins declared
seventeen computed fields whose computes only their hosts supply), whether an
`@api.onchange` parameter is a field of a concrete model
(`lint_field_trigger_unknown`; the ORM logs one warning and never fires the
method for that name), whether an `@api.constrains` parameter is a field a
write reaches (`lint_constrains_parameter_invalid`: no such field, a dotted
path, or a non-stored compute with no inverse; the ORM logs one warning, keeps
the method, and `_check_fields` never matches the name, so the constraint
enforces nothing -- point_of_sale's lock-date guard sat dead that way on four
`account_config_id.*` paths; the parameter list may be a callable, which the
gate evaluates as the ORM does, and `test_constrains_gate_reads_a_planted_fault`
keeps it from going blind), and whether a `string=` restates the label
`Field._setup_attrs__` derives from the name -- strip `_id`/`_ids`, `_` to a
space, title-case -- with no lower definition in the MRO saying otherwise
(`lint_field_string_restates_label`). That last one is MRO-aware on purpose: an
`_inherit` class may restate the auto label to override a base class's
different string, and four did (`res.users.create_date` in `website_forum`
over `base`'s "Created on" among them). A syntactic reading cannot tell those
from the 4,205 that said nothing, so the registry decides and the syntactic
scanner is not given the rule.

**`test_unreachable_overrides.py` reads, per model, the MRO of every method**
(`unreachable_override`, a zero rule graded on a fuller install): a
definition that does not extend through `super()` ends the chain, and an
override behind it that does is reported, because it never runs. Two kinds of
definition are not enders. A wrapper the framework installs on the registry
class, a verb door or checkpoint or an approval binding, carries `__wrapped__`
and reaches the rest of the MRO through the method it wraps. Before
2026-09-27 the gate read those as enders and reported 27 overrides of
`action_confirm`, `button_validate`, `action_post` and the like that do run.
`TERMINAL_BY_DESIGN` names the definitions that end their chain on purpose,
one reason each: append-only logs refusing a write, a bank account archived
rather than deleted, a slide taking its channel's URL. What they skip would be
wrong or moot for their model. `test_no_terminal_by_design_entry_is_stale`
fails when a named definition extends again, so the list cannot outlive its
reasons. The full-scope reading of 49 on 2026-09-27 (frozen, base 96d7ba78c081)
was 27 wrappers, 12 terminal by design, 3 copies of mixin_approval_gate's step,
6 broken chains and pos_settle_due replacing the POS field list it now extends.
The copies and the broken chains were fixed. A funding request of
web_scraper_wallet, whose unlink is refused, joined the named ones the same day.

**The same file holds `orphan_super`**, the other half of a chain: a bare
`super().<name>()` that no class after it in a concrete model's MRO defines. A
parent's rename leaves the override under the old name, never called, and
raising `AttributeError` if it were. An abstract model is judged where it is
mixed in, not on its own registry entry, and a class nested in a method answers
for its own `super()`. The full-scope reading of 2 on 2026-09-28 (frozen, base
b98c81a221fb) was `approval_account`'s `button_draft` and `button_cancel`,
dead since `account.move` renamed them `action_draft` and `action_cancel`; the
narrow scope read 1, `base` extending `web`'s `search_panel_select_range`,
which moved to `web`. Both were fixed. `device.transport.event`, whose write is
refused, joined `TERMINAL_BY_DESIGN` the same day.

**`test_stored_reader_context.py` reads the context a stored field's value
depends on** (`stored_field_reader_context`, a zero rule): for every stored
field, the registry's `field_depends_context` minus the keys the ORM stores or
holds constant -- `company` on a company-dependent field, `lang` on a translated
one, `bin_size` on a binary, and the access scope where `get_cache_key` does
not vary it (a relation, or a `compute_sudo` compute) -- and nothing at all on
a relation that is not computed, whose rows every slot is filtered from. What
is left is a column holding one reader's answer for everyone: the ORM keeps a
cache slot per key value and the flush writes the first it meets, which is how
an invoice's signer stayed the previous poster (`78b2667a8d37`). Transient
models are not exempt: the mail composer is read through one env per
recipient language within a single send. The first reading (frozen, base f69c0b072dc0) found
18 on a 783-module install (the full scope plus every module declaring a
context dependency): 17 fields, 9 of them on wizards, under 15 declarations on
computes whose stored value is meant to be the acting user's or the opening
context's, which were dropped, and one label, `resource.assignment.name`,
stored in whichever language computed it and now computed per reader. `test_the_gate_reads_a_planted_fault` keeps the
exemptions from widening.

`unreadable-source` has no checker file of its own: the engine emits it when a
file cannot be parsed or tokenised. Both used to be swallowed, and a file whose
comments cannot be read is one whose every waiver is silently inert.

## The XML rules

The same two halves, for data files. **`_xml_rules.py`** is the vocabulary: an
`XmlRule` is a name, an advice and a check -- a function over one parsed
`DataFile` and a cross-file `Context` (the `_name`s every module's Python
declares, the module names on the addons path). **`_xml_scan.py`** parses every
`core_data_files()` entry whose root is `<odoo>`, `<data>` or `<openerp>` once,
records whether a manifest lists it and whether the module's Python names it,
and runs every rule. A rule declared `every_repository` also reads the data
files of every other checkout on the addons path (`sibling_data_files()`, the
same `is_formattable` filter) and is graded per repository as
`lint_xml_<rule>_<repository>`; today that is `deprecated-output-directive`,
`dynamic-event-handler` and `inline-event-handler`, all at zero in enterprise and agromarin as well. `test_xml_lint.py`
iterates the registry against `lint_xml_<rule>` in `floors.json`, and carries a
planted positive and a clean negative for every rule, so no rule can go vacuous
unnoticed.

Static OWL templates are not data files: `test_owl_templates.py` scans every XML file under an addon's static tree and every tagged `xml` template in addon JS (the vendored lib tree and o_spreadsheet excluded) for `t-esc` -- the attribute, an `<attribute name="t-esc">` operation or an `@t-esc` XPath -- per repository, as the hard-zero gates `owl_t_esc_<repo>`. The vendored OWL 3 still parses `t-esc` as a deprecated alias of `t-out` and warns on every template it compiles. The same walk holds the hard-zero gates `owl_inline_event_handler_<repo>`: a static `on*` attribute on an HTML element (a lowercase tag other than `<t>`) or as the name of an `<attribute>` operation, the client half of `inline-event-handler` and one predicate with it (`_xml_rules.inline_event_handlers`). OWL sets such an attribute as a plain DOM attribute, and the nonce script policy every HTML response carries runs no inline handler; a component's `on*` attribute is a prop and a `t-call`'s a parameter, so neither is counted. A static file that does not parse (test_assetsbundle's malformed fixtures) is skipped.

A hook installed under a UI signal is frozen at mount: `test_setup_hooks.py` finds every `if` inside a component's `setup()` whose condition reads the input modality (`isTouch`, `inputModality`) or the viewport (`isSmall`, `ui.size`), directly or through a getter of the same file, and whose branches call a `use*()` hook. It scans every addon's static JS outside `tests`, the vendored lib tree and o_spreadsheet, per repository, as the hard-zero gates `setup_hook_modality_<repo>` and `setup_hook_viewport_<repo>`.

`test_owl3_api.py` counts, in every addon's `static/src` outside the vendored trees and with JS comments stripped, the bare calls of the six OWL 2 APIs that OWL 3 removes or redefines: `owl_on_rendered` (`onRendered(`), `owl_on_will_render` (`onWillRender(`), `owl_this_render` (`this.render(`), `owl_use_component` (`useComponent(`), `owl_use_effect` (`useEffect(`, whose OWL 3 form drops the dependency array; a component calls `useLayoutEffect` from `@web/core/utils/layout_effect`, OWL 2's implementation over `onMounted` / `onPatched`) and `owl_env_services` (`this.env.services`, which a component takes in setup through `useService` instead). A method that only shares the name, such as `props.comp.onRendered`, is not counted. Beside them it counts the `this.env` keys a component will no longer have, in the JS and, with XML comments stripped, in the static templates: `owl_env_bus`, `owl_env_config`, `owl_env_debug`, `owl_env_is_small`, `owl_env_model`, `owl_env_search_model`, `owl_env_utils`, and the context families `owl_env_dialog_context`, `owl_env_mail_context`, `owl_env_builder_context` and `owl_env_addon_contexts`; each gate's failure message names the hook that replaces the read. `owl_env_reads` counts every `this.env` left in `static/src` -- services, stores and models that keep an env of their own, and the spreadsheet addons' o_spreadsheet reads. `owl_sub_env_raw` counts the `useSubEnv(` / `useChildSubEnv(` calls outside a top-level `provide*` function, so a scope hands a value down only through the `provide*` hook paired with the accessor its readers call. `owl_use_env_raw` counts the `useEnv()` calls outside a top-level `use*` / `provide*` accessor whose body only returns it -- the hooks still reading an env of their own, and those handing the whole env to a model, a dialog or a service. `owl_patched_props` counts a component's `props` or `defaultProps` rewritten after its class is defined -- `X.props = ...`, `Object.assign(X.props, ...)` and a `props` / `defaultProps` key of `patch(X, {...})` -- because OWL 3 reads props from the schema a component passes to `useProps`; the owner exports that object and a patch extends it in place. `owl_copied_props` counts, across every addon at once, a `static props = {...}` that spreads a props object some module extends with `Object.assign(xProps, ...)`: the spread is a copy taken when the class is defined, before any patch runs, so the owner points its static at the exported object and states its defaults there (`.optional(<default>)`). `owl_unbound_props` counts, in every addon's JS outside the vendored trees -- `static/tests` as well as `static/src` -- and with comments stripped but strings kept, a class extending `Component` directly that reads `this.props` (its template literal included) without a `props = ...` field: OWL 3's constructor takes only the node, so such a component's `this.props` is undefined and its first read throws; on 2026-10-01 test_assetsbundle's `LazyTestComponent`, which the OWL 3 port missed because it sits under `odoo/odoo/addons`, failed web's `AddonSuite.test_test_assetsbundle` this way. Every one is an exact ratchet per repository, as the elevation gates are, keyed `<gate>_<repository>` in `floors.json` with the repository from `lint_case.repo_of`: `owl_on_rendered_odoo`, `owl_on_will_render_odoo`, `owl_this_render_odoo`, `owl_use_component_odoo`, `owl_env_services_odoo`, `owl_env_bus_odoo`, `owl_env_config_odoo`, `owl_env_debug_odoo`, `owl_env_is_small_odoo`, `owl_env_model_odoo`, `owl_env_reads_odoo`, `owl_env_reads_l10n`, `owl_env_search_model_odoo`, `owl_env_utils_odoo`, `owl_env_utils_l10n`, `owl_use_env_raw_odoo`, `owl_patched_props_odoo` and `owl_use_effect_odoo`. A repository with no key is a hard zero, which is every context family, `owl_sub_env_raw` everywhere, `owl_patched_props` and `owl_use_effect` outside odoo, `owl_copied_props` and `owl_unbound_props` everywhere, and every gate in agromarin and design-themes. A narrow addons path reads only the odoo keys, so the l10n ones are checked where test_lint runs with l10n on the path. The floors go down as the OWL 3 migration removes the sites. `owl_removed_import` has no key anywhere, a hard zero in every repository: it counts, in every addon's JS outside the vendored trees and with comments stripped, each name an `import { ... } from "@odoo/owl"` asks for that the vendored `web/static/lib/owl/owl.es.js` does not export -- read from that file's `export { ... }` block, so the list follows the library. Such an import fails at link time, and the backend bundle with it: on 2026-09-27 two agromarin modules and design-themes' test_themes each left a whole web client dead at pre_boot.

`test_bus_claims.py` counts, in every addon's `static/src` outside the vendored trees and with JS comments stripped, a bus claim made as a statement of its own: `addChannel(` or `subscribe(` on a receiver named `bus_service`, `busService` or `bus`, right after `;`, `{` or `}`. Both return their release; a claim whose release is dropped cannot be given back, and a component that does so holds the channel or the callback after it is destroyed. A component claims through `useBusChannel` / `useBusSubscription` (`@bus/services/bus_service`), which release on destroy; anything else keeps the release and calls it when its owner ends. An exact ratchet per repository, `bus_dropped_claim_odoo` alone: the services that live as long as the page, whose claims have no owner that ends before it; every other repository is a hard zero.

`test_action_options.py` reads the keys the `ActionOptions` typedef declares in `web/static/src/webclient/actions/action_service.js` and, in every addon's JS outside the vendored trees with comments stripped, finds a `doAction(request, { ... })` call, a method's or a bare function's, whose literal options carry a key outside them; a spread and a non-literal second argument are not read. The action service ignores such a key without a word: `clear_breadcrumbs` in four spreadsheet calls, document's `fullscreen` and voip's `target` were dead this way until 2026-10-11. A hard zero in every repository, `action_unknown_option_<repository>` with no key.

The same file counts the other ambient reads a component makes of `this.env`, each an exact ratchet lowered as components take the value through a hook instead: `owl_env_bus` (`this.env.bus`), `owl_env_config` (`this.env.config`), `owl_env_debug` (`this.env.debug`), `owl_env_is_small` (`this.env.isSmall`), `owl_env_model` (`this.env.model`), `owl_env_search_model` (`this.env.searchModel`) and `owl_env_utils` (`this.env.utils`); `owl_env_dialog_context`, `owl_env_mail_context`, `owl_env_builder_context` and `owl_env_addon_contexts` hold at zero the reads their provider hooks replaced.

| rule | what it catches |
|---|---|
| `attributes-spec-child` | an element other than `<attribute>` under `position="attributes"`. `_apply_attributes` iterates `spec.iter("attribute")`, so a `<field>` there is never added and a `<t t-if>` around an attribute guards nothing -- `website_sale` applied its accordion classes on mobile because of one. |
| `duplicate-field` | one `<field name>` twice in a record. The loader keeps the last; the first is dead. 34 records carried one. |
| `expression-syntax` | `domain`, `context`, `options`, `invisible`, `readonly`, `required`, `column_invisible`, `filter_domain` inside a model-backed view arch that do not parse as Python, or are empty. `%(xmlid)d` is substituted before parsing; QWeb templates are out of scope, because `required=""` is an HTML boolean there. |
| `eval-syntax` | an `eval=` that does not parse. `eval=""` is the case: the loader treats it as absent and reads the element text. |
| `xpath-syntax` | an `expr=` lxml cannot compile (`hasclass()` shimmed). |
| `tree-view` | a `<tree>` element, or `tree` in a `view_mode`. |
| `removed-attribute` | `attrs=` or `states=` inside a view arch. |
| `kanban-box` | `t-name="kanban-box"`, the pre-17.0 card name. |
| `search-item-name` | a `<filter>` without `name`, or a search `<group>` with `string`/`expand`. |
| `deprecated-output-directive` | `t-esc` / `t-raw`; `ir.qweb` logs a deprecation per compile. Graded in every repository on the path (`lint_xml_deprecated_output_directive_<repo>`). Fixer: `_modernize_output_directives.py`. |
| `dynamic-event-handler` | `t-att-on*` / `t-attf-on*` on an element, or as the name of an `<attribute>` operation. `ir.qweb` escapes the value for HTML, not for the JavaScript string it lands in. Graded in every repository on the path (`lint_xml_dynamic_event_handler_<repo>`). The eleven odoo sites became `data-o-href` / `data-clipboard-text` read by portal's `href_link` and `copy_to_clipboard` interactions, a `<label for>` the file input, and one inert radio inside the link that already carried the href. A twelfth, an `<attribute name="t-att-onload">` a grep for the attribute form did not see, was l10n_ph's disbursement-voucher `minimal_layout` override, dead since WeasyPrint (no `subst`, no script runs), and was deleted. |
| `inline-event-handler` | a static `on*` attribute on an element other than `<t>`, or as the name of an `<attribute>` operation. The nonce script policy every HTML response carries (8a75cdb3b0e3) runs no inline handler; 3301acbb8bdd rewrote the server templates' handlers into Interactions and `data-*` attributes. Graded in every repository on the path (`lint_xml_inline_event_handler_<repo>`), at zero in each; `owl_inline_event_handler_<repo>` holds the client templates with the same predicate. |
| `legacy-x2many-command` | an `eval` list holding `(6, 0, ...)`-style tuples; `Command` is in the eval context. Fixer: `_modernize_commands.py`. |
| `menuitem-placement` | a `<menuitem>` in a file whose name does not say `menu`. Fixer: `_relocate_menus.py`. |
| `data-root` | a root element other than `<odoo>`. |
| `orphan-data-file` | a data file no manifest lists and no Python of its module names by path. `addons/marketing_card/data/utm_source_data.xml` was one: the record it declares never existed, and two `env.ref(..., raise_if_not_found=False)` degraded silently around it. |
| `unknown-model` | `<record model>`, a view's `model`, an action's `res_model` naming no `_name` in the tree. |
| `optional-value` | `optional=` outside `show` / `hide` / `conditional`. |
| `kanban-template-scope` | a kanban entry template reading a `t-set` from a sibling template. |
| `groupby-filter-domain` | any `domain` on a group-by `<filter>`; `classifyByContext()` promotes it and `visitFilter()` never reads the domain again. |
| `duplicate-arch-name` | two definitions (not inheritance locators) sharing a `name` in one arch, for `filter`, `page`, `group`, `notebook`. An xpath by that name reaches only the first; two filters with one name are toggled together by `search_default_<name>` -- `maintenance`'s dashboard "Done" link activated a "Done" and a "Ready" filter in different groups and ANDed to nothing. |
| `special-button-type` | `special=` with `type=`: the special is handled first, the type is dead. `name=` stays, it is an xpath and tour target. |
| `nolabel-outside-group` | `nolabel=` on a form field that is not an own child of a `<group>` or a `<setting>`, the only two places `form_compiler.js` reads it: a field in a `<div>` inside a group is as unlabelled without it. Two widgets read it as their own prop wherever they sit (`NOLABEL_WIDGETS`, pinned against the JS), a list or kanban inside the form is another arch, and an inheriting arch's field lands where its locator says, so all three are skipped. Graded in every repository on the path (`lint_xml_nolabel_outside_group_<repo>`), a hard zero in each since the 2026-10-01 sweep. Fixer: `_drop_dead_nolabels.py`. |
| `column-invisible-outside-list` | `column_invisible=` in a form: a literal is promoted to `invisible=`, an expression is never evaluated and the field shows. |
| `boolean-spelling` | `invisible="true"` and friends: py.js aliases `true`, Python does not; the guide writes conditions as Python. |

`readonly-duplicates-invisible` (`invisible="X" readonly="X"` read as a dead readonly) was
retired on 2026-10-01. A `readonly=` that evaluates true keeps the field's pending value out of
the save (`isWithheldAsReadonly`, `field_values.js`), and `invisible=` does not: the 38 attributes
its sweep dropped in b88630a48fee let a hidden field's onchange value reach the server, and
website_slides lost a slide's file when its content type changed (`TestSlideFormContent`).

The last three moved here from `test_view_hygiene.py`, which keeps the gates
that read installed views or every manifest (`OrphanLabelLinter`,
`ActWindowViewOrderLinter`, `DroppedViewTextLinter`).

`DroppedViewTextLinter` (`view_dropped_text`, a hard zero) reads the combined
arch of every installed primary form view, across repositories, for a text node
the form compiler never renders: directly inside a `<setting>`, `<group>`,
`<notebook>`, a notebook's `<page>`, or a `<div name="button_box">` with an
element child -- `form_compiler.js` builds each from `el.children`, which holds
elements only -- and, in a `js_class="base_settings"` form, an `<app>` or a
`<block>` (`settings_form_compiler.js`). Leading text and the tail after a
child both count; text inside a child element (`<span>bytes</span>`) renders
and does not. Such text still reaches the translation export, which is how
`pos_self_order`'s stray "a" got a msgid. A finding names the view that
brought the text, from the combine's provenance, not the primary it lands in.
It replaced a `pos_self_order`-local test that read one module's own
`arch_db`, `<setting>` and `<block>` only.

`ViewFieldAccessLinter` (`view_field_access`) validates every installed primary
non-qweb view the way `_check_xml` does, collecting what the view validator logs
as an "Access Rights Inconsistency": an element whose `invisible`, `readonly`,
`context`, `decoration-*` or other expression reads a field that some of the
users the element is shown to cannot read -- the client is never sent that field
for them. It reads `NameManager.group_inconsistencies()`, the generator the
warning itself is emitted from, so the gate and the install log cannot disagree.
A finding names the primary view and the element. The users an element is shown
to start from the primary view's `group_ids`: a restricted view is served only
to those groups (`get_view` falls back to the next primary view of the type),
so it is validated as they see it. The gate is a zero rule; the narrow scope
installs few views, so grade it on a fuller install.

`test_record_refs.py` judges every reference shape `odoo/tools/convert.py`
resolves at load: `ref=`, `ref()` inside `eval`, `context`, `search` and
`t-value`, a bare `uid=`, `<menuitem parent/action/groups>`, `<template
inherit_id/website_id/groups>`, `<delete id>`, and `%(xmlid)d` inside a
`type="xml"`/`type="html"` field or a `<template>` (with `%%` honoured). Its
declaring tags are the loader's -- `record`, `template` (by `id` or `t-name`),
`menuitem`, `asset`. What the ORM mints is derived, not skipped: a record of a
model with `_inherits` also declares `<xmlid>_<parent_model>`, every manifest
`category` declares its `base.module_category_*` chain the way
`odoo/modules/db.py` does, and `model_<x>` / `module_<x>` resolve only when
`<x>` is a declared model or a module on the path. `field_`, `selection_` and
`constraint_` still need the registry and stay undecidable.

## The fixers, and what they may not change

| | invariant | why |
|---|---|---|
| `_pretty_xml.py` | `_xml_identity.is_faithful` | order-**preserving**: it reindents, wraps, and writes the XML declaration on line 1 -- the one thing it adds, which is why `comparable` no longer counts the declaration as identity (136 files gained it on 2026-09-12) |
| `_sort_xml_records.py` | `_xml_identity.preserves_content` | order-**insensitive**: reordering is the job. Inside a model-backed view arch it also orders the attributes of every view-semantic element (`ARCH_TAGS`, HTML left alone) by `ARCH_ATTRIB_ORDER`: what it is (`name`, `for`, `expr`, `position`, `special`, `type`), what it says (`string`, `placeholder`, `help`, `confirm`), how it renders (`widget`, `icon`, `col`, `nolabel`, `optional`, ...), what data it takes (`domain`, `context`, `options`, `default_order`, `editable`, ...), when it applies (`groups`, `invisible`, `column_invisible`, `readonly`, `required`), then `class`/`style`, then the rest alphabetically -- so the conditions a reviewer scans for sit together. Core had no such order (26,384 of 26,848 arch fields put `name` first and agreed on nothing else); the sweep moved 17,394 lines in 1,272 files. `FIELD_ORDER` is one list per technical model (22, `ir.ui.view` to `mail.message.subtype`), every name pinned to the registry by `test_fixers.py` -- the canon carried four fields a rename had deleted (`groups_id` three times, `print_wizard`, `filter`, `mobile_view_filter`) and sorted nothing for them. A comment travels with the field it precedes; any other child keeps its place after the fields, so the sorter settles every record `test_xml_records.py` reports. |
| `_sort_manifests.py` | `normalize` then a round-trip: the rendered dict must equal `normalize(data)` | value-**normalising**: see below |
| `_modernize_output_directives.py` | `is_rename_only`: the two documents, walked in parallel, differ in nothing but the renamed attribute keys | value-**renaming**: `t-esc` becomes `t-out` in place, which is what `ir.qweb` and Owl both compile it to. The rename is made in the source bytes, inside start tags only, so a file that is not in canonical form keeps its layout: re-serialising through lxml collapsed enterprise's and agromarin's multi-line tags and respelled their declarations: 3775 lines deleted for 2216 renamed in enterprise (frozen, base 7477852a70e). `t-raw` is not renamed -- it skips escaping, so `t-out` could change output -- and an element carrying both is left for a human. Swept 2026-09-12: 115 files, `deprecated-output-directive` 500 -> 0; one inheritance locator (`sale_timesheet`, `td[t[@t-esc=...]]`) followed the rename by hand. Swept 2026-09-27 in enterprise (99 files) and agromarin (15 files, plus `stock_threed_building`'s static template; frozen, bases 7477852a70e and 0bb465fc6), with the translations of the two payroll mail templates it renamed. |
| `_relocate_menus.py` | a fresh install before and after produces the same `ir.ui.menu` rows (xmlid, name, parent, action, sequence, groups) -- checked by installing every changed module from two worktrees and diffing the dump, not by the script | structure-**moving**: every top-level `<menuitem>` of a module, with its subtree and the comments before it, goes to the module's `views/` menus file, named after the module with a `_menus` suffix, in manifest load order (an existing menu file's own menus interleaved by their original position). The file is listed after every file that defines an action a menu names and before the first staying file that needs a menu -- a `ref()` to it, an `ir.ui.menu` record redefining it by `id` -- which is the end of `data` when nothing does. Refuses a module when no such position exists, when a menuitem sits under `noupdate`, or when the module's Python names a menu (`--python-refs-verified <module>` once you have read that none runs while data loads). A source file left with no element is deleted with its manifest line. Swept 2026-09-12: 98 modules; `event`'s six `ir.ui.menu` action patches became the menuitems' own `action=`, `point_of_sale` and `website` carry their menu-bound client actions in the menus file, `hr` swapped two manifest lines; `menuitem-placement` 333 -> 0. |
| `_sort_field_attributes.py` | the module's AST with every field call normalised -- positionals mapped to their keywords, keywords sorted by name -- is identical before and after, checked per file before it is written | spelling-**normalising**: every positional argument becomes the keyword `POSITIONAL_PARAMETERS` names, keywords take `FIELD_ATTRIBUTE_ORDER`, two or more go one per line with a trailing comma and `ruff format` lays the file out. A comment trailing an argument travels with it, one on a line of its own with the argument that follows; a `*args`, a `**kwargs` or a comment after the last argument is declined and reported. Swept 2026-09-13: 12,060 declarations in 2,024 core files, none declined; `field-positional-argument` 5,948 -> 0, `field-attribute-order` 7,525 -> 0. |
| `_drop_field_labels.py` | the registry's `field.string` for every installed field, before and after, is identical -- the fixer removes only what `get_attrs` would have derived anyway, and the check is a fresh registry over the rewritten source | value-**dropping**: `string=` (or the positional label) whose value equals the auto label and whose every lower MRO definition says nothing else, located through the built registry (`-d <db>`), so it is exact rather than syntactic; touched files are re-run through `ruff format`. Swept 2026-09-13 on a 645-module community install: `lint_field_string_restates_label` 4,205 -> 0. A field class called by name rather than as `fields.<X>` (resource_asset's `AssetIdentifier`) loses only a keyword `string=`: its positionals follow its own signature. The full-scope lane found 37 more on 2026-09-25 (frozen, base 97eeb000aad2) that the narrow scope never installs; 31 swept, 6 left in account and mrp. |
| `_modernize_commands.py` | `is_equivalent`: both the original and the rewrite are mapped to `(code, id, values)` tuples and compared as `ast.dump` | value-**rewriting**: `(6, 0, ids)` becomes `Command.set(ids)` inside an `eval` list, and the sub-commands inside a `create`/`update` dict with it. No evaluation, so it runs without odoo-bin; a refusal is a rewrite the round-trip would not reproduce. The new values are spliced into the file's own bytes, each `eval=` matched by its unescaped value and re-escaped for its own quote, and the file is written only when the original tree, with those values set on it, is canonically (c14n) equal to the written bytes -- so a comment, an entity or another attribute's spelling survives, which re-serialising the tree did not guarantee. Swept 2026-09-12: 312 files, `legacy-x2many-command` 1,408 -> 0. |
| `_drop_dead_nolabels.py` | the parsed file with exactly the rule's dead `nolabel` attributes deleted from the tree is canonically (c14n) equal to the rewritten bytes, and the rule run again over the written file finds nothing | value-**dropping**: the k-th `nolabel=` written outside a comment is the k-th element carrying one, so each dead one is cut from the source bytes and the file keeps its formatting; a file whose attributes do not correspond one per tag is skipped. The dead elements are held as a set of the elements themselves: an lxml element is a proxy rebuilt on each access once released, so an `id()` taken during the scan named other elements by the time of the cut -- the first sweep (2026-10-01) removed live labels that way, and its tree-versus-bytes check, made with the same wrong identity, agreed; the re-run of the rule is the check that would have refused it. Swept 2026-10-01: 419 attributes in 180 files across odoo, enterprise and agromarin. |
| `_settings_port_reads.py` | the rewritten module parses to the original tree with each selected call replaced by its port call, compared as `ast.dump`, before the file is written | call-**rewriting**: `X["ir.config_parameter"].sudo().get_param[_int|_float|_bool](key, default)` becomes `X.registry.settings.get[_int|_float|_bool](X, key, default)` (coding_guidelines.rst §10.9), the same read with no elevated recordset handed to the caller. A bare `get_param(key)` gains an explicit `False`, the value it answered; an environment that is not a name or attribute chain, or a call with a comment inside it, is left alone. Swept 2026-10-01 with the hand-converted remainder: 460 reads in 294 files (odoo 242/168, enterprise 213/122, agromarin 5/4), `bare_sudo_<repo>` 4483/2290/513 -> 4250/2077/512. |

`_xml_sweep.py` runs a fixer over every data file **once**; the gates read the
result rather than each making their own pass.

## Manifests: one vocabulary, one fixer, two gates

`_sort_manifests.MANIFEST_KEY_ORDER` is the whole vocabulary: every key the
loader reads (`_DEFAULT_MANIFEST` plus `author`, `license`, `icon`, the
app-store fields, `oca_data_manual` for agromarin's seed tooling) in canonical
order. `DEPRECATED_KEYS` names the four the loader defaults but nothing reads
(`init_xml`, `update_xml`, `demo_xml`, `test`). A key in neither is unknown.
`test_manifests` pins that the two sets together cover `_DEFAULT_MANIFEST`.

`normalize(module, data)` is what the fixer may change, and all of it is
loader-neutral or a stated `doc/coding_guidelines.rst` §1.2 rule: keys go to
canonical order; a key restating its `_DEFAULT_MANIFEST` value is dropped
(`version` excepted, the guide wants it stated; `auto_install: []` is not the
default, it means *always*); `name`, `category`, `author`, `license` and the
URL keys are stripped; `summary` collapses to one line; a whitespace-only
`description` or `website` goes (a whitespace `description` is truthy and
**blocks the README fallback** -- 37 modules had one); `countries` lowercases
(`ir.module.module._update_countries` uppercases anyway); an `icon` equal to
its own default goes; a `set` bundle under `assets` becomes a sorted list (a
set has no order, and `crm_livechat` shipped one). Strings are written as
they are, not `\uXXXX`-escaped -- the 2026-09-11 sweep escaped 12 manifests'
authors, which the `ensure_ascii` default did silently. What follows the dict
literal is kept.

| gate | reads | floor |
|---|---|---|
| `lint_manifest_shape` | `sort_manifest(path, dry_run=True)` is `True` (would rewrite) or `None` (declines) | hard zero |
| `lint_manifest_value` | `_checker_manifest.ManifestChecker.findings` | hard zero |

The value rules are what no fixer can decide: unknown or deprecated key; a
value of the wrong type; `version` the loader would mark uninstallable
(`_normalize_version`); `license` outside `ir.module.module`'s selection
(pinned against the field); `category` with an empty segment or a root no
`odoo/addons/base/data/ir_module_category_data.xml` -- or a sibling's file of
that name -- declares (the loader creates
any category on the fly, so a typo is a stray category); a URL key without a
scheme; `depends` naming itself, a duplicate, or a module on no addons path;
an `auto_install` trigger outside `depends`; `external_dependencies` with a
kind other than `python`, `bin`, `apt` (`l10n_ec_edi` wrote `deb`, read by
nothing), or an `apt` hint for a dependency `python` does not declare; a
`countries` code that is not two letters, or a single country with no `l10n`
in the module name; a `data`/`demo` entry matching no file, listed twice, a
`demo` entry outside `demo/`, a `data` entry under `demo/` or named `*_demo`;
an `icon` matching no file; a hook name `__init__.py` does not bind (a `from
.x import *` waives it); an `assets` bundle not `<module>.<bundle>`, not a
list, or a directive the asset pipeline does not know or with the wrong arity.

**The sibling repositories are read by the same two scripts, without
odoo-bin.** From the workspace root, with the venv interpreter:

```bash
p314o19m/bin/python odoo/odoo/addons/test_lint/tests/_sort_manifests.py --dry-run l10n agromarin design-themes
p314o19m/bin/python odoo/odoo/addons/test_lint/tests/_checker_manifest.py odoo/odoo/addons odoo/addons l10n agromarin design-themes
```

Both locate the `odoo` package from their own path when it is not importable.
The checker resolves `depends` and `icon` across every root it is handed, so
hand it all of them. Measured 2026-09-12 over 1615 manifests: 1194 rewritten,
one value finding left (`partner_relationship_blocklist`, single-country with
no `l10n`, a rename that is not the fixer's call).

## Scope, and what it excludes

`lint_case.is_core_path` scopes every gate to this checkout, except the
per-repository ones (the elevation, OWL 3, setup-hook, `owl_t_esc` and `owl_inline_event_handler` gates and
the `every_repository` XML rules), which read every manifest on the addons path
and key a floor per repository. `_py_scan.corpus()`
additionally drops `_vendor/`, `upgrades/` and `migrations/`;
`_pretty_xml.is_formattable` drops `_vendor`, `static`, `node_modules` and
`tests`, because a fixture is not a data file.

The reference gates (`test_record_refs.py`, `test_group_refs.py`,
`test_menu_parents.py`, `test_button_targets.py`) read *definitions* from every
manifest on the addons path and judge *references* from this checkout only, so
a run with `l10n/` on the path reads the same as the narrow scope.

**The sibling repositories are graded only where they are on the path.** The
cross-repo runner under `tooling/` went on 2026-09-11 with the rest of
`tooling/`; the Python checkers run only here, over this checkout. The
per-repository gates above read l10n and agromarin on the full-scope lane
and see nothing of them at the narrow scope; the manifest scripts above take
roots on the command line.

## Running the gates locally

There is no CI any more; every gate below runs by hand.

| run | scope |
|---|---|
| `odoo-bin --addons-path=odoo/addons,addons -d <db> -i test_lint --test-enable --test-tags /test_lint --stop-after-init --no-http` | the whole module, `--addons-path=odoo/addons,addons`, only `test_lint` installed |
| `odoo/addons/test_lint/lint_full_scope.sh` | the whole module on the workspace addons path, over a scratch install of the script's `FULL_SCOPE` modules (odoo, l10n and agromarin), with demo data, dropped afterwards; a module left without its demo fails the lane; `--keep`/`--db` re-run on one database, `--tags` narrows, `--without-demo` skips the demo |

**A gate that reads the installed registry cannot be graded at the narrow
scope.** `TestSchemeDuplication` passes there for want of modules to measure;
`TestDocstring` is one-sided (`exact=False`) for the same reason. Do not floor either at a narrow-scope reading.
`TestFieldDeclarations` and `ViewFieldAccessLinter` read the registry too, but their floors are zero and they
pass at the narrow scope over the little installed there: a zero there says
nothing about a module that is not installed. The dead point_of_sale constraint
read zero at the narrow scope and four on an install with point_of_sale, so run
the class on a fuller install before trusting it.

**The full-scope lane is what grades the rest.** `lint_full_scope.sh` installs
`FULL_SCOPE` with demo data into a scratch database created through odoo-bin (so
`db_template` applies), repeats `-i` until the modules it names stop going
missing (a single `-i` converges on a subgraph and exits 0), fails when an
installed module is left without its demo, runs `/test_lint` with
`-u test_lint` and drops the database. A `--ref` worktree grades its own addons: the conf's
`odoo/addons` entry is replaced by the checkout's. What only this lane can see:
`TestFieldDeclarations`, `TestStoredReaderContext`, `TestIndex`, `TestLintOverrideSignatures`,
`OrphanLabelLinter`, `DroppedViewTextLinter`, `ViewFieldAccessLinter`, `TestSchemeDuplication`, `TestDocstring`, the bundle gates
that read what is served (`TestBundlesAssemble`, `TestBundleTokenDefs`,
`TestOrphanAssets`, `TestAssetPathsExist`, `TestBundleDoubleEvaluation`), and the
per-repository floors of l10n and agromarin (`bare_sudo_agromarin`,
`owl_env_reads_l10n`). `OrphanLabelLinter` binds a label the way
`FormCompiler` does -- to the next compiled field whose `id` (else `name`) it
names, or at once to one already compiled, a literal-invisible node or ancestor
never compiling -- so a label naming a field `id` is not orphaned and a later
hidden duplicate of the field does not empty it.
