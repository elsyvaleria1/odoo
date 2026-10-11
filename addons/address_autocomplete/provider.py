import dataclasses


@dataclasses.dataclass(frozen=True)
class AddressProvider:

    code: str
    label: str
    adapter: str
