import dataclasses


@dataclasses.dataclass(frozen=True)
class CaptchaProvider:
    """What `captcha` knows of a provider; its adapter knows the rest."""

    code: str
    label: str
    adapter: str
