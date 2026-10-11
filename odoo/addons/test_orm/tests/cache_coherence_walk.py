"""Random walks over the cache and compute engine, checked against fresh reads.

A walk is a list of operations drawn from a seed: creates (single and batch,
with x2many commands of every code, mixed and bare-id lists), writes, unlinks,
archiving, reads through users, languages, companies and `active_test`,
invalidations, flushes, savepoints released or rolled back, a constraint
violation caught inside a savepoint, drafts built with `new()` and kept
(`LIVE_DRAFTS` at a time) to be edited by later steps (`draft_edit`), reads
and writes of company-dependent fields through `with_company` (`company`),
properties written by name or as definitions with values (`DEFINITIONS`),
lookups through an ormcache, and ancestor units (a category grafted under new ones,
its derived value read, a level above it dropped from the cache alone, a level
at or above that one written). Operations name records by draws resolved against the
rows alive when they run, so any subsequence of a walk is a walk: that is what
lets a failure shrink to the few operations that cause it.

At every `check` operation, at every savepoint's end and at the end, the walk
flushes and then asserts, each time in transactions that share nothing with
the walk's own:

1. every value the walk's cache holds for a real record equals what a fresh
   read returns for the same user, context and record (an x2many as a set:
   runtime.md lets a slot keep the order of its last fill);
2. every stored computed and stored related field equals its value recomputed
   from scratch, and every `parent_path` equals the chain its `parent_id`s
   spell;
3. every ormcached category lookup equals a fresh search;
4. no line holds the negative quantity its constraint refuses;
5. every order's properties read the same, under their category's
   definition, through the walk's caches as through a fresh read (a
   properties field's stored value is not compared with its recomputation:
   its compute adds the definition's defaults to what it holds);
6. every kept draft reads, field by field (its lines' twins included), what
   its origin holds now or what it was assigned, and lists its origin's
   lines unless it was given lines.

A draft step also fails at once when it changes a saved record's pending
write. `KINDS_COMPARED` names what a bounded run must have compared.

Where the walk is narrower than any program could be, it is on purpose:

- a single operation never names a record one of its own DELETE commands
  removes, nor makes a category its own ancestor: the ORM refuses both
  (MissingError, a foreign key, a recursion), and a refused operation leaves
  the transaction to be rolled back, which a walk does not do midway;
- a draft whose origin was deleted, or taken by a rolled-back savepoint, is
  let go unread: it raises MissingError when read, as upstream's. The twins
  it was given relations to keep being read, and no longer list it;
- the models declare what their computes read (`.active` of an x2many over
  archivable rows, `active_test` where the result depends on it) and their
  stored computes store the same value whichever caller triggers them: see
  test_orm's `test_cache_coherence`.

A plain `cr.savepoint(flush=False)` is the raw-SQL tool: rolling it back leaves
the ORM state to the caller, as upstream does. The walk therefore opens one on
a flushed transaction (work pending from before would otherwise be flushed into
it and rolled back with it), flushes before rolling it back and recovers with
`env.clear()` after (the cache and the computes still queued, those of drafts
included), and checks what that contract still promises: the ormcache groups
the rolled-back work cleared are cleared again.
"""

import random
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.libs.iteration import PENDING

CATEGORY = "test_orm.coherence.category"
ORDER = "test_orm.coherence.order"
LINE = "test_orm.coherence.line"
TAG = "test_orm.coherence.tag"
ITEM = "test_orm.coherence.item"
SPECIAL = "test_orm.coherence.item.special"
MODELS = (CATEGORY, ORDER, LINE, TAG, ITEM, SPECIAL)
ARCHIVABLE = (CATEGORY, ORDER, LINE, TAG)

CODES = ("A", "B", "C")
NAMES = ("a", "b", "c", "")
LABELS = ("x", "y", "")

READABLE = {
    CATEGORY: (
        "name",
        "code",
        "active",
        "parent_id",
        "parent_path",
        "child_ids",
        "order_ids",
        "item_ids",
        "depth",
        "full_name",
        "trail",
        "order_total",
        "subtree_total",
        "item_weight",
        "properties_definition",
    ),
    ORDER: (
        "name",
        "active",
        "category_id",
        "line_ids",
        "tag_ids",
        "priority",
        "fallback_tag_id",
        "priority_label",
        "attributes",
        "total",
        "line_count",
        "tag_names",
        "tag_labels",
        "category_name",
        "category_depth",
    ),
    LINE: (
        "order_id",
        "active",
        "qty",
        "price",
        "amount",
        "order_category_id",
        "order_name",
    ),
    TAG: ("name", "label", "active", "order_ids", "order_count"),
    ITEM: ("name", "weight", "category_id"),
    SPECIAL: ("name", "weight", "category_id", "extra", "load", "weight_label"),
}

PLAIN = frozenset(
    ("name", "code", "active", "qty", "price", "weight", "extra", "label")
)
RECURSIVE = frozenset(("depth", "full_name", "trail", "subtree_total"))

