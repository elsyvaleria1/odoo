import re
from typing import Literal

_PREFIX_SEPARATOR = re.compile(r"[,;]")


def split_account_prefixes(
    account_prefix: str | Literal[False] | None,
) -> tuple[str, ...]:
    compact = "".join((account_prefix or "").split())
    return tuple(prefix for prefix in _PREFIX_SEPARATOR.split(compact) if prefix)


def get_account_prefix_placeholder(env, account_type: str, fallback: str) -> str:
    account = env["account.account"].search(
        [
            *env["account.account"]._get_domain_company_compatible(env.company),
            ("account_type", "=", account_type),
        ],
        limit=1,
    )
    prefixes = fallback
    try:
        prefix_num = int((account.code or "")[:2])
    except ValueError:
        pass
    else:
        prefixes = f"{prefix_num}, {prefix_num + 1}, {prefix_num + 2}"
    return env._("e.g. %(prefix)s", prefix=prefixes)
