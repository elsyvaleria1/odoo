import dataclasses


@dataclasses.dataclass(frozen=True)
class AddressProvider:
    """What `address_autocomplete` knows of a provider; its adapter knows the
    rest."""

    code: str
    label: str
    # the adapter model answering the provider's suggestions and details
    adapter: str
