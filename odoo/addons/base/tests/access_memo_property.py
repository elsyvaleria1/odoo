import os
import random
import traceback
import typing
from contextlib import contextmanager
from dataclasses import dataclass, field

from odoo import Command
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.libs.lru import LRU
from odoo.orm.domain import Domain
from odoo.orm.runtime.transaction import Transaction

LONG = int(os.environ.get("ACCESS_MEMO_PROPERTY_STEPS", "0"))
SEEDS = int(os.environ.get("ACCESS_MEMO_PROPERTY_SEEDS", "0"))
LANGS = ("en_US", "fr_FR")
WORDS = ("alpha", "beta", "gamma", "delta")
OPERATIONS = ("read", "write", "unlink")
CANDIDATES = 6

type Mutation = tuple[typing.Any, ...]


@dataclass
class World:
    env: typing.Any
    names: dict[str, str]
    note_class: typing.Any
    companies: typing.Any
    groups: typing.Any
    everyone: typing.Any
    users: typing.Any
    contacts: typing.Any
    company_partners: typing.Any
    sql: bool
    handles: dict[str, list[int]] = field(default_factory=dict)
    rows: list[int] = field(default_factory=list)
    grants: list[int] = field(default_factory=list)

    def model(self, role: str, env: typing.Any = None) -> typing.Any:
        return (env or self.env)[self.names[role]]

    def bound(self, name: str) -> typing.Any:
        return getattr(self, name).with_env(self.env)

    def record(self, role: str, index: int) -> typing.Any:
        ids = self.handles[role]
        if not ids:
            return None
        record = self.model(role).browse(ids[index % len(ids)])
        return record if record.exists() else None

    def ids(self, role: str, indexes: typing.Iterable[int]) -> list[int]:
        found = []
        for index in indexes:
            record = self.record(role, index)
            if record is not None and record.id not in found:
                found.append(record.id)
        return found


def _french(word: str) -> str:
    return WORDS[(WORDS.index(word) + 1) % len(WORDS)]


def create_world(env, names: dict[str, str], note_class: str, *, sql: bool) -> World:
    if not env["res.lang"]._activate_lang("fr_FR"):
        env["res.lang"]._create_lang("fr_FR")
    company_a = env.company
    company_b = env["res.company"].create({"name": "Memo property B"})
    companies = company_a | company_b
    groups = env["res.groups"].create(
        [{"name": f"memo property {i}"} for i in range(3)]
    )
    everyone = env.ref("base.group_everyone", raise_if_not_found=False) or env[
        "res.groups"
    ].create({"name": "memo property everyone"})
    company_partners = env["res.partner"].create(
        [{"name": f"memo property firm {i}", "is_company": True} for i in range(2)]
    )
    users = env["res.users"]
    for i in range(3):
        users |= env["res.users"].create(
            {
                "name": f"memo property user {i}",
                "login": f"memo_property_user_{i}",
                "company_id": company_a.id,
                "company_ids": [Command.set(companies.ids if i < 2 else company_a.ids)],
                "group_ids": [
                    Command.link(groups[0].id),
                    *([Command.link(groups[1 + i].id)] if i < 2 else []),
                ],
            }
        )
    users[0].partner_id.parent_id = company_partners[0]
    contacts = env["res.partner"].create(
        [
            {"name": "memo property contact 0", "parent_id": company_partners[0].id},
            {"name": "memo property contact 1", "parent_id": company_partners[1].id},
            {"name": "memo property contact 2"},
        ]
    )
    world = World(
        env=env,
        names=names,
        note_class=env["ir.access.class"].search([("name", "=", note_class)])
        or env["ir.access.class"].create({"name": note_class}),
        companies=companies,
        groups=groups,
        everyone=everyone,
        users=users,
        contacts=contacts | users.partner_id,
        company_partners=company_partners,
        sql=sql,
    )
    folders = world.model("folder")
    root = folders.create({"name": "root", "company_id": company_a.id})
    folder_a = folders.create({"name": "a", "parent_id": root.id})
    folder_b = folders.create(
        {"name": "b", "parent_id": root.id, "company_id": company_b.id}
    )
    leaves = folders.create(
        [
            {"name": "a1", "parent_id": folder_a.id, "manager_id": users[0].id},
            {"name": "a2", "parent_id": folder_a.id},
            {"name": "b1", "parent_id": folder_b.id, "manager_id": users[1].id},
        ]
    )
    tags = world.model("tag").create(
        [{"name": f"tag {i}", "color": i} for i in range(3)]
    )
    all_folders = root | folder_a | folder_b | leaves
    docs = world.model("doc").create(
        [
            {
                "name": WORDS[i % 4],
                "level": i % 5,
                "state": ("draft", "open", "done")[i % 3],
                "folder_id": all_folders[i % 6].id,
                "owner_id": users[i % 3].id,
                "partner_id": world.contacts[i % len(world.contacts)].id,
                "company_id": companies[i % 2].id if i % 3 else False,
                "tag_ids": [Command.link(tags[i % 3].id)],
                "note": f"note {i}",
            }
            for i in range(8)
        ]
    )
    for doc in docs:
        doc.with_context(lang="fr_FR").name = _french(doc.name)
    lines = world.model("line").create(
        [
            {
                "doc_id": docs[i % 8].id,
                "amount": i % 5,
                "kind": ("open", "closed")[i % 2],
                "owner_id": users[i % 3].id,
                "label": WORDS[i % 4],
            }
            for i in range(12)
        ]
    )
    for line in lines[::2]:
        line.with_context(lang="fr_FR").label = _french(line.label)
    world.handles = {
        "folder": all_folders.ids,
        "tag": tags.ids,
        "doc": docs.ids,
        "line": lines.ids,
    }
    access = env["ir.access"].sudo()
    access.search([("model_id.model", "in", list(names.values()))]).unlink()
    for role, kind in SLOTS:
        target = (
            {"class_id": world.note_class.id}
            if role == "note"
            else {"model_id": env["ir.model"]._get_id(names[role])}
        )
        world.rows.append(
            access.create(
                {
                    "name": f"memo property {role} {kind}",
                    "kind": kind,
                    "group_id": (groups[0] if kind == "permission" else everyone).id,
                    "operation": "ru" if role == "note" else "crud",
                    "active": kind == "permission",
                    **target,
                }
            ).id
        )
    env.flush_all()
    return world