DEFINITIONS = (
    {"name": "p_int", "type": "integer", "string": "Int", "default": 3},
    {"name": "p_char", "type": "char", "string": "Char"},
    {"name": "p_bool", "type": "boolean", "string": "Bool"},
    {"name": "p_tag", "type": "many2one", "string": "Tag", "comodel": TAG},
)
DRAFT_FIELDS = ("name", "priority", "category_id", "fallback_tag_id")
DRAFT_LINE_FIELDS = ("qty", "price")
LIVE_DRAFTS = 3

CHECKPOINTS = frozenset(("check", "close_savepoint"))
KINDS_COMPARED = ("cache", "recompute", "ormcache", "properties", "drafts")

_KINDS = (
    ("create", 14),
    ("write", 24),
    ("unlink", 4),
    ("archive", 4),
    ("read", 40),
    ("invalidate", 7),
    ("flush", 3),
    ("savepoint", 4),
    ("caught_error", 2),
    ("draft", 5),
    ("lookup", 6),
    ("ancestor", 4),
    ("company", 5),
    ("draft_edit", 4),
    ("check", 6),
)


PROFILES = (
    {"watched": (CATEGORY,), "boost": {"read": 2, "invalidate": 2, "ancestor": 3}},
    {"watched": (ITEM, SPECIAL), "boost": {}},
    {"watched": (ORDER, LINE, TAG), "boost": {"archive": 2}},
    {"watched": (CATEGORY, ORDER), "boost": {"savepoint": 4, "lookup": 2}},
    {
        "watched": (ORDER, LINE),
        "boost": {"draft": 3, "draft_edit": 3, "caught_error": 3},
    },
    {"watched": (ORDER, TAG), "boost": {"company": 3, "draft": 2}},
    {"watched": None, "boost": {}},
)


def generate(seed, steps):
    draw = _Draw(random.Random(seed), PROFILES[seed % len(PROFILES)])
    ops = []
    while len(ops) < steps:
        ops += draw.unit()
    return ops[:steps]


class _Draw:

    def __init__(self, rng, profile):
        self.rng = rng
        boost = profile["boost"]
        self.kinds = [kind for kind, _weight in _KINDS]
        self.kind_weights = [
            weight * boost[kind]
            if kind in boost
            else weight
            if kind in ("create", "write", "check", "lookup")
            else weight * rng.choice((0, 1, 1, 2))
            for kind, weight in _KINDS
        ]
        self.focus = {model: self._focus(fnames) for model, fnames in READABLE.items()}
        watched = profile["watched"] or rng.sample(MODELS, rng.choice((1, 2, 3)))
        self.model_weights = [5 if model in watched else 1 for model in MODELS]
        self.recent = []

    def _focus(self, fnames):
        weights = [
            1 if fname in PLAIN else 6 if fname in RECURSIVE else 3 for fname in fnames
        ]
        count = self.rng.randint(1, min(4, len(fnames)))
        chosen = []
        while len(chosen) < count:
            fname = self.rng.choices(fnames, weights)[0]
            if fname not in chosen:
                chosen.append(fname)
        return chosen

    def number(self):
        return self.rng.randrange(1 << 16)

    def model(self):
        if self.recent and self.rng.random() < 0.5:
            return self.rng.choice(self.recent)[0]
        return self.rng.choices(MODELS, self.model_weights)[0]

    def field(self):
        if self.recent and self.rng.random() < 0.6:
            return self.rng.choice(self.recent)
        model = self.model()
        return model, self.rng.choice(self.focus[model])

    def refs(self):
        if self.rng.random() < 0.25:
            return ()
        return tuple(self.number() for _ in range(self.rng.choice((1, 1, 2, 3))))

    def unit(self, depth=0):
        operation = self.operation()
        if operation[0] == "ancestor":
            return self.ancestor_unit(*operation[1:])
        if operation[0] == "company" and self.rng.random() < 0.4:
            _kind, _write, draws, viewer, other, payload = operation
            return [("company_rename", draws, viewer, other, payload), ("check",)]
        if operation[0] != "savepoint" or depth > 1:
            return [] if operation[0] == "savepoint" else [operation]
        inner = []
        for _ in range(self.rng.randint(1, 5)):
            inner += self.unit(depth + 1)
        return [operation, *inner, ("close_savepoint", self.rng.random() < 0.6)]

    def ancestor_unit(self, draw, fname, viewer, payload):
        rng = self.rng
        dropped = rng.choice((1, 1, 2))
        written = dropped + rng.choice((0, 1))
        return [
            ("graft", draw, written, viewer, payload),
            ("read", CATEGORY, (draw,), viewer, fname),
            ("uncache_ancestor", draw, dropped, fname),
            ("write_ancestor", draw, written, viewer, payload),
            ("check",),
        ]

    def operation(self):
        rng = self.rng
        number = self.number
        match rng.choices(self.kinds, self.kind_weights)[0]:
            case "create":
                count = rng.choice((1, 1, 2, 3))
                return ("create", self.model(), count, number(), number())
            case "write":
                return (
                    "write",
                    self.model(),
                    self.refs() or (number(),),
                    number(),
                    number(),
                )
            case "unlink":
                return ("unlink", self.model(), self.refs() or (number(),), number())
            case "archive":
                refs = self.refs() or (number(),)
                return (
                    "archive",
                    rng.choice(ARCHIVABLE),
                    refs,
                    number(),
                    rng.random() < 0.6,
                )
            case "read":
                model, fname = self.field()
                self.recent = [*self.recent[-3:], (model, fname)]
                return ("read", model, self.refs(), number(), fname)
            case "invalidate":
                model, fname = self.field()
                scope = rng.choice(("all", "model", "recordset", "fields", "fields"))
                return ("invalidate", scope, model, self.refs() or (number(),), fname)
            case "savepoint":
                return ("savepoint", rng.random() < 0.5)
            case "caught_error":
                return ("caught_error", number(), number())
            case "draft":
                return ("draft", number(), number())
            case "draft_edit":
                return ("draft_edit", number(), number())
            case "company":
                return (
                    "company",
                    rng.random() < 0.5,
                    self.refs() or (number(),),
                    number(),
                    rng.random() < 0.5,
                    number(),
                )
            case "lookup":
                return ("lookup", rng.choice(CODES), number())
            case "ancestor":
                fname = rng.choice(("trail", "trail", "trail", "full_name", "depth"))
                return ("ancestor", number(), fname, number(), number())
            case kind:
                return (kind,)


