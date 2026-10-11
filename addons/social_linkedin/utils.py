def urn_to_id(obj_urn):
    if not obj_urn:
        return ""
    if obj_urn.startswith("urn:li:comment") and "," in obj_urn:
        return obj_urn.split(",")[-1].rstrip(")")
    return obj_urn.split(":")[-1]


def id_to_urn(obj_id, name) -> str:
    return f"urn:{name}:{urn_to_id(obj_id)}" if obj_id else ""
