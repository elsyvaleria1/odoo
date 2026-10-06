# The Odoo rules of the ruff fork (`E85`, Agro-Marin/ruff) held to test_lint's
# floors: each `lint_<rule name>_<repo>` in tests/floors.json is the exact count
# of that rule's unsuppressed findings in that repository, counted here with
# `ruff check --select E85` under the repository's own ruff.toml.
#
#   python odoo/addons/test_lint/lint_ruff_gates.py [--ruff <binary>] [--workspace <dir>]
#
# The siblings are read from --workspace (default: beside this checkout), so a
# worktree of this checkout still finds them.
#
# Exit 1 when a count is off its floor, or when the ruff given is not the fork.
import argparse
import collections
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[2]
FLOORS = HERE / "tests" / "floors.json"
_logger = logging.getLogger("odoo.addons.test_lint.ruff_gates")

# test_lint's corpus leaves out vendored code and migration scripts. Kept out of
# the repositories' ruff.toml: a stock ruff, as an editor bundles, refuses an
# E85 code there.
NOT_OURS = ("**/_vendor/**", "**/upgrades/**", "**/migrations/**")
# The doors that compare a bearer token by design: access.link's resolver and
# mixin.bearer.token's store (link-token-compare's own exemption).
LINK_DOORS = (
    "odoo/addons/base/models/access_link.py",
    "odoo/addons/base/models/mixin_bearer_token.py",
    "odoo/tools/security.py",
)
# Counted with every noqa ignored: a call to a removed method cannot be waived.
UNSUPPRESSABLE = ("E8535",)


def ignores(repo: str) -> str:
    entries = {glob: ["E85"] for glob in NOT_OURS}
    if repo == "odoo":
        entries |= {door: ["E8537"] for door in LINK_DOORS}
    body = ", ".join(
        f"{json.dumps(glob)} = {json.dumps(codes)}" for glob, codes in entries.items()
    )
    return f"lint.extend-per-file-ignores = {{{body}}}"


def findings(ruff: str, root: Path, repo: str, *extra: str) -> list[dict]:
    from odoo.libs.json import loads as json_loads

    result = subprocess.run(
        [
            ruff,
            "check",
            "--no-cache",
            "--exit-zero",
            "--output-format",
            "json",
            "--config",
            ignores(repo),
            *extra,
            ".",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        sys.exit(f"ruff failed in {root}:\n{result.stderr}")
    return json_loads(result.stdout or "[]")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruff", default=str(Path(sys.executable).with_name("ruff")))
    parser.add_argument("--workspace", type=Path, default=CHECKOUT.parent)
    args = parser.parse_args()
    # each repository is checked from its own root, so a relative path to ruff
    # is anchored here first
    ruff = shutil.which(args.ruff)
    if ruff is None:
        sys.exit(f"no ruff at {args.ruff}")
    args.ruff = str(Path(ruff).resolve())
    sys.path.insert(0, str(CHECKOUT))
    from odoo.libs.json import loads as json_loads
    from odoo.logutils import init_logger

    init_logger()

    listing = subprocess.run(
        [args.ruff, "rule", "--all", "--output-format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    names = {
        rule["code"]: rule["name"]
        for rule in json_loads(listing.stdout or "[]")
        if (rule.get("code") or "").startswith("E85")
    }
    if not names:
        sys.exit(
            f"{args.ruff} knows no E85 rule: it is not the Agro-Marin/ruff fork "
            "that requirements-dev.txt pins"
        )

    counts: collections.Counter[str] = collections.Counter()
    scanned = []
    repositories = {
        "odoo": CHECKOUT,
        "l10n": args.workspace / "l10n",
        "agromarin": args.workspace / "agromarin",
    }
    for repo, root in repositories.items():
        if not root.is_dir():
            _logger.info("skipped %s: no %s", repo, root)
            continue
        scanned.append(repo)
        rows = [
            row
            for row in findings(args.ruff, root, repo, "--select", "E85")
            if row["code"] not in UNSUPPRESSABLE
        ]
        rows += findings(
            args.ruff, root, repo, "--select", ",".join(UNSUPPRESSABLE), "--ignore-noqa"
        )
        for row in rows:
            counts[f"lint_{names[row['code']].replace('-', '_')}_{repo}"] += 1

    floors = json_loads(FLOORS.read_text())
    gates = {
        f"lint_{name.replace('-', '_')}_{repo}"
        for name in names.values()
        for repo in scanned
    }
    failed = [gate for gate in sorted(gates) if counts[gate] != floors.get(gate, 0)]
    for gate in failed:
        _logger.error(
            "%s: %d findings, floor %d", gate, counts[gate], floors.get(gate, 0)
        )
    _logger.info(
        "ruff E85 gates: %d checked over %s, %d off their floor",
        len(gates),
        ", ".join(scanned),
        len(failed),
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