def viewers(env, user_id, company_id):
    contexts = [
        {
            **({"lang": "fr_FR"} if lang else {}),
            **({"active_test": False} if inactive else {}),
            **({"allowed_company_ids": [company_id]} if other else {}),
        }
        for lang in (False, True)
        for inactive in (False, True)
        for other in (False, True)
    ]
    found = []
    for context in contexts:
        found.append(env(context=context))
        user_env = env(user=user_id, context=context, su=False)
        found += [user_env, user_env(su=True)]
    return found


@dataclass(frozen=True)
class Failure:
    signature: tuple
    detail: str


class Walk:

    def __init__(self, harness):
        self.harness = harness
        self.env = harness.env
        self.viewers = harness.viewers
        self.savepoints = []
        self.log = []
        self.compared = Counter()
        self.doomed = set()
        self.drafts = []
        self.assigned = {}
        self.company_envs = []
        other = next(
            viewer.context["allowed_company_ids"][0]
            for viewer in self.viewers
            if viewer.context.get("allowed_company_ids")
        )
        self.companies = (self.env.company.id, other)

    def run(self, ops):
        for step, op in enumerate(ops):
            self.log.append(f"{step}: {op!r}")
            self.doomed = set()
            try:
                getattr(self, f"_op_{op[0]}")(*op[1:])
            except Exception as exc:
                return self._failure(("raised", op[0], type(exc).__name__), exc)
            if op[0] in CHECKPOINTS and (failure := self.check()):
                return failure
        while self.savepoints:
            try:
                self._op_close_savepoint(False)
            except Exception as exc:
                return self._failure(
                    ("raised", "close_savepoint", type(exc).__name__), exc
                )
        return self.check()

    def _failure(self, signature, exc):
        return Failure(signature, f"{type(exc).__name__}: {exc}")


    def _viewer(self, draw):
        return self.viewers[draw % len(self.viewers)]

    def _alive(self, model_name):
        doomed = self.doomed
        return sorted(
            id_
            for id_ in self.harness.alive_ids(model_name)
            if (model_name, id_) not in doomed
        )

    def _pick(self, model_name, draws):
        alive = self._alive(model_name)
        if not alive:
            return []
        return sorted({alive[draw % len(alive)] for draw in draws})

    def _op_create(self, model_name, count, viewer, payload):
        env = self._viewer(viewer)
        rng = random.Random(payload)
        vals_list = [self._vals(rng, model_name, ()) for _ in range(count)]
        self.log[-1] += f" {vals_list}"
        records = env[model_name].create(vals_list)
        self.log[-1] += f" -> {records._ids}"

    def _op_write(self, model_name, draws, viewer, payload):
        ids = self._pick(model_name, draws)
        if not ids:
            return
        env = self._viewer(viewer)
        vals = self._vals(random.Random(payload), model_name, ids)
        if "attributes" in vals and (
            "category_id" in vals
            or len(self.env[model_name].browse(ids).category_id) > 1
        ):
            del vals["attributes"]
        if vals:
            self.log[-1] += f" {ids} {vals}"
            env[model_name].browse(ids).write(vals)

    def _op_unlink(self, model_name, draws, viewer):
        if ids := self._pick(model_name, draws):
            self._viewer(viewer)[model_name].browse(ids).unlink()
            self.log[-1] += f" -> {ids}"
            self._drop_dead_drafts()

    def _op_archive(self, model_name, draws, viewer, archive):
        if ids := self._pick(model_name, draws):
            records = self._viewer(viewer)[model_name].browse(ids)
            if archive:
                records.action_archive()
            else:
                records.action_unarchive()
            self.log[-1] += f" -> {ids}"

    def _op_read(self, model_name, draws, viewer, fname):
        ids = self._pick(model_name, draws) if draws else self._alive(model_name)
        records = self._viewer(viewer)[model_name].browse(ids)
        if len(records) > 1 and fname != "parent_path":
            records.read([fname])
        for record in records:
            _ = record[fname]

    def _op_invalidate(self, scope, model_name, draws, fname):
        match scope:
            case "all":
                self.env.invalidate_all()
            case "model":
                self.env[model_name].invalidate_model()
            case "recordset":
                ids = self._pick(model_name, draws)
                self.env[model_name].browse(ids).invalidate_recordset()
            case _:
                ids = self._pick(model_name, draws)
                self.env[model_name].browse(ids).invalidate_recordset([fname])

    def _ancestor(self, draw, levels):
        ids = self._pick(CATEGORY, (draw,))
        node = self.env[CATEGORY].with_context(active_test=False).browse(ids)
        for _level in range(levels):
            node = node.parent_id
        return node

    def _op_graft(self, draw, levels, viewer, payload):
        rng = random.Random(payload)
        Category = self._viewer(viewer)[CATEGORY]
        node = self._ancestor(draw, 0)
        if not node:
            node = Category.create({"name": rng.choice(NAMES), "code": "C"})
        depth = 0
        while node.parent_id:
            node, depth = node.parent_id, depth + 1
        if depth >= levels:
            return
        parent = False
        for _level in range(levels - depth):
            vals = {"name": rng.choice(NAMES), "code": rng.choice((*CODES, False))}
            parent = Category.create({**vals, "parent_id": parent}).id
        Category.browse(node.ids).write({"parent_id": parent})
        self.log[-1] += f" -> {node.id} under {parent}"

    def _op_uncache_ancestor(self, draw, levels, fname):
        if ancestor := self._ancestor(draw, levels):
            ancestor.invalidate_recordset([fname])
            self.log[-1] += f" -> {ancestor.id}"

    def _op_write_ancestor(self, draw, levels, viewer, payload):
        ancestor = self._ancestor(draw, levels)
        if not ancestor:
            return
        rng = random.Random(payload)
        fname = rng.choice(("code", "code", "name", "parent_id"))
        if fname == "parent_id":
            vals = {fname: self._parent_outside(rng, ancestor.ids)}
        else:
            pool = (*CODES, False) if fname == "code" else NAMES
            vals = {fname: rng.choice([v for v in pool if v != ancestor[fname]])}
        self.log[-1] += f" -> {ancestor.id} {vals}"
        self._viewer(viewer)[CATEGORY].browse(ancestor.ids).write(vals)

    def _op_flush(self):
        self.env.flush_all()

    def _op_savepoint(self, flush):
        if not flush:
            self.env.flush_all()
        self.savepoints.append((self.env.cr.savepoint(flush=flush), flush))

    def _op_close_savepoint(self, rollback):
        if not self.savepoints:
            return
        savepoint, flush = self.savepoints.pop()
        if flush:
            savepoint.close(rollback=rollback)
            return
        if rollback:
            self.env.flush_all()
        savepoint.close(rollback=rollback)
        if rollback:
            self.env.clear()

    def _op_caught_error(self, draw, viewer):
        ids = self._pick(LINE, (draw,))
        if not ids:
            return
        env = self._viewer(viewer)
        try:
            with self.env.cr.savepoint():
                env[LINE].browse(ids).write({"qty": -1})
                env.flush_all()
        except ValidationError:
            return
        raise AssertionError(
            f"line {ids} took a negative quantity without a ValidationError"
        )

    def _note_assigned(self, record, vals):
        origin = record._origin.id
        if not origin:
            return
        assigned = self.assigned.setdefault((record._name, origin), {})
        for fname, value in vals.items():
            key = record.env.get_cache_key(record._fields[fname])
            assigned.setdefault(fname, {})[key] = value

    def _op_draft(self, viewer, payload):
        env = self._viewer(viewer)
        rng = random.Random(payload)
        origin = (
            self._pick(ORDER, (rng.randrange(1 << 16),)) if rng.random() < 0.5 else []
        )
        Order = env[ORDER]
        vals = self._vals(rng, ORDER, ())
        before = self._dirty_values()
        draft = Order.new(vals, origin=Order.browse(origin) if origin else None)
        self.log[-1] += f" -> origin {origin} {vals}"
        self._note_assigned(draft, vals)
        if "line_ids" in vals:
            for other in self.drafts:
                self._note_assigned(other, {"line_ids": True})
        for command in vals.get("line_ids") or ():
            if isinstance(command, (list, tuple)) and command[0] == Command.UPDATE:
                line = env[LINE].browse(command[1])
                self._note_assigned(line, command[2])
        for fname in READABLE[ORDER]:
            _ = draft[fname]
        draft.line_ids.mapped("amount")
        if categories := self._pick(CATEGORY, (rng.randrange(1 << 16),)):
            draft.category_id = env[CATEGORY].browse(categories)
            self._note_assigned(draft, {"category_id": categories[0]})
            _ = draft.total, draft.category_name, draft.line_ids.mapped("amount")
        self._assert_no_leak(before)
        if origin:
            self.drafts = [*self.drafts[1 - LIVE_DRAFTS :], draft]

    def _drop_dead_drafts(self):
        alive = set(self.harness.alive_ids(ORDER))
        self.drafts = [draft for draft in self.drafts if draft._origin.id in alive]

    def _op_draft_edit(self, draw, payload):
        self._drop_dead_drafts()
        if not self.drafts:
            return
        draft = self.drafts[draw % len(self.drafts)]
        rng = random.Random(payload)
        before = self._dirty_values()
        twins = draft.line_ids.filtered(lambda line: line._origin)
        if twins and rng.random() < 0.5:
            twin = twins[rng.randrange(len(twins))]
            vals = {rng.choice(DRAFT_LINE_FIELDS): rng.randrange(5)}
            twin.update(vals)
            self._note_assigned(twin, vals)
            self.log[-1] += f" -> line twin of {twin._origin.id} {vals}"
        else:
            vals = {
                fname: value
                for fname, value in self._vals(rng, ORDER, (), nested=True).items()
                if fname in DRAFT_FIELDS
            }
            draft.update(vals)
            self._note_assigned(draft, vals)
            self.log[-1] += f" -> draft of {draft._origin.id} {vals}"
        _ = draft.total, draft.priority_label, draft.line_ids.mapped("amount")
        self._assert_no_leak(before)

    def _dirty_values(self):
        core = self.env.core
        found = {}
        pending = {
            (field, id_)
            for field in core.get_pending_fields()
            for id_ in core.get_pending_ids(field)
        }
        for field in list(core.iter_cached_fields()):
            dirty = [id_ for id_ in core.get_dirty(field) or () if isinstance(id_, int)]
            if not dirty:
                continue
            if field in self.env.registry.field_depends_context:
                slots = list(core.iter_context_caches(field))
            else:
                slots = [(None, core.get_field_data_or_none(field) or {})]
            for id_ in dirty:
                for key, slot in slots:
                    if id_ in slot:
                        found[field, id_, key] = repr(slot[id_])
        return found, pending

    def _assert_no_leak(self, before):
        before, pending = before
        after, _pending = self._dirty_values()
        was_dirty = {(field, id_) for field, id_, _key in before}
        if leaked := sorted(
            f"{field} of {id_}"
            for (field, id_, key), value in after.items()
            if (field, id_) not in pending
            and (
                ((field, id_, key) in before and before[field, id_, key] != value)
                or (field, id_) not in was_dirty
            )
        ):
            raise AssertionError(f"a draft wrote to saved records: {leaked}")

    def _op_company(self, write, draws, viewer, other, payload):
        ids = self._pick(ORDER, draws)
        if not ids:
            return
        company = self.companies[other]
        records = self._viewer(viewer)[ORDER].browse(ids).with_company(company)
        if records.env not in self.company_envs:
            self.company_envs.append(records.env)
        if write:
            rng = random.Random(payload)
            vals = (
                {"priority": rng.randrange(4)}
                if rng.random() < 0.6
                else {"fallback_tag_id": rng.choice([False, *self._alive(TAG)])}
            )
            self.log[-1] += f" {ids} under {company} {vals}"
            records.write(vals)
        for record in records:
            _ = record.priority, record.fallback_tag_id, record.priority_label

    def _op_company_rename(self, draws, viewer, other, payload):
        ids = self._pick(ORDER, draws)
        tags = self._alive(TAG)
        if not ids or not tags:
            return
        rng = random.Random(payload)
        tag = rng.choice(tags)
        company = self.companies[1 if other else 0]
        records = self._viewer(viewer)[ORDER].browse(ids).with_company(company)
        if records.env not in self.company_envs:
            self.company_envs.append(records.env)
        records.write({"fallback_tag_id": tag})
        for record in records:
            _ = record.priority_label
        name = f"renamed {rng.randrange(1000)}"
        self._viewer(viewer)[TAG].browse(tag).write({"name": name})
        self.log[-1] += f" {ids} under {company} name tag {tag}, renamed {name!r}"

    def _op_lookup(self, code, viewer):
        self._viewer(viewer)[CATEGORY]._get_category_id_by_code(code)

    def _op_check(self):
        pass


    def _vals(self, rng, model_name, ids, nested=False):
        vals = {}

        def maybe(probability):
            return rng.random() < probability

        def one(comodel):
            if comodel == CATEGORY and (found := self._category_by_code(rng)):
                return found
            alive = self._alive(comodel)
            return rng.choice(alive) if alive and maybe(0.85) else False

        match model_name:
            case "test_orm.coherence.category":
                if maybe(0.5):
                    vals["name"] = rng.choice(NAMES)
                if maybe(0.3):
                    vals["code"] = rng.choice((*CODES, False))
                if maybe(0.5):
                    vals["parent_id"] = self._parent_outside(rng, ids)
                if maybe(0.08):
                    vals["active"] = maybe(0.5)
                if maybe(0.15):
                    vals["properties_definition"] = self._definition(rng)
            case "test_orm.coherence.order":
                if maybe(0.4):
                    vals["name"] = rng.choice(NAMES)
                if maybe(0.4):
                    vals["category_id"] = one(CATEGORY)
                if maybe(0.2):
                    vals["priority"] = rng.randrange(4)
                if maybe(0.12):
                    vals["fallback_tag_id"] = one(TAG)
                if maybe(0.2):
                    vals["attributes"] = self._attributes(rng)
                if maybe(0.06):
                    vals["active"] = maybe(0.5)
                if not nested and maybe(0.5):
                    vals["line_ids"] = self._commands(rng, LINE)
                if not nested and maybe(0.35):
                    vals["tag_ids"] = self._commands(rng, TAG)
            case "test_orm.coherence.line":
                if not nested and maybe(0.5):
                    vals["order_id"] = one(ORDER)
                if maybe(0.6):
                    vals["qty"] = rng.randrange(5)
                if maybe(0.5):
                    vals["price"] = rng.randrange(5)
                if maybe(0.06):
                    vals["active"] = maybe(0.5)
            case "test_orm.coherence.tag":
                if maybe(0.5):
                    vals["name"] = rng.choice(NAMES)
                if maybe(0.4):
                    vals["label"] = rng.choice(LABELS)
                if maybe(0.06):
                    vals["active"] = maybe(0.5)
                if not nested and maybe(0.3):
                    vals["order_ids"] = self._commands(rng, ORDER)
            case "test_orm.coherence.item" | "test_orm.coherence.item.special":
                if maybe(0.4):
                    vals["name"] = rng.choice(NAMES)
                if maybe(0.6):
                    vals["weight"] = rng.randrange(9)
                if maybe(0.4):
                    vals["category_id"] = one(CATEGORY)
                if model_name == SPECIAL and maybe(0.5):
                    vals["extra"] = rng.randrange(6)
        return vals

    def _definition(self, rng):
        chosen = rng.sample(DEFINITIONS, rng.randrange(len(DEFINITIONS) + 1))
        return [dict(definition) for definition in chosen]

    def _property_value(self, rng, definition):
        match definition["type"]:
            case "integer":
                return rng.randrange(5)
            case "char":
                return rng.choice(NAMES)
            case "boolean":
                return rng.random() < 0.5
            case _:
                alive = self._alive(TAG)
                return rng.choice(alive) if alive and rng.random() < 0.8 else False

    def _attributes(self, rng):
        chosen = self._definition(rng)
        if rng.random() < 0.6:
            return {d["name"]: self._property_value(rng, d) for d in chosen}
        values = [{**d, "value": self._property_value(rng, d)} for d in chosen]
        if values and rng.random() < 0.5:
            values[0]["definition_changed"] = True
        return values

    def _category_by_code(self, rng):
        if rng.random() >= 0.4:
            return None
        found = self.env[CATEGORY]._get_category_id_by_code(rng.choice(CODES))
        return found if found and (CATEGORY, found) not in self.doomed else None

    def _parent_outside(self, rng, ids):
        alive = self._alive(CATEGORY)
        if not alive or rng.random() < 0.2:
            return False
        candidate = self._category_by_code(rng) or rng.choice(
            alive[-3:] if rng.random() < 0.6 else alive
        )
        node = self.env[CATEGORY].with_context(active_test=False).browse(candidate)
        while node:
            if node.id in ids:
                return False
            node = node.parent_id
        return candidate

    def _commands(self, rng, comodel):
        alive = self._alive(comodel)
        if alive and rng.random() < 0.1:
            return rng.sample(alive, min(len(alive), rng.randrange(1, 3)))
        if alive and rng.random() < 0.1:
            return [rng.choice(alive), self._vals(rng, comodel, (), nested=True)]
        commands = []
        for _ in range(rng.choice((1, 1, 2, 3))):
            code = rng.randrange(7)
            if code == 0 or (not alive and code not in (5, 6)):
                commands.append(
                    Command.create(self._vals(rng, comodel, (), nested=True))
                )
                continue
            match code:
                case 1:
                    vals = self._vals(rng, comodel, (), nested=True)
                    commands.append(Command.update(rng.choice(alive), vals))
                case 2:
                    doomed = rng.choice(alive)
                    self.doomed.add((comodel, doomed))
                    alive = [id_ for id_ in alive if id_ != doomed]
                    commands.append(Command.delete(doomed))
                case 3:
                    commands.append(Command.unlink(rng.choice(alive)))
                case 4:
                    commands.append(Command.link(rng.choice(alive)))
                case 5:
                    commands.append(Command.clear())
                case _:
                    chosen = (
                        rng.sample(alive, rng.randrange(len(alive) + 1))
                        if alive
                        else []
                    )
                    commands.append(Command.set(chosen))
        return commands


    def check(self):
        try:
            self.env.flush_all()
        except Exception as exc:
            return self._failure(("raised", "flush", type(exc).__name__), exc)
        for name, check in (
            ("cache", self._check_cache),
            ("recompute", self._check_recompute),
            ("ormcache", self._check_ormcache),
            ("properties", self._check_properties),
            ("drafts", self._check_drafts),
        ):
            try:
                found = check()
            except Exception as exc:
                return self._failure(
                    ("raised", f"check_{name}", type(exc).__name__), exc
                )
            if found:
                signature, details = found
                return Failure(signature, "\n".join(details))
        return None

    def _slots(self, field):
        core = self.env.core
        if field in self.env.registry.field_depends_context:
            for key, slot in list(core.iter_context_caches(field)):
                viewer = next(
                    (
                        v
                        for v in (*self.viewers, *self.company_envs)
                        if v.get_cache_key(field) == key
                    ),
                    None,
                )
                if viewer is not None:
                    yield viewer, key, slot
        elif (slot := core.get_field_data_or_none(field)) is not None:
            yield self.env, None, slot

    def _check_cache(self):
        mismatches = []
        signature = None
        alive = {
            model_name: set(self.harness.alive_ids(model_name)) for model_name in MODELS
        }
        with self.harness.fresh() as fresh:
            for field in list(self.env.core.iter_cached_fields()):
                if field.model_name not in MODELS:
                    continue
                for viewer, key, slot in list(self._slots(field)):
                    held = {
                        id_: value
                        for id_, value in slot.items()
                        if isinstance(id_, int) and value is not PENDING
                    }
                    if not held:
                        continue
                    env = fresh(viewer)
                    for id_, value in sorted(held.items()):
                        if id_ not in alive[field.model_name]:
                            mismatches.append(
                                f"{field} caches {value!r} for deleted record {id_} ({key})"
                            )
                            signature = signature or (
                                "deleted",
                                field.model_name,
                                field.name,
                            )
                            continue
                        truth = _fresh_value(env, field, id_)
                        self.compared["cache"] += 1
                        if not _same(field, value, truth):
                            mismatches.append(
                                f"{field} of {id_} under {key}: cached {value!r}, fresh {truth!r}"
                            )
                            signature = signature or (
                                "cache",
                                field.model_name,
                                field.name,
                            )
        return (signature, mismatches) if mismatches else None

    def _check_recompute(self):
        mismatches = []
        signature = None
        with self.harness.fresh() as fresh:
            env = fresh(self.env)
            computed = []
            for model_name in MODELS:
                ids = sorted(self.harness.alive_ids(model_name))
                records = env[model_name].browse(ids)
                for field in records._fields.values():
                    if (
                        field.store
                        and field.compute
                        and field.model_name == model_name
                        and field.type != "properties"
                    ):
                        stored = {
                            record.id: _fresh_value(env, field, record.id)
                            for record in records
                        }
                        computed.append((field, records, stored))
            categories = env[CATEGORY].browse(sorted(self.harness.alive_ids(CATEGORY)))
            for category in categories:
                chain, node = [], category
                while node:
                    chain.append(node.id)
                    node = node.parent_id
                expected = "".join(f"{id_}/" for id_ in reversed(chain))
                if category.parent_path != expected:
                    mismatches.append(
                        f"parent_path of {category.id} is {category.parent_path!r}, its parents spell {expected!r}"
                    )
                    signature = signature or ("parent_path", CATEGORY, "parent_path")
            negative = (
                env[LINE]
                .browse(sorted(self.harness.alive_ids(LINE)))
                .filtered(lambda line: line.qty < 0)
            )
            if negative:
                mismatches.append(f"lines {negative.ids} hold a negative quantity")
                signature = signature or ("constraint", LINE, "qty")
            for field, records, _stored in computed:
                env.add_to_compute(field, records)
            for field, records, stored in computed:
                for record in records:
                    value = _fresh_value(env, field, record.id)
                    self.compared["recompute"] += 1
                    if not _same(field, stored[record.id], value):
                        mismatches.append(
                            f"{field} of {record.id}: stored {stored[record.id]!r}, recomputed {value!r}"
                        )
                        signature = signature or (
                            "recompute",
                            field.model_name,
                            field.name,
                        )
        return (signature, mismatches) if mismatches else None

    def _check_properties(self):
        mismatches = []
        ids = sorted(self.harness.alive_ids(ORDER))
        with self.harness.fresh() as fresh:
            for viewer in (self.env, self.viewers[1]):
                held = viewer[ORDER].browse(ids).read(["attributes"])
                truth = fresh(viewer)[ORDER].browse(ids).read(["attributes"])
                self.compared["properties"] += len(ids)
                for mine, theirs in zip(held, truth, strict=True):
                    if mine != theirs:
                        mismatches.append(
                            f"attributes of {mine['id']} read {mine['attributes']!r}, "
                            f"fresh {theirs['attributes']!r}"
                        )
        return (("properties", ORDER, "attributes"), mismatches) if mismatches else None

    def _twin_value(self, record, fname):
        by_key = self.assigned.get((record._name, record.id), {}).get(fname)
        return next(iter(by_key.values())) if by_key else record[fname]

    def _check_drafts(self):
        mismatches = []
        self._drop_dead_drafts()

        def plain(value):
            return (value._origin.id or False) if hasattr(value, "_ids") else value

        for draft in self.drafts:
            origin = draft._origin
            pairs = [(draft, origin, DRAFT_FIELDS)]
            held = sorted(line._origin.id or 0 for line in draft.line_ids)
            truth = sorted(origin.line_ids.ids)
            shown = sorted(
                line.id
                for line in origin.with_context(active_test=False).line_ids
                if self._twin_value(line, "active")
            )
            self.compared["drafts"] += 1
            if held not in (truth, shown) and "line_ids" not in self.assigned.get(
                (ORDER, origin.id), {}
            ):
                mismatches.append(
                    f"draft of order {origin.id} lists lines {held}, its origin {truth}"
                )
            pairs.extend(
                (line, line._origin, DRAFT_LINE_FIELDS)
                for line in draft.line_ids
                if line._origin
            )
            for record, saved, fnames in pairs:
                assigned = self.assigned.get((saved._name, saved.id), {})
                for fname in fnames:
                    key = record.env.get_cache_key(record._fields[fname])
                    allowed = [plain(saved[fname])]
                    if key in (by_key := assigned.get(fname, {})):
                        allowed.append(plain(by_key[key]))
                    value = plain(record[fname])
                    self.compared["drafts"] += 1
                    if not any(value == ok or not (value or ok) for ok in allowed):
                        mismatches.append(
                            f"{fname} of the draft of {saved} reads {value!r}, "
                            f"its origin holds {allowed[0]!r}"
                            + (
                                f", it was assigned {allowed[1]!r}"
                                if allowed[1:]
                                else ""
                            )
                        )
        return (("drafts", ORDER, "twin"), mismatches) if mismatches else None

    def _check_ormcache(self):
        mismatches = []
        with self.harness.fresh() as fresh:
            env = fresh(self.env)
            for code in CODES:
                held = self.env[CATEGORY]._get_category_id_by_code(code)
                self.compared["ormcache"] += 1
                found = (
                    env[CATEGORY]
                    .with_context(active_test=False)
                    .search([("code", "=", code)], order="id", limit=1)
                )
                if held != (found.id or None):
                    mismatches.append(
                        f"the lookup of {code!r} answers {held}, a search {found.id or None}"
                    )
        return (
            (("ormcache", CATEGORY, "_get_category_id_by_code"), mismatches)
            if mismatches
            else None
        )


