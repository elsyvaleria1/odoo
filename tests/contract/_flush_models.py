from odoo import api, fields, models

_MOD = "test_search_flush"


class FlushGroup(models.Model):
    _name = "flush.group"
    _module = _MOD
    _description = "Search Flush Group"
    _order = "rank"
    _log_access = False

    value = fields.Integer()
    rank = fields.Integer(compute="_compute_rank", store=True)
    untouched = fields.Integer(compute="_compute_untouched", store=True)

    @api.depends("value")
    def _compute_rank(self):
        for record in self:
            record.rank = record.value * 2

    @api.depends("value")
    def _compute_untouched(self):
        for record in self:
            record.untouched = record.value + 100


class FlushItem(models.Model):
    _name = "flush.item"
    _module = _MOD
    _description = "Search Flush Item"
    _log_access = False

    name = fields.Char()
    group_id = fields.Many2one("flush.group")


class RecNode(models.Model):
    _name = "rec.node"
    _module = _MOD
    _description = "Recursive Compute Node"
    _log_access = False

    name = fields.Char()
    parent_id = fields.Many2one("rec.node")
    root_id = fields.Many2one(
        "rec.node", compute="_compute_root_id", store=True, recursive=True
    )

    @api.depends("parent_id", "parent_id.root_id")
    def _compute_root_id(self):
        for node in self:
            node.root_id = node.parent_id["root_id"] or node

    @api.constrains("root_id")
    def _check_root(self):
        for node in self:
            if node.root_id and node.root_id["parent_id"]:
                raise ValueError(f"{node} has a non-root root_id")


class RecAlternating(models.Model):
    _name = "rec.alternating"
    _module = _MOD
    _description = "Alternating Recursive Compute Node"
    _log_access = False

    name = fields.Char()
    parent_id = fields.Many2one("rec.alternating")
    upward = fields.Char(compute="_compute_upward", store=True, recursive=True)
    downward = fields.Char(compute="_compute_downward", store=True, recursive=True)

    @api.depends("name", "parent_id.downward")
    def _compute_upward(self):
        for node in self:
            node.upward = (
                f"{node.parent_id['downward']} / {node.name}"
                if node.parent_id
                else node.name
            )

    @api.depends("name", "parent_id.upward")
    def _compute_downward(self):
        for node in self:
            node.downward = (
                f"{node.parent_id['upward']} / {node.name}"
                if node.parent_id
                else node.name
            )


def assert_parent_write_survives_a_middle_first_read(env):
    Node = env["rec.node"]
    chain = [Node.create({"name": "root"})]
    for i in range(5):
        chain.append(Node.create({"name": f"c{i}", "parent_id": chain[-1].id}))
    env.flush_all()
    env.invalidate_all(flush=False)

    detached = chain[1]
    detached.parent_id = False

    root_field = Node._fields["root_id"]
    assert all(env.is_to_compute(root_field, node) for node in chain[1:])
    assert chain[3].root_id == detached

    env.flush_all()
    env.invalidate_all(flush=False)
    for node in chain[1:]:
        assert node.root_id == detached
    return chain[1:], detached


def assert_alternating_fields_survive_a_middle_first_read(env):
    Node = env["rec.alternating"]
    chain = [Node.create({"name": "Root"})]
    for i in range(6):
        chain.append(Node.create({"name": f"c{i}", "parent_id": chain[-1].id}))
    env.flush_all()
    env.invalidate_all(flush=False)

    chain[0].name = "Renamed"
    for fname in ("upward", "downward"):
        assert all(env.is_to_compute(Node._fields[fname], node) for node in chain)
    for fname in ("upward", "downward"):
        assert chain[3][fname] == "Renamed / c0 / c1 / c2"

    env.flush_all()
    env.invalidate_all(flush=False)
    for i, node in enumerate(chain):
        expected = " / ".join(["Renamed", *(f"c{j}" for j in range(i))])
        assert node.upward == node.downward == expected
    return chain
