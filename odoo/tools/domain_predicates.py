import operator

SET_DOMAIN_OPERATORS = frozenset({"in", "not in"})

DOMAIN_PREDICATES = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "in": lambda element, container: element in container,
    "not in": lambda element, container: element not in container,
}