def _fresh_value(env, field, id_):
    record = env[field.model_name].browse(id_)
    _ = record[field.name]
    core = env.core
    if field in env.registry.field_depends_context:
        slot = core.get_context_data_or_none(field, env.get_cache_key(field))
    else:
        slot = core.get_field_data_or_none(field)
    return slot[id_]


def _same(field, held, truth):
    if field.type in ("one2many", "many2many"):
        return set(held) == set(truth)
    return held == truth or (not held and not truth)


def shrink(ops, reproduces):
    granularity = 2
    while len(ops) >= 2:
        chunk = -(-len(ops) // granularity)
        for start in range(0, len(ops), chunk):
            complement = ops[:start] + ops[start + chunk :]
            if reproduces(complement):
                ops = complement
                granularity = max(granularity - 1, 2)
                break
        else:
            if granularity >= len(ops):
                break
            granularity = min(len(ops), granularity * 2)
    return ops


def explore(run, seed, steps):
    ops = generate(seed, steps)
    failure, _log = run(ops)
    if failure is None:
        return None

    def reproduces(candidate):
        found, _ = run(candidate)
        return found is not None and found.signature == failure.signature

    minimal = shrink(ops, reproduces)
    final, log = run(minimal)
    final = final or failure
    return (
        f"seed {seed} ({steps} steps) breaks {final.signature}; "
        f"shrunk from {len(ops)} to {len(minimal)} operations:\n  "
        + "\n  ".join(log)
        + f"\n{final.detail}"
    )


@contextmanager
def no_savepoints_left(walk):
    try:
        yield walk
    finally:
        while walk.savepoints:
            savepoint, _flush = walk.savepoints.pop()
            savepoint.close(rollback=True)
