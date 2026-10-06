import os
import random

from odoo.exceptions import AccessError

# the differential property of the access policy: for every principal and
# operation, the records the check admits are the records the filter finds.
# test_access_rights runs it on PostgreSQL, where the search compiles to SQL
# and the check evaluates in memory.

OPERATIONS = ("read", "write")
LETTERS = {"read": "r", "write": "u"}
BREAK = os.environ.get("ACCESS_PROPERTY_BREAK") == "1"


def leaf(rng: random.Random) -> str:
    kind = rng.randrange(9)
    if kind == 0:
        operator = rng.choice(["=", "!=", "<", ">", ">=", "<="])
        return f"[('a', '{operator}', {rng.randrange(5)})]"
    if kind == 1:
        return f"[('b', 'in', {rng.sample(range(5), rng.randrange(0, 4))})]"
    if kind == 2:
        return f"[('flag', '=', {rng.choice([True, False])})]"
    if kind == 3:
        return "[('owner_id', '=', user.id)]"
    if kind == 4:
        return "['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]"
    if kind == 5:
        operator = rng.choice(["ilike", "not ilike", "=like", "like"])
        return f"[('name', '{operator}', '{rng.choice(['x', 'y%', '%z', 'Q'])}')]"
    if kind == 6:
        return (
            f"[('parent_id.a', '{rng.choice(['=', '>', '!='])}', {rng.randrange(5)})]"
        )
    if kind == 7:
        return f"[('parent_id', '{rng.choice(['=', '!='])}', False)]"
    return "[('owner_id', '=', False)]"


def domain(rng: random.Random, depth: int = 0) -> str:
    if depth > 1 or rng.random() < 0.5:
        return leaf(rng)
    operator = rng.choice(["&", "|", "!"])
    if operator == "!":
        return f"['!'] + {domain(rng, depth + 1)}"
    return f"['{operator}'] + {domain(rng, depth + 1)} + {domain(rng, depth + 1)}"


def row_values(rng: random.Random, model_id: int, groups, everyone) -> dict:
    # a permission or a guard, for a group or everyone, over a random domain
    # or a rung of the model's anchors, for a random subset of operations
    kind = "guard" if rng.random() < 0.2 else "permission"
    group = rng.choice(groups)
    values = {
        "name": "property row",
        "model_id": model_id,
        "kind": kind,
        "operation": "".join(
            letter
            for letter, odds in (("c", 0.3), ("r", 1.0), ("u", 0.6), ("d", 0.3))
            if rng.random() < odds
        ),
        "group_id": group.id,
    }
    if kind == "guard":
        if rng.random() < 0.5:
            values["group_id"] = everyone.id
            values["guard_scope"] = "everyone"
        else:
            values["guard_scope"] = "members"
    shape = rng.randrange(6)
    if shape == 0:
        values["reach"] = "own"
    elif shape == 1:
        values["reach"] = "company"
    elif shape == 2:
        values["reach"] = rng.choice(["own", "company"])
        values["domain"] = rng.choice(
            ["[('flag', '=', True)]", "[('a', '<', 3)]", "[('b', '!=', 1)]"]
        )
    else:
        values["domain"] = domain(rng)
    return values


def record_values(rng: random.Random, users, companies, earlier_ids) -> dict:
    return {
        "name": rng.choice(["x1", "yy", "az", "Q", "xyz", False]),
        "a": rng.randrange(5),
        "b": rng.randrange(5),
        "flag": rng.random() < 0.5,
        "owner_id": rng.choice([False, *users.ids]),
        "company_id": rng.choice([False, *companies.ids]),
        "parent_id": rng.choice([False, *earlier_ids[-20:]]),
    }


def build_world(env, model_name: str, rng: random.Random, *, records: int):
    groups = env["res.groups"].create([{"name": f"property {i}"} for i in range(5)])
    companies = env["res.company"].browse(env.company.id) | env["res.company"].create(
        {"name": "property B"}
    )
    users = env["res.users"]
    for i in range(6):
        user = env["res.users"].create(
            {
                "name": f"property user {i}",
                "login": f"property_user_{i}_{rng.random()}",
                "company_id": companies[0].id,
                "company_ids": [(6, 0, companies.ids if i % 2 else companies[:1].ids)],
            }
        )
        held = [groups[0], *rng.sample(list(groups[1:]), rng.randrange(0, 3))]
        if held:
            user.group_ids = [(4, group.id) for group in held]
        users |= user
    docs = env[model_name]
    for _i in range(records):
        docs |= docs.create(record_values(rng, users, companies, docs.ids))
    return groups, companies, users, docs


def principals(env, users, companies):
    for user in users:
        sets = [companies[:1]]
        if companies[1] in user.company_ids:
            sets.append(companies)
        for allowed in sets:
            yield (
                user,
                env(
                    user=user.id,
                    su=False,
                    context={"allowed_company_ids": allowed.ids},
                ),
            )


def divergences(env, model_name: str, docs, users, companies) -> tuple[list, list]:
    # every path's answer against the SQL (or in-memory) search of the
    # access domain under sudo
    found, sizes = [], []
    policy = env.registry.access_policy
    for user, uenv in principals(env, users, companies):
        for operation in OPERATIONS:
            if policy.model_allowed(uenv, model_name, operation):
                access = policy.record_domain(uenv, model_name, operation)
                principal_su = uenv[model_name].sudo().with_context(active_test=False)
                expected = set(principal_su.search(access).ids)
                answers = {
                    "filtered_domain": set(
                        docs.with_env(principal_su.env).filtered_domain(access).ids
                    ),
                }
            else:
                expected, answers = set(), {}
            asked = "write" if BREAK and operation == "read" else operation
            mine = docs.with_env(uenv)
            answers["has_access"] = {d.id for d in mine if d.has_access(asked)}
            answers["_filtered_access"] = set(mine._filtered_access(operation).ids)
            if operation == "read":
                try:
                    answers["search"] = set(uenv[model_name].search([]).ids)
                except AccessError:
                    answers["search"] = set()
            sizes.append(len(expected))
            for path, got in answers.items():
                if got != expected:
                    found.append(
                        {
                            "user": user.login,
                            "companies": uenv.context["allowed_company_ids"],
                            "operation": operation,
                            "path": path,
                            "only_domain": sorted(expected - got)[:5],
                            "only_path": sorted(got - expected)[:5],
                        }
                    )
            uenv.invalidate_all()
    return found, sizes


def run(env, model_name: str, *, seed: int, rounds: int, records: int) -> dict:
    rng = random.Random(seed)
    groups, companies, users, docs = build_world(env, model_name, rng, records=records)
    everyone = env.ref("base.group_everyone", raise_if_not_found=False) or env[
        "res.groups"
    ].create({"name": "everyone"})
    model_id = env["ir.model"]._get_id(model_name)
    rows = env["ir.access"].sudo()
    found, sizes, total_rows = [], [], 0
    for _round in range(rounds):
        rows.search([("model_id", "=", model_id)]).unlink()
        count = rng.randrange(1, 8)
        rows.create(
            [row_values(rng, model_id, groups, everyone) for _i in range(count)]
        )
        total_rows += count
        env.flush_all()
        env.invalidate_all()
        round_found, round_sizes = divergences(env, model_name, docs, users, companies)
        found.extend(round_found)
        sizes.extend(round_sizes)
    return {
        "seed": seed,
        "rounds": rounds,
        "rows": total_rows,
        "cases": len(sizes),
        "divergences": found,
        "visible": (min(sizes), sorted(sizes)[len(sizes) // 2], max(sizes)),
        "records": len(docs),
    }
