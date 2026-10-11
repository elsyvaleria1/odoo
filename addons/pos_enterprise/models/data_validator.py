def object_of(schema):

    def object_validator(value):
        if not isinstance(value, dict):
            return False, "not an object"

        for key, expected in schema.items():
            if expected and key not in value:
                return False, f"Missing key '{key}'"

            if callable(expected):
                valid, error = expected(value[key])
                if not valid:
                    return False, error

        return True, None

    return object_validator


def list_of(schema):

    def list_validator(value):
        if not isinstance(value, list):
            return False, "not a list"

        for item in value:
            if callable(schema):
                valid, error = schema(item)
                if not valid:
                    return False, error
            elif schema is True:
                continue
            else:
                return False, "can't be list_of(False)"

        return True, None

    return list_validator
