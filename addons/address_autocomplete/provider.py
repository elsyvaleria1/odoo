import dataclasses


@dataclasses.dataclass(frozen=True)
class AddressProvider:
    """What `address_autocomplete` knows of a provider; its adapter knows the
    rest."""

    code: str
    label: str
    adapter: str
