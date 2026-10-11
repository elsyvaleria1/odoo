def snake_case_to_camel_case(snake_case: str) -> str:
    parts = snake_case.split("_")
    converted = parts[0].lower() + "".join(part.title() for part in parts[1:])

    converted = converted.replace("Json", "JSON")

    return converted
