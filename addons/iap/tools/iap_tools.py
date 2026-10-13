DEFAULT_ENDPOINT = "https://iap.odoo.com"


_STATES_FILTER_COUNTRIES_WHITELIST = {
    "AR",
    "AU",
    "BR",
    "CA",
    "IN",
    "MY",
    "MX",
    "NZ",
    "AE",
    "US",
}


def iap_get_endpoint(env):
    return env.registry.settings.get(env, "iap.endpoint", DEFAULT_ENDPOINT)
