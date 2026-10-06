ISAPI_NS = {"ns": "http://www.isapi.org/ver20/XMLSchema"}


def _namespaced(path):
    prefix = ".//" if path.startswith(".//") else ""
    steps = path[len(prefix) :].split("/")
    return prefix + "/".join(f"ns:{step}" if step else step for step in steps)


def find_element(element, path):
    if element is None:
        return None
    node = element.find(_namespaced(path), ISAPI_NS)
    if node is None:
        node = element.find(path)
    return node


def find_text(element, path, default=""):
    node = find_element(element, path)
    if node is None or not node.text:
        return default
    return node.text.strip()
