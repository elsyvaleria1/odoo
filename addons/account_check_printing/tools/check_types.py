from typing import Literal, TypedDict


class CheckAddressValues(TypedDict):
    company_street: str
    company_city_state: str
    company_name: str | Literal[False]
    company_logo: str | bytes | Literal[False]
    bank_name: str | Literal[False]
    bank_street: str
    bank_city_state: str
    bank_routing: str | Literal[False]
    partner_street: str
    partner_city_state: str
