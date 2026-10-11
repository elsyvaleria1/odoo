def extend_serialized_json(json: str, key_value_pairs: list) -> str:
    parts = [json.removesuffix("}")]
    if json != "{}":
        parts.append(",")
    for i, (key, value) in enumerate(key_value_pairs):
        parts.extend([f'"{key}":', value])
        if i != len(key_value_pairs) - 1:
            parts.append(",")
    parts.append("}")
    return "".join(parts)
