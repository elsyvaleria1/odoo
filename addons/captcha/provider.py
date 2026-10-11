import dataclasses


@dataclasses.dataclass(frozen=True)
class CaptchaProvider:

    code: str
    label: str
    adapter: str
