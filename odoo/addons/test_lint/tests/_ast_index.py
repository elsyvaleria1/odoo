import ast


def walk_with_parents(tree: ast.AST) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        nodes.append(node)
        children = list(ast.iter_child_nodes(node))
        for child in children:
            child._parent = node
        stack.extend(reversed(children))
    tree._nodes = nodes
    return nodes


def nodes(tree: ast.AST) -> list[ast.AST]:
    # Every checker iterates the module once per run: the list is built on the
    # first request and kept on the tree, so the other checkers reuse it rather
    # than each paying an ast.walk.
    cached = getattr(tree, "_nodes", None)
    return cached if cached is not None else walk_with_parents(tree)