LEAVES = {
    "doc": (
        ("plain", "[('level', '>=', {n})]"),
        ("plain", "[('state', '=', '{state}')]"),
        ("owner", "[('owner_id', '=', user.id)]"),
        ("company", "[('company_id', 'in', company_ids)]"),
        (
            "company",
            "['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ),
        ("hierarchy", "[('folder_id', 'child_of', [{folder}])]"),
        ("hierarchy", "[('folder_id', 'parent_of', [{folder}])]"),
        ("hierarchy", "[('folder_id.parent_id', '=', {folder})]"),
        ("path", "[('folder_id.manager_id', '=', user.id)]"),
        ("path", "[('folder_id.company_id', 'in', company_ids + [False])]"),
        ("path", "[('folder_id.active', '=', True)]"),
        ("x2many", "[('line_ids', 'any', [('amount', '>', {n})])]"),
        ("x2many", "[('line_ids', 'not any', [('kind', '=', 'closed')])]"),
        ("x2many", "[('open_line_ids.owner_id', '=', user.id)]"),
        ("m2m", "[('tag_ids', 'in', [{tag}])]"),
        ("m2m", "[('tag_ids.color', '=', {color})]"),
        ("compute", "[('total', '>', {double})]"),
        ("translated", "[('name', 'ilike', '{word}')]"),
        (
            "partner",
            "[('partner_id', 'child_of', [user.partner_id.commercial_partner_id.id])]",
        ),
    ),
    "line": (
        ("plain", "[('amount', '>=', {n})]"),
        ("plain", "[('kind', '=', '{kind}')]"),
        ("owner", "[('owner_id', '=', user.id)]"),
        ("path", "[('doc_id.level', '>=', {n})]"),
        ("active", "[('active', '=', True)]"),
        ("company", "[('doc_id.company_id', 'in', company_ids + [False])]"),
        ("translated", "[('label', 'ilike', '{word}')]"),
    ),
    "folder": (
        ("company", "[('company_id', 'in', company_ids + [False])]"),
        ("owner", "[('manager_id', '=', user.id)]"),
        ("hierarchy", "[('id', 'child_of', [{folder}])]"),
        ("active", "[('active', '=', True)]"),
    ),
    "tag": (("plain", "[('color', '<', {low})]"),),
}
REACHES = {
    "own": "owner",
    "company": "company",
    "partner": "partner",
    "own_partner": "partner",
}


THEMES = (
    *sorted({hazard for leaves in LEAVES.values() for hazard, _text in leaves}),
    "bypass",
)


def _hazards(role: str) -> list[str]:
    if role == "note":
        return sorted(set(REACHES.values()))
    return sorted({hazard for hazard, _template in LEAVES[role]})


def _leaf(
    rng: random.Random, world: World, role: str, hazard: str | None = None
) -> str:
    hazard = hazard or rng.choice(_hazards(role))
    template = rng.choice([text for name, text in LEAVES[role] if name == hazard])
    n = rng.randrange(5)
    return template.format(
        n=n,
        double=n * 2,
        low=rng.randrange(1, 4),
        color=n % 3,
        state=rng.choice(["draft", "open", "done"]),
        kind=rng.choice(["open", "closed"]),
        word=rng.choice(WORDS),
        folder=rng.choice(world.handles["folder"]),
        tag=rng.choice(world.handles["tag"]),
    )


def _domain(rng: random.Random, world: World, role: str, depth: int = 0) -> str:
    if depth > 1 or rng.random() < 0.75:
        return _leaf(rng, world, role)
    operator = rng.choices(["&", "|", "!"], [1, 2, 1])[0]
    if operator == "!":
        return f"['!'] + {_domain(rng, world, role, depth + 1)}"
    left = _domain(rng, world, role, depth + 1)
    return f"['{operator}'] + {left} + {_domain(rng, world, role, depth + 1)}"


SLOTS = (
    ("doc", "permission"),
    ("doc", "permission"),
    ("doc", "guard"),
    ("line", "permission"),
    ("line", "guard"),
    ("folder", "permission"),
    ("tag", "permission"),
    ("note", "permission"),
    ("note", "guard"),
)


def _row_spec(rng: random.Random, world: World, role: str, kind: str) -> dict:
    spec: dict[str, typing.Any] = {
        "role": role,
        "kind": kind,
        "group": rng.choices(range(3), [4, 1, 1])[0],
        "operation": "".join(
            letter
            for letter, odds in (("c", 0.3), ("r", 1.0), ("u", 0.5), ("d", 0.3))
            if rng.random() < odds
        ),
        "active": kind == "permission" or rng.random() < 0.4,
    }
    if kind == "guard":
        spec["scope"] = rng.choice(["everyone", "members"])
    if role == "note":
        spec["operation"] = rng.choice(["r", "ru"])
        reaches = ["own", "company", "partner", "own_partner"]
        spec["reach"] = rng.choice([*reaches, "" if kind == "permission" else "none"])
        return spec
    if role in ("doc", "line") and rng.random() < 0.3:
        reaches = ["own", "partner", "own_partner"]
        spec["reach"] = rng.choice([*reaches, "company"] if role == "doc" else reaches)
        if rng.random() < 0.3:
            n = rng.randrange(1, 5)
            spec["domain"] = rng.choice(
                [
                    f"[('level', '<', {n})]",
                    "[('state', '!=', 'done')]",
                    f"[('total', '<=', {n * 2})]",
                ]
                if role == "doc"
                else [f"[('amount', '<', {n})]", "[('kind', '=', 'open')]"]
            )
        return spec
    spec["domain"] = _domain(rng, world, role)
    return spec


def _value(rng: random.Random, world: World, role: str, fname: str) -> typing.Any:
    n = rng.randrange(5)
    match fname:
        case "level" | "amount":
            return n
        case "color":
            return n % 3
        case "state":
            return rng.choice(["draft", "open", "done"])
        case "kind":
            return rng.choice(["open", "closed"])
        case "active":
            return rng.random() < 0.6
        case "name" | "label":
            return rng.choice(WORDS)
        case "note":
            return f"note {n}"
        case "owner_id" | "manager_id":
            return rng.choice([False, *world.users.ids])
        case "partner_id":
            return rng.choice([False, *world.contacts.ids])
        case "company_id":
            return rng.choice([False, *world.companies.ids])
        case "folder_id" | "parent_id":
            return ("ref", "folder", rng.randrange(8)) if n else False
        case "doc_id":
            return ("ref", "doc", rng.randrange(12))
    raise ValueError(fname)


TRANSLATED = {"doc": "name", "line": "label"}
WRITABLE = {
    "doc": (
        "level",
        "state",
        "active",
        "name",
        "owner_id",
        "partner_id",
        "company_id",
        "folder_id",
        "note",
    ),
    "line": ("amount", "kind", "active", "owner_id", "doc_id", "label"),
    "folder": ("parent_id", "active", "company_id", "manager_id"),
    "tag": ("color", "active"),
}
BYPASSABLE = {
    "cache": {
        "doc": ("level", "state", "owner_id", "company_id"),
        "line": ("owner_id", "amount"),
        "folder": ("manager_id", "company_id"),
        "tag": ("color",),
    },
    "raw": {
        "doc": ("level", "state", "owner_id", "company_id"),
        "line": ("owner_id", "amount", "doc_id"),
        "folder": ("manager_id", "company_id"),
        "tag": ("color",),
    },
}


def _write_modes(role: str | None, fname: str, bypass: bool = False) -> list[str]:
    bypassing = [
        mode
        for mode, by_role in BYPASSABLE.items()
        if fname in by_role.get(role or "", ())
    ]
    return bypassing if bypass and bypassing else ["write", *bypassing]


def _prepare_mutation(
    rng: random.Random, world: World, depth: int = 0, focus: tuple | None = None
) -> Mutation:
    kind = rng.choices(
        [
            "write",
            "write_lang",
            "create",
            "unlink",
            "lines",
            "tags",
            "membership",
            "grant",
            "rule_create",
            "rule_write",
            "rule_unlink",
            "partner_parent",
            "cache_write",
            "raw_write",
            "savepoint",
            "flush",
        ],
        [30, 4, 6, 4, 6, 5, 5, 3, 3, 8, 2, 3, 4, 4, 2, 2],
    )[0]
    i = rng.randrange(16)
    aimed = focus is not None and rng.random() < 0.7
    if aimed:
        i = rng.choice(focus[4])
    match kind:
        case "write":
            role = rng.choices(["doc", "line", "folder", "tag"], [6, 4, 3, 1])[0]
            if aimed and focus[3] in WRITABLE:
                role = focus[3]
            fname = rng.choice(WRITABLE[role])
            return (kind, role, i, fname, _value(rng, world, role, fname))
        case "write_lang":
            role = rng.choice(["doc", "line"])
            if aimed and focus[3] == "line":
                role = "line"
            return (kind, role, i, rng.choice(LANGS), rng.choice(WORDS))
        case "create":
            return _prepare_create_mutation(rng, world)
        case "unlink":
            return (kind, rng.choices(["doc", "line", "folder"], [2, 4, 1])[0], i)
        case "lines":
            return (
                kind,
                i,
                rng.choice(["create", "delete", "unlink", "link"]),
                rng.randrange(16),
                rng.randrange(5),
            )
        case "tags":
            return (kind, i, rng.choice(["link", "unlink", "set"]), rng.randrange(3))
        case "membership":
            return (kind, rng.randrange(3), rng.randrange(3), rng.random() < 0.5)
        case "grant":
            if world.grants and rng.random() < 0.4:
                return ("ungrant", i)
            return (kind, rng.randrange(3), rng.randrange(1, 3), rng.randrange(2))
        case "rule_create":
            role = rng.choice(["doc", "doc", "line", "folder", "note"])
            kind_of_row = rng.choice(["permission", "guard"])
            return (kind, {**_row_spec(rng, world, role, kind_of_row), "active": True})
        case "rule_write":
            slot = rng.randrange(len(SLOTS))
            return (kind, slot, _row_spec(rng, world, *SLOTS[slot]), rng.random() < 0.3)
        case "rule_unlink":
            return (kind, i)
        case "partner_parent":
            return (kind, rng.randrange(len(world.contacts)), rng.randrange(3))
        case "cache_write":
            role = rng.choice(list(BYPASSABLE["cache"]))
            fname = rng.choice(BYPASSABLE["cache"][role])
            return (kind, role, i, fname, _value(rng, world, role, fname))
        case "raw_write":
            role = rng.choice(list(BYPASSABLE["raw"]))
            fname = rng.choice(BYPASSABLE["raw"][role])
            value = _value(rng, world, role, fname)
            return (kind, role, i, fname, value, rng.random() < 0.5)
        case "savepoint" if depth == 0:
            inner = tuple(
                _prepare_mutation(rng, world, 1) for _i in range(rng.randrange(1, 4))
            )
            return (
                kind,
                inner,
                tuple(_prepare_observation(rng) for _i in range(rng.randrange(2))),
            )
    return ("flush",)


def _prepare_create_mutation(rng: random.Random, world: World) -> Mutation:
    role = rng.choice(["doc", "line", "folder"])
    values = {
        fname: _value(rng, world, role, fname)
        for fname in WRITABLE[role]
        if rng.random() < 0.6
    }
    if role == "line":
        values.setdefault("doc_id", _value(rng, world, role, "doc_id"))
    return ("create", role, values)


def _principal(rng: random.Random) -> tuple:
    return (
        rng.randrange(3),
        rng.choice(["A", "B", "AB", "BA", ""]),
        rng.choice(LANGS),
        rng.choice([None, None, 0, 1, 2, 3]),
        rng.random() < 0.85,
    )


def _prepare_observation(rng: random.Random) -> Mutation:
    kind = rng.choices(
        [
            "has_access",
            "filtered",
            "check",
            "search",
            "read",
            "x2many",
            "web_read",
            "read_group",
            "masked",
            "display",
        ],
        [10, 6, 3, 5, 5, 8, 2, 2, 4, 2],
    )[0]
    role = rng.choices(["doc", "line", "folder", "tag"], [6, 3, 2, 1])[0]
    indexes = tuple(rng.randrange(16) for _i in range(rng.randrange(1, 6)))
    match kind:
        case "has_access" | "filtered" | "check":
            detail: typing.Any = rng.choices(OPERATIONS, [6, 1, 1])[0]
        case "search":
            detail = rng.choice([None, "level", "name", "tree"])
        case "x2many":
            role, detail = "doc", rng.choice(["line_ids", "open_line_ids", "tag_ids"])
        case "read":
            detail = None
        case "web_read" | "masked":
            role, detail = "doc", None
        case _:
            detail = None
    return ("observe", _principal(rng), kind, role, indexes, detail)


REACH_READS = {
    "own": "'owner_id'",
    "own_partner": "'partner_id' partner",
    "partner": "'partner_id' partner child_of",
    "company": "'company_id' company_ids",
}


def _spec_texts(specs: typing.Iterable[dict]) -> list[str]:
    return [
        f"{spec.get('domain') or ''} {REACH_READS.get(spec.get('reach') or '', '')}"
        for spec in specs
    ]


def _fact_mutation(
    rng: random.Random,
    world: World,
    texts: list[str],
    focus: tuple,
    bypass: bool = False,
) -> tuple:
    text = " ".join(texts)
    i = rng.choice(focus[4]) if rng.random() < 0.7 else rng.randrange(16)
    options: list[tuple] = []
    for role, fnames in WRITABLE.items():
        for fname in fnames:
            if f"'{fname}'" in text or f".{fname}'" in text or f"'{fname}." in text:
                index = i if role == focus[3] else rng.randrange(16)
                options.append(
                    ("write", role, index, fname, _value(rng, world, role, fname))
                )
    if "total" in text or "line_ids" in text:
        options += [
            ("write", "line", rng.randrange(16), "amount", rng.randrange(5)),
            ("write", "line", rng.randrange(16), "doc_id", ("ref", "doc", i)),
            ("write", "line", rng.randrange(16), "active", rng.random() < 0.5),
            (
                "lines",
                i,
                rng.choice(["create", "delete", "unlink"]),
                rng.randrange(16),
                rng.randrange(5),
            ),
        ]
    if "tag_ids" in text:
        options.append(
            ("tags", i, rng.choice(["link", "unlink", "set"]), rng.randrange(3))
        )
    for role, fname in TRANSLATED.items():
        if f"'{fname}'" in text:
            index = i if role == focus[3] else rng.randrange(16)
            options.append(
                ("write_lang", role, index, rng.choice(LANGS), rng.choice(WORDS))
            )
    if "child_of" in text or "parent_of" in text or "parent_id" in text:
        options += [
            (
                "write",
                "folder",
                rng.randrange(8),
                "parent_id",
                _value(rng, world, "folder", "parent_id"),
            ),
            ("write", "doc", i, "folder_id", _value(rng, world, "doc", "folder_id")),
        ]
    if "partner" in text:
        options.append(
            ("partner_parent", rng.randrange(len(world.contacts)), rng.randrange(3))
        )
    if focus[3] == "doc":
        options += _via_options(rng, world, text, i, bypass) * 3
    if not options:
        return _prepare_mutation(rng, world, focus=focus)
    op = rng.choice(options)
    if op[0] == "write":
        mode = rng.choice(_write_modes(op[1], op[3], bypass))
        if mode == "cache":
            return ("cache_write", *op[1:])
        if mode == "raw":
            return ("raw_write", *op[1:], rng.random() < 0.5)
    return op


VIA = (
    (("child_of", "parent_of", "folder_id.parent_id"), "folder_id", ("parent_id",)),
    (
        ("child_of", "parent_of", "folder_id.parent_id"),
        "folder_id.parent_id",
        ("parent_id",),
    ),
    (("folder_id.manager_id",), "folder_id", ("manager_id",)),
    (("folder_id.company_id",), "folder_id", ("company_id",)),
    (("folder_id.active",), "folder_id", ("active",)),
    (("total", "'amount'"), "line_ids", ("amount", "active", "doc_id")),
    (("'kind'", "not any"), "line_ids", ("kind", "active", "doc_id")),
    (("owner_id",), "line_ids", ("owner_id", "kind", "active")),
    (("'label'",), "line_ids", ("label",)),
    (("'active'",), "line_ids", ("active",)),
    (("tag_ids.color",), "tag_ids", ("color", "active")),
    (("tag_ids",), "tag_ids", ("active",)),
    (("partner",), "partner_id", ("parent_id",)),
)
VIA_ROLE = {
    "folder_id": "folder",
    "folder_id.parent_id": "folder",
    "line_ids": "line",
    "tag_ids": "tag",
}


def _via_options(
    rng: random.Random, world: World, text: str, i: int, bypass: bool = False
) -> list[tuple]:
    options = []
    for words, path, fnames in VIA:
        if not any(word in text for word in words):
            continue
        fname = rng.choice(fnames)
        role = VIA_ROLE.get(path)
        if path == "partner_id":
            value: typing.Any = rng.choice([False, *world.company_partners.ids])
        else:
            value = _value(rng, world, role, fname)
        mode = rng.choice(_write_modes(role, fname, bypass))
        options.append(("write_via", i, path, rng.randrange(4), fname, value, mode))
    return options


def _memoized(check: tuple) -> bool:
    if check[2] in ("has_access", "filtered", "check"):
        return check[5] == "read"
    return check[2] not in ("search", "read_group")


def _focus_role(check: tuple) -> str:
    if check[2] == "masked":
        return "note"
    if check[2] == "x2many":
        return "tag" if check[5] == "tag_ids" else "line"
    return check[3]


def _focus_rule(
    rng: random.Random, world: World, check: tuple, theme: str | None = None
) -> tuple[list[tuple], str]:
    role = _focus_role(check)
    hazard = theme if theme in _hazards(role) else rng.choice(_hazards(role))
    spec = _row_spec(rng, world, role, "permission")
    spec.update(group=0, operation="ru" if role == "note" else "crud")
    spec.pop("domain", None)
    spec.pop("reach", None)
    reaches = [reach for reach, read in REACHES.items() if read == hazard]
    if role == "line":
        reaches = [reach for reach in reaches if reach != "company"]
    if role == "note" or (role in ("doc", "line") and reaches and rng.random() < 0.4):
        spec["reach"] = rng.choice(reaches)
    else:
        spec["domain"] = _leaf(rng, world, role, hazard)
    slot = SLOTS.index((role, "permission"))
    ops = [("rule_write", slot, spec, False)]
    if check[2] == "x2many":
        everything = {**_row_spec(rng, world, "doc", "permission"), "group": 0}
        everything.update(operation="crud", domain=False, reach=False)
        ops.append(
            ("rule_write", SLOTS.index(("doc", "permission")), everything, False)
        )
    for other, (other_role, kind) in enumerate(SLOTS):
        if other == slot or other_role != role:
            continue
        if kind == "permission" or rng.random() < 0.7:
            idle = {**_row_spec(rng, world, role, kind), "active": False}
            ops.append(("rule_write", other, idle, False))
    return ops, hazard


SCOPE_EPISODES = 0.15
SCOPE_HAZARDS = ("owner", "plain")


VARIED = {"owner": 0, "company": 1, "translated": 2, "partner": 3, "active": 4}


def _vary(rng: random.Random, check: tuple, hazard: str | None) -> tuple:
    slot = VARIED.get(hazard or "", rng.randrange(5))
    if rng.random() < 0.3:
        slot = rng.randrange(5)
    principal = list(check[1])
    while principal[slot] == check[1][slot]:
        principal[slot] = _principal(rng)[slot]
    return (check[0], tuple(principal), *check[2:])


def _differing(world: World, check: tuple, variations: list[tuple]) -> tuple | None:
    ids = world.ids(check[3], check[4])
    with _in_scratch(world):
        answers = {
            variation: observe(
                principal_env(world, variation[1]),
                world,
                *variation[2:4],
                ids,
                check[5],
            )
            for variation in (check, *variations)
        }
    return next((v for v in variations if answers[v] != answers[check]), None)


def _resolve(world: World, value: typing.Any) -> typing.Any:
    if isinstance(value, tuple) and value and value[0] == "ref":
        record = world.record(value[1], value[2])
        return record.id if record is not None else False
    return value


def _update_world(world: World, op: Mutation) -> None:
    env = world.env
    kind = op[0]
    handler = _WORLD_MUTATION_HANDLERS.get(kind)
    if handler is not None:
        handler(world, op, env)
        return
    match kind:
        case "savepoint":
            try:
                with env.cr.savepoint():
                    for inner in op[1]:
                        _update_world(world, inner)
                    for check in op[2]:
                        failure = _observe_and_compare(world, check)
                        if failure:
                            raise _Divergence(failure)
                    raise _Rollback
            except _Rollback:
                pass
        case "flush":
            env.flush_all()


def _update_world_records(world: World, op: Mutation, env: typing.Any) -> None:
    kind = op[0]
    match kind:
        case "write":
            _role, _i, fname, value = op[1:]
            record = world.record(_role, _i)
            value = _resolve(world, value)
            if record is None or (fname == "parent_id" and _below(record, value)):
                return
            record.write({fname: value})
        case "write_lang":
            role, index, lang, word = op[1:]
            record = world.record(role, index)
            if record is not None:
                record.with_context(lang=lang)[TRANSLATED[role]] = word
        case "create":
            role, values = op[1:]
            values = {k: _resolve(world, v) for k, v in values.items()}
            if role == "line" and not values.get("doc_id"):
                return
            world.handles[role].append(world.model(role).create(values).id)
        case "unlink":
            record = world.record(op[1], op[2])
            if record is not None:
                record.unlink()


def _update_world_relations(world: World, op: Mutation, env: typing.Any) -> None:
    kind = op[0]
    match kind:
        case "lines":
            doc = world.record("doc", op[1])
            if doc is None:
                return
            command, line_index, amount = op[2:]
            line = world.record("line", line_index)
            if command == "create":
                doc.line_ids = [Command.create({"amount": amount, "kind": "open"})]
                world.handles["line"].append(doc.line_ids.sorted("id")[-1].id)
            elif line is not None:
                maker = {
                    "delete": Command.delete,
                    "unlink": Command.unlink,
                    "link": Command.link,
                }[command]
                doc.line_ids = [maker(line.id)]
        case "tags":
            doc = world.record("doc", op[1])
            tag = world.record("tag", op[3])
            if doc is None or tag is None:
                return
            command = {
                "link": Command.link(tag.id),
                "unlink": Command.unlink(tag.id),
                "set": Command.set([tag.id]),
            }[op[2]]
            doc.tag_ids = [command]


def _update_world_access(world: World, op: Mutation, env: typing.Any) -> None:
    kind = op[0]
    match kind:
        case "membership":
            user, group = world.bound("users")[op[1]], world.bound("groups")[op[2]]
            add = op[3]
            user.group_ids = [
                Command.link(group.id) if add else Command.unlink(group.id)
            ]
        case "grant":
            user, group, company = (
                world.bound("users")[op[1]],
                world.bound("groups")[op[2]],
                world.bound("companies")[op[3]],
            )
            if company not in user.company_ids:
                return
            world.grants.append(
                env["res.users.grant"]
                .create(
                    {
                        "user_id": user.id,
                        "group_id": group.id,
                        "company_ids": [Command.set(company.ids)],
                    }
                )
                .id
            )
        case "ungrant":
            grant = env["res.users.grant"].browse(
                world.grants[op[1] % len(world.grants)] if world.grants else []
            )
            if grant.exists():
                grant.unlink()
        case "rule_create":
            world.rows.append(env["ir.access"].create(_row_values(world, op[1])).id)
        case "rule_write":
            row = env["ir.access"].browse(world.rows[op[1]])
            if op[3]:
                row.active = not row.active
                return
            values = _row_values(world, op[2])
            values.pop("model_id", None)
            values.pop("class_id", None)
            row.write(values)
        case "rule_unlink":
            created = world.rows[len(SLOTS) :]
            row = env["ir.access"].browse(
                created[op[1] % len(created)] if created else []
            )
            if row.exists():
                row.unlink()


def _update_world_related_records(world: World, op: Mutation, env: typing.Any) -> None:
    kind = op[0]
    match kind:
        case "partner_parent":
            contact = world.bound("contacts")[op[1]]
            parents = [*world.bound("company_partners"), False]
            parent = parents[op[2]]
            if contact.is_company or contact == parent:
                return
            contact.parent_id = parent
        case "write_via":
            doc_index, path, pick, fname, value, mode = op[1:]
            doc = world.record("doc", doc_index)
            targets = doc.with_context(active_test=False).mapped(path) if doc else []
            if not targets:
                return
            target = targets[pick % len(targets)]
            value = _resolve(world, value)
            if target._name == "res.partner" and (
                target.is_company or target.id == value
            ):
                return
            if fname == "parent_id" and _below(target, value):
                return
            _write_as(world, target, fname, value, mode)
        case "cache_write":
            role, index, fname, value = op[1:]
            record = world.record(role, index)
            if record is not None:
                _write_as(world, record, fname, _resolve(world, value), "cache")
        case "raw_write":
            role, index, fname, value, whole_model = op[1:]
            record = world.record(role, index)
            if record is not None:
                mode = "raw_model" if whole_model else "raw"
                _write_as(world, record, fname, _resolve(world, value), mode)


_WORLD_MUTATION_HANDLERS: dict[
    str, typing.Callable[[World, Mutation, typing.Any], None]
] = {
    "write": _update_world_records,
    "write_lang": _update_world_records,
    "create": _update_world_records,
    "unlink": _update_world_records,
    "lines": _update_world_relations,
    "tags": _update_world_relations,
    "membership": _update_world_access,
    "grant": _update_world_access,
    "ungrant": _update_world_access,
    "rule_create": _update_world_access,
    "rule_write": _update_world_access,
    "rule_unlink": _update_world_access,
    "partner_parent": _update_world_related_records,
    "write_via": _update_world_related_records,
    "cache_write": _update_world_related_records,
    "raw_write": _update_world_related_records,
}


def _write_as(world: World, record: typing.Any, fname: str, value, mode: str) -> None:
    env = world.env
    record_field = record._fields[fname]
    if mode == "write":
        record.write({fname: value})
    elif mode == "cache":
        env.cache.update(
            record,
            record_field,
            [record_field.convert_to_cache(value, record)],
            dirty=True,
        )
    else:
        record.flush_recordset()
        column = record_field.convert_to_column(value, record)
        if world.sql:
            env.cr.execute(
                f'UPDATE "{record._table}" SET "{fname}" = %s WHERE id = %s',  # noqa: E8501 -- table and column of the generator's fixed models
                (column, record.id),
            )
        else:
            env.cr.storage.update_rows(record._table, [(record.id, {fname: column})])
        if mode == "raw_model":
            record.invalidate_model([fname])
        else:
            record.invalidate_recordset([fname])


def _role_of(world: World, model_name: str) -> str:
    return next(role for role, name in world.names.items() if name == model_name)


def _below(record: typing.Any, parent_id: int) -> bool:
    tree = record.with_context(active_test=False).search(
        [("id", "child_of", record.id)]
    )
    return bool(parent_id) and parent_id in tree._ids


def _row_values(world: World, spec: dict) -> dict:
    env = world.env
    group = world.groups[spec["group"]]
    values: dict[str, typing.Any] = {
        "name": "memo property row",
        "kind": spec["kind"],
        "group_id": group.id,
        "operation": spec["operation"],
        "active": spec["active"],
    }
    if spec["role"] == "note":
        values["class_id"] = world.note_class.id
    else:
        values["model_id"] = env["ir.model"]._get_id(world.names[spec["role"]])
    if spec["kind"] == "guard":
        values["guard_scope"] = spec["scope"]
        if spec["scope"] == "everyone":
            values["group_id"] = world.everyone.id
    reach = spec.get("reach") or False
    values["reach"], values["anchor"] = reach, False
    if reach == "own_partner":
        values["reach"], values["anchor"] = "own", "partner"
    values["domain"] = spec.get("domain") or False
    return values


class _Rollback(Exception):
    pass


class _Divergence(Exception):
    def __init__(self, failure: dict) -> None:
        super().__init__(failure)
        self.failure = failure


def principal_env(world: World, principal: tuple) -> typing.Any:
    user_index, companies, lang, acting, active_test = principal
    user = world.bound("users")[user_index]
    held = world.bound("companies")
    allowed = [
        held[0 if letter == "A" else 1].id
        for letter in companies
        if held[0 if letter == "A" else 1] in user.company_ids
    ]
    context: dict[str, typing.Any] = {"lang": lang, "active_test": active_test}
    if allowed:
        context["allowed_company_ids"] = allowed
    env = world.env(user=user.id, su=False, context=context)
    if acting is not None:
        contact = world.bound("contacts")[acting]
        env = env["res.partner"].with_acting_partner(contact).env
    return env


def _norm(value: typing.Any) -> typing.Any:
    if hasattr(value, "_ids"):
        return tuple(value._ids)
    if isinstance(value, dict):
        return tuple(sorted((key, _norm(item)) for key, item in value.items()))
    if isinstance(value, list | tuple):
        return tuple(_norm(item) for item in value)
    return value


READ_FIELDS = {
    "doc": ["name", "level", "state", "total", "folder_id", "note", "active"],
    "line": ["amount", "kind", "doc_id", "active", "label"],
    "folder": ["name", "parent_id", "company_id"],
    "tag": ["name", "color"],
}


def observe(env: typing.Any, world: World, kind: str, role: str, ids, detail):
    model = env[world.names[role]]
    records = model.browse(ids)
    try:
        match kind:
            case "has_access":
                return tuple(record.has_access(detail) for record in records)
            case "filtered":
                return tuple(records._filtered_access(detail)._ids)
            case "check":
                records.check_access(detail)
                return "allowed"
            case "search":
                domain = {
                    None: [],
                    "level": [("level", ">", 1)] if role == "doc" else [],
                    "name": [("name", "ilike", "a")] if role != "line" else [],
                    "tree": {
                        "doc": [("folder_id", "child_of", world.handles["folder"][1])],
                        "folder": [("id", "child_of", world.handles["folder"][1])],
                        "line": [
                            (
                                "doc_id.folder_id",
                                "parent_of",
                                world.handles["folder"][3],
                            )
                        ],
                        "tag": [],
                    }[role],
                }[detail]
                return tuple(sorted(model.search(domain)._ids))
            case "read":
                return _norm(records.read(READ_FIELDS[role]))
            case "x2many":
                return tuple(
                    tuple(record[detail]._ids)
                    for record in records._filtered_access("read")
                )
            case "web_read":
                if not hasattr(records, "web_read"):
                    return None
                return _norm(
                    records.web_read(
                        {
                            "name": {},
                            "note": {},
                            "total": {},
                            "folder_id": {"fields": {"display_name": {}}},
                            "line_ids": {"fields": {"amount": {}, "kind": {}}},
                            "tag_ids": {"fields": {"color": {}}},
                        }
                    )
                )
            case "read_group":
                groupby = {
                    "doc": ["state"],
                    "line": ["kind"],
                    "folder": ["parent_id"],
                    "tag": ["color"],
                }[role]
                return _norm(model._read_group([], groupby, ["__count"]))
            case "masked":
                masked = records._field_masked_ids(records._fields["note"])
                return None if masked is None else tuple(sorted(masked))
            case "display":
                return _norm(
                    [
                        (record.id, record.display_name)
                        for record in records._filtered_display_name_access()
                    ]
                )
    except (AccessError, MissingError) as error:
        return ("raise", type(error).__name__)
    raise ValueError(kind)


@contextmanager
def from_scratch(
    env: typing.Any, *, registry_caches: bool = False
) -> typing.Iterator[typing.Callable]:
    env.flush_all()
    cr, registry = env.cr, env.registry
    old_transaction, old_cache = cr.transaction, cr.cache
    lrus = registry.ormcache_lrus
    saved = dict(lrus)
    for name, lru in saved.items():
        lrus[name] = LRU(lru.count, lru.items() if registry_caches else ())
    fresh = Transaction(registry)
    fresh.backend = old_transaction.backend
    cr.transaction, cr.cache = fresh, {}
    try:
        fresh.default_env = fresh.environment(cr, env.uid, {}, True)
        yield lambda other: fresh.environment(
            cr, other.uid, other.context, other.su, other.privileges
        )
    finally:
        cr.transaction, cr.cache = old_transaction, old_cache
        lrus.clear()
        lrus.update(saved)


def definition(env: typing.Any, model_name: str, operation: str, ids) -> set:
    policy = env.registry.access_policy
    if not policy.model_allowed(env, model_name, operation):
        return set()
    domain = policy.record_domain(env, model_name, operation)
    candidates = env[model_name].sudo().with_context(active_test=False)
    return set(candidates.search(Domain("id", "in", list(ids)) & domain)._ids)


def _as_verdicts(kind: str, ids, admitted: set) -> typing.Any:
    if kind == "has_access":
        return tuple(id_ in admitted for id_ in ids)
    if kind == "filtered":
        return tuple(id_ for id_ in ids if id_ in admitted)
    if all(id_ in admitted for id_ in ids):
        return "allowed"
    return ("raise", "AccessError")


def _observe_and_compare(world: World, op: tuple) -> dict | None:
    _tag, principal, kind, role, indexes, detail = op
    ids = world.ids(role, indexes)
    if not ids and kind not in ("search", "read_group"):
        return None
    env = principal_env(world, principal)
    memo = observe(env, world, kind, role, ids, detail)
    with from_scratch(world.env) as fresh_env:
        scratch_env = fresh_env(env)
        scratch = observe(scratch_env, world, kind, role, ids, detail)
        expected = None
        if kind in ("has_access", "filtered", "check"):
            admitted = definition(scratch_env, world.names[role], detail, ids)
            expected = _as_verdicts(kind, ids, admitted)
    if memo == scratch and (expected is None or memo == expected):
        return None
    return {
        "check": op,
        "ids": ids,
        "memo": memo,
        "from_scratch": scratch,
        "definition": expected,
    }


def _execute(world: World, op: tuple) -> dict | None:
    try:
        if op[0] == "observe":
            return _observe_and_compare(world, op)
        _update_world(world, op)
    except _Divergence as divergence:
        return divergence.failure
    except Exception as error:
        return {
            "crash": f"{type(error).__name__}: {str(error).splitlines()[0][:200]}",
            "trace": traceback.format_exc(limit=-6),
        }
    return None


@contextmanager
def _isolated(world: World) -> typing.Iterator[None]:
    env = world.env
    snapshot = (
        {role: list(ids) for role, ids in world.handles.items()},
        list(world.rows),
        list(world.grants),
    )
    try:
        with env.cr.savepoint():
            env.registry.clear_all_caches()
            env.invalidate_all()
            yield
            raise _Rollback
    except _Rollback:
        pass
    finally:
        world.handles = snapshot[0]
        world.rows, world.grants = snapshot[1], snapshot[2]
        env.registry.clear_all_caches()
        env.invalidate_all()


def run(world: World, ops: list[tuple]) -> dict | None:
    failure = None
    with _isolated(world):
        for step, op in enumerate(ops):
            if failure := _execute(world, op):
                failure["step"] = step
                break
    return failure


def _same_finding(found: dict | None, failure: dict) -> bool:
    if found is None:
        return False
    if "crash" in failure:
        return found.get("crash", "").split(":")[0] == failure["crash"].split(":")[0]
    return "crash" not in found


def shrink(world: World, ops: list[tuple], failure: dict) -> tuple[list, dict]:
    ops = ops[: failure["step"] + 1]
    chunk = max(1, len(ops) // 2)
    while chunk >= 1:
        index = 0
        while index < len(ops):
            candidate = ops[:index] + ops[index + chunk :]
            found = run(world, candidate) if candidate else None
            if found is not None and _same_finding(found, failure):
                ops, failure = candidate[: found["step"] + 1], found
            else:
                index += chunk
        chunk //= 2
    return ops, failure


def describe(ops: list[tuple], failure: dict) -> str:
    lines = "\n".join(f"  {step}: {op!r}" for step, op in enumerate(ops))
    if "crash" in failure:
        return (
            f"the sequence crashed:\n{lines}\n  {failure['crash']}\n{failure['trace']}"
        )
    return (
        f"the access memo diverged from a principal judged from scratch:\n{lines}"
        f"\n  memo: {failure['memo']!r}\n  from scratch: {failure['from_scratch']!r}"
        f"\n  access domain: {failure['definition']!r}\n  ids: {failure['ids']!r}"
    )


TRIABLE = frozenset(
    {
        "write",
        "write_via",
        "write_lang",
        "create",
        "unlink",
        "lines",
        "tags",
        "partner_parent",
        "cache_write",
        "raw_write",
    }
)


@contextmanager
def _in_scratch(world: World) -> typing.Iterator[None]:
    handles = {role: list(ids) for role, ids in world.handles.items()}
    real = world.env
    with from_scratch(real, registry_caches=True) as fresh:
        world.env = fresh(real)
        try:
            yield
        finally:
            world.env, world.handles = real, handles


def _indirect(op: tuple, check: tuple) -> bool:
    if op[0] in (
        "lines",
        "tags",
        "partner_parent",
        "write_lang",
        "cache_write",
        "write_via",
    ):
        return True
    return op[0] in ("write", "raw_write") and op[1] != _focus_role(check)


def _flipping(world: World, check: tuple, candidates: list[tuple]) -> tuple | None:
    _tag, principal, kind, role, indexes, detail = check
    ids = world.ids(role, indexes)
    candidates = sorted(candidates, key=lambda op: not _indirect(op, check))
    with _in_scratch(world):
        before = observe(
            principal_env(world, principal), world, kind, role, ids, detail
        )
        for candidate in candidates:
            if candidate[0] not in TRIABLE:
                continue
            try:
                with world.env.cr.savepoint():
                    _update_world(world, candidate)
                    after = observe(
                        principal_env(world, principal), world, kind, role, ids, detail
                    )
                    raise _Rollback
            except _Rollback:
                pass
            except UserError, ValidationError:
                continue
            except Exception:
                return candidate
            if after != before:
                return candidate
    return None


class _ExplorationResult(typing.NamedTuple):
    operations: list[Mutation]
    failure: dict[str, typing.Any] | None


@dataclass(slots=True)
class _MutationExplorer:
    world: World
    rng: random.Random
    theme: str
    operations: list[Mutation]
    texts: list[str]

    def _prepare_observation_for_theme(self) -> Mutation:
        by_kind: dict[str, list[tuple]] = {}
        for _attempt in range(40):
            check = _prepare_observation(self.rng)
            readable = self.theme == "bypass" or self.theme in _hazards(
                _focus_role(check)
            )
            if readable and _memoized(check):
                by_kind.setdefault(check[2], []).append(check)
        if not by_kind:
            return _prepare_observation(self.rng)
        return self.rng.choice(by_kind[self.rng.choice(sorted(by_kind))])

    def _run_operation_and_get_failure(
        self, op: Mutation
    ) -> dict[str, typing.Any] | None:
        self.operations.append(op)
        if op[0] == "rule_create":
            self.texts.extend(_spec_texts([op[1]]))
        elif op[0] == "rule_write":
            self.texts.extend(_spec_texts([op[2]]))
        return _execute(self.world, op)

    def _run_scope_episode_and_get_failure(self) -> dict[str, typing.Any] | None:
        indexes = tuple(
            self.rng.randrange(16) for _i in range(self.rng.randrange(1, 4))
        )
        check = ("observe", _principal(self.rng), "x2many", "doc", indexes, "line_ids")
        focus, _hazard = _focus_rule(
            self.rng, self.world, check, self.rng.choice(SCOPE_HAZARDS)
        )
        for op in focus:
            if failure := self._run_operation_and_get_failure(op):
                return failure
        if failure := self._run_operation_and_get_failure(check):
            return failure
        candidates = [
            (
                "write_via",
                self.rng.choice(indexes),
                "line_ids",
                self.rng.randrange(4),
                fname,
                _value(self.rng, self.world, "line", fname),
                self.rng.choice(("raw", "raw_model")),
            )
            for fname in self.rng.choices(BYPASSABLE["raw"]["line"], k=3)
        ]
        chosen = _flipping(self.world, check, candidates) or candidates[0]
        return self._run_operation_and_get_failure(
            chosen
        ) or self._run_operation_and_get_failure(check)

    def _run_episode_and_get_failure(self) -> dict[str, typing.Any] | None:
        if self.rng.random() < SCOPE_EPISODES:
            return self._run_scope_episode_and_get_failure()
        if self.rng.random() < 0.2:
            return self._run_operation_and_get_failure(
                _prepare_mutation(self.rng, self.world)
            )
        themed = self.rng.random() < 0.7
        check = (
            self._prepare_observation_for_theme()
            if themed
            else _prepare_observation(self.rng)
        )
        read, hazard = self.texts[-3:], None
        if themed or self.rng.random() < 0.5:
            focus, hazard = _focus_rule(
                self.rng, self.world, check, self.theme if themed else None
            )
            for op in focus:
                if failure := self._run_operation_and_get_failure(op):
                    return failure
            read = _spec_texts([focus[0][2]])
            self.texts.extend(read)
        if failure := self._run_operation_and_get_failure(check):
            return failure
        for _round in range(self.rng.randrange(1, 4)):
            candidates = [
                _fact_mutation(
                    self.rng, self.world, read, check, themed and self.theme == "bypass"
                )
                if self.rng.random() < 0.7
                else _prepare_mutation(self.rng, self.world, focus=check)
                for _i in range(CANDIDATES)
            ]
            chosen = _flipping(self.world, check, candidates) or candidates[0]
            if failure := self._run_operation_and_get_failure(
                chosen
            ) or self._run_operation_and_get_failure(check):
                return failure
        if self.rng.random() < 0.7:
            variations = [_vary(self.rng, check, hazard) for _i in range(4)]
            varied = _differing(self.world, check, variations) or variations[0]
            if failure := self._run_operation_and_get_failure(varied):
                return failure
            if self.rng.random() < 0.5:
                return self._run_operation_and_get_failure(check)
        return None


def explore_mutations(world: World, seed: int, steps: int) -> _ExplorationResult:
    rng = random.Random(seed)
    ops: list[Mutation] = []
    texts: list[str] = []
    theme = THEMES[seed % len(THEMES)]
    explorer = _MutationExplorer(world, rng, theme, ops, texts)

    failure = None
    with _isolated(world):
        for slot, (role, kind) in enumerate(SLOTS):
            spec = _row_spec(rng, world, role, kind)
            if kind == "permission" and slot != 1:
                spec["group"] = 0
            failure = failure or explorer._run_operation_and_get_failure(
                ("rule_write", slot, spec, False)
            )
        while failure is None and len(ops) < steps:
            failure = explorer._run_episode_and_get_failure()
        if failure is not None:
            failure["step"] = len(ops) - 1
    return _ExplorationResult(ops, failure)


def campaign(world: World, seed: int, steps: int) -> tuple[dict, str | None]:
    ops, failure = explore_mutations(world, seed, steps)
    stats = {
        "seed": seed,
        "steps": len(ops),
        "checks": sum(op[0] == "observe" for op in ops),
    }
    if failure is None:
        return stats, None
    replayed = run(world, ops)
    if replayed is None:
        return stats, describe(ops, failure) + "\n  (not reproduced by a replay)"
    ops, failure = shrink(world, ops, replayed)
    return stats, describe(ops, failure)
