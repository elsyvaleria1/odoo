import ast
from collections import defaultdict

from odoo.exceptions import ValidationError

_ALLOWED_FUNCS = ("min", "max")
_ALLOWED_NAMES = ("price_unit", "quantity", "base", "product", "uom")
_ALLOWED_CONSTANT_T = (int, float, type(None))


_NODE_WHITELIST = (
    ast.Expression,
    ast.Name,
    ast.Call,
    ast.Subscript,
    ast.Constant,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.UnaryOp,
    ast.UAdd,
    ast.USub,
)


class ProductUomFieldRewriter(ast.NodeTransformer):
    """
    - Rewrites  product.foo -> product['foo']
    - Collects every field name accessed (through product.foo or product['foo'])
    (Same logic for 'uom')
    """

    SUB_ENTITIES = (("product.product", "product"), ("uom.uom", "uom"))

    def __init__(self) -> None:
        super().__init__()
        self.accessed_fields = defaultdict(set)

    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Name):
            for model, alias in self.SUB_ENTITIES:
                if node.value.id == alias:
                    assert isinstance(node.attr, str), "Attribute name must be a string"

                    self.accessed_fields[model].add(node.attr)

            return ast.Subscript(
                value=node.value,
                slice=ast.Constant(node.attr),
                ctx=node.ctx,
            )
        return node

    def visit_Subscript(self, node: ast.Subscript):
        node = self.generic_visit(node)
        if (
            isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            for model, alias in self.SUB_ENTITIES:
                if node.value.id == alias:
                    self.accessed_fields[model].add(node.slice.value)
        return node


class TaxFormulaValidator(ast.NodeVisitor):
    """
    Walks AST and rejects anything that is not needed or not reproducible in pyjs.

    The ast must be transformed by ProductUomFieldRewriter before being passed to this validator as
    this visitor does not whitelist Attribute nodes
    """

    def __init__(self, env) -> None:
        self.env = env
        super().__init__()

    def visit(self, node) -> None:
        if not isinstance(node, _NODE_WHITELIST):
            raise ValidationError(
                self.env._("Invalid AST node: %s", type(node).__name__)
            )
        super().visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, _ALLOWED_CONSTANT_T):
            raise ValidationError(
                self.env._("Only int, float or None are allowed as constant values")
            )

    def visit_Name(self, node: ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise ValidationError(self.env._("Unknown identifier: %s", str(node.id)))
        if not isinstance(node.ctx, ast.Load):
            raise ValidationError(
                self.env._("Only read access to identifiers is allowed")
            )

    def visit_Call(self, node: ast.Call):
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id in _ALLOWED_FUNCS
            and isinstance(node.func.ctx, ast.Load)
        ):
            raise ValidationError(self.env._("Unknown function call"))
        for arg in node.args:
            self.visit(arg)
        if node.keywords:
            raise ValidationError(self.env._("Kwargs are not allowed"))

    def visit_Subscript(self, node: ast.Subscript):
        if not (
            isinstance(node.value, ast.Name)
            and node.value.id in ("product", "uom")
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
            and isinstance(node.ctx, ast.Load)
        ):
            raise ValidationError(
                self.env._(
                    "Only product['string'] or uom['string'] read-access is allowed"
                )
            )

        self.visit(node.value)


def check_formula(env, formula: str) -> str:
    assert isinstance(formula, str), "Formula must be a string"

    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError, ValueError:
        raise ValidationError(env._("Invalid formula")) from None

    TaxFormulaValidator(env).visit(tree)


def normalize_formula(env, formula: str, field_predicate=None) -> tuple[str, set[str]]:
    assert isinstance(formula, str), "Formula must be a string"

    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError, ValueError:
        raise ValidationError(env._("Invalid formula")) from None

    transformer = ProductUomFieldRewriter()
    transformed_tree = transformer.visit(tree)
    ast.fix_missing_locations(
        transformed_tree
    )

    if callable(field_predicate):
        for model, fields in transformer.accessed_fields.items():
            for field in fields:
                if not field_predicate(model, field):
                    raise ValidationError(env._("Field '%s' is not accessible", field))

    return ast.unparse(transformed_tree), transformer.accessed_fields
