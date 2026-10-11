import ast
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from .ir_access import PREDICATE_BINDS as BINDS
from .ir_access import domain_group_tests, predicate_arguments


class IrAccessPredicate(models.Model):
    _name = "ir.access.predicate"
    _description = "Access Predicate"
    _order = "name"

    name = fields.Char(
        required=True,
        help="How rows name it, module-qualified: approval.approver_of.",
    )
    description = fields.Char(
        translate=True,
        help="What it says in an explanation of access: you are deciding its approval.",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        ondelete="cascade",
        help="The model it is written for; empty for a predicate any model can use.",
    )
    template = fields.Char(
        help="A domain reading P (the principal: P.user, P.partner, "
        "P.commercial_partner, P.companies, P.employees, P.teams, P.units) and "
        "args (the row's arguments).",
    )
    method = fields.Char(
        help="Instead of a template, a method of the model taking the principal's "
        "binds and the row's arguments and answering a domain; its name starts "
        "with _access_predicate_.",
    )

    _name_unique = models.Constraint("UNIQUE (name)", "A predicate's name is unique.")
    _template_or_method = models.Constraint(
        "CHECK ((template IS NULL) != (method IS NULL))",
        "A predicate is a template or a method, not both.",
    )

    @api.constrains("template", "method", "model_id")
    def _check_definition(self) -> None:
        for predicate in self:
            if predicate.method:
                if not predicate.method.startswith("_access_predicate_"):
                    raise ValidationError(
                        self.env._(
                            "The method of predicate %(name)s must start with "
                            "_access_predicate_.",
                            name=predicate.name,
                        )
                    )
                # a predicate for any model names a method every model has
                model_name = predicate.model_id.model or "base"
                if not callable(getattr(self.env[model_name], predicate.method, None)):
                    raise ValidationError(
                        self.env._(
                            "Predicate %(name)s names %(method)s, which its model "
                            "does not define.",
                            name=predicate.name,
                            method=predicate.method,
                        )
                    )
                continue
            predicate._check_template()

    def _check_template(self) -> None:
        try:
            tree = ast.parse(self.template, mode="eval")
        except SyntaxError as e:
            raise ValidationError(
                self.env._("Predicate %(name)s: %(error)s", name=self.name, error=e)
            ) from None
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        if names - {"P", "args", "True", "False", "None"}:
            raise ValidationError(
                self.env._(
                    "Predicate %(name)s reads %(names)s; a template reads only P "
                    "and args.",
                    name=self.name,
                    names=", ".join(sorted(names - {"P", "args"})),
                )
            )
        read = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "P"
        }
        if read - BINDS:
            raise ValidationError(
                self.env._(
                    "Predicate %(name)s reads P.%(binds)s; the principal offers "
                    "%(offered)s.",
                    name=self.name,
                    binds=", P.".join(sorted(read - BINDS)),
                    offered=", ".join(sorted(BINDS)),
                )
            )
        if tests := domain_group_tests(self.template):
            raise ValidationError(
                self.env._(
                    "Predicate %(name)s tests the user's groups (%(tests)s); "
                    "membership is what an access row's group states.",
                    name=self.name,
                    tests=", ".join(tests),
                )
            )

    def _arguments(self, model_name: str) -> tuple[frozenset[str], frozenset[str]]:
        # the arguments it reads, required and optional: a template's are the
        # args.<name> it spells, a method's what predicate_arguments declares
        # on it (nothing, undeclared), wherever in the model's classes
        self.check_singleton()
        if self.template:
            tree = ast.parse(self.template, mode="eval")
            return frozenset(
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "args"
            ), frozenset()
        for cls in type(self.env[model_name]).__mro__:
            method = vars(cls).get(self.method)
            if arguments := getattr(method, "_access_arguments", None):
                return arguments
        return frozenset(), frozenset()

    def write(self, vals: dict[str, Any]) -> bool:
        result = super().write(vals)
        if {"template", "method", "model_id"} & vals.keys():
            # what it reads may have changed: the rows naming it still pass it
            # exactly that. A row on a model no module has loaded yet -- base
            # reloading its predicates during an upgrade -- is checked when its
            # own module loads it.
            self.env["ir.access"].search(
                [("predicate_id", "in", self.ids)]
            )._check_reach(loaded_only=True)
        self.env["ir.access"]._clear_access_caches()
        return result


class Base(models.AbstractModel):
    _inherit = "base"

    @predicate_arguments("operation", "role", optional=("with",))
    def _access_predicate_conditional_reach(self, bind, args) -> Domain:
        # a restricted role's ceiling (base.conditional_reach), for the members
        # of args["role"]: they reach what their conditional permissions on the
        # model reach for args["operation"], and whatever the groups implying
        # the role (its wider variants) or named in args["with"] grant -- not
        # what another group reaching every record grants beside, as record
        # rules bounded access lines
        Access = self.env["ir.access"]
        role = self.env.ref(args["role"]).id
        family = set(Access._group_ids_implying().get(role, {role}))
        family.update(self.env.ref(xmlid).id for xmlid in args.get("with", ()))
        return Access._conditional_reach(
            self._name, args["operation"], frozenset(family)
        )

    @predicate_arguments("field", optional=("kindless",))
    def _access_predicate_enabled_asset_kind(self, bind, args) -> Domain:
        user = self.env["res.users"].browse(bind("user"))
        domain = Domain(args["field"], "in", user._get_enabled_asset_kinds())
        if args.get("kindless"):
            path = args["field"].split(".")
            for end in range(1, len(path) + 1):
                domain |= Domain(".".join(path[:end]), "=", False)
        return domain
