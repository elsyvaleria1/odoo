from . import controllers
from . import models


def post_init_hook(env) -> None:
    names = ["Autos", "Camionetas", "Torton", "Tractor", "Maquinaria"]
    tag_model = env["product.tag"]
    for index, name in enumerate(names, start=1):
        tag = tag_model.search([("name", "=", name)], limit=1)
        if tag:
            tag.visible_to_customers = True
        else:
            tag_model.create(
                {"name": name, "visible_to_customers": True, "sequence": index * 10}
            )
