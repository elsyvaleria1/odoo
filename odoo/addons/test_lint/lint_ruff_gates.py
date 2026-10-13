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

NOT_OURS = ("**/_vendor/**", "**/upgrades/**", "**/migrations/**")
LINK_DOORS = (
    "odoo/addons/base/models/access_link.py",
    "odoo/addons/base/models/mixin_bearer_token.py",
    "odoo/tools/security.py",
)
UNSUPPRESSABLE = ("E8535",)


def ignores(repo: str) -> str:
    entries = {glob: ["E85"] for glob in NOT_OURS}
    if repo == "odoo":
        entries |= {door: ["E8537"] for door in LINK_DOORS}
    body = ", ".join(
        f"{json.dumps(glob)} = {json.dumps(codes)}" for glob, codes in entries.items()
    )
    return f"lint.extend-per-file-ignores = {{{body}}}"


def get_findings(ruff: str, root: Path, repo: str, *extra: str) -> list[dict]:
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


def unformatted(ruff: str, root: Path) -> list[tuple[str, str]]:
    from odoo.libs.json import loads as json_loads

    root = root.resolve()
    result = subprocess.run(
        [ruff, "format", "--check", "--no-cache", "--output-format", "json", "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode > 1 and not result.stdout:
        sys.exit(f"ruff format failed in {root}:\n{result.stderr}")
    return sorted(
        {
            (Path(row["filename"]).relative_to(root).as_posix(), row["message"])
            for row in json_loads(result.stdout or "[]")
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruff", default=str(Path(sys.executable).with_name("ruff")))
    parser.add_argument("--workspace", type=Path, default=CHECKOUT.parent)
    args = parser.parse_args()
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
    unformatted_files = []
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
            for row in get_findings(args.ruff, root, repo, "--select", "E85")
            if row["code"] not in UNSUPPRESSABLE
        ]
        rows += get_findings(
            args.ruff, root, repo, "--select", ",".join(UNSUPPRESSABLE), "--ignore-noqa"
        )
        for row in rows:
            if row["code"] in names:
                counts[f"lint_{names[row['code']].replace('-', '_')}_{repo}"] += 1
        unformatted_files += [
            (repo, path, message) for path, message in unformatted(args.ruff, root)
        ]

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
    for repo, path, message in unformatted_files:
        _logger.error("ruff format: %s/%s: %s", repo, path, message)
    _logger.info(
        "ruff format gate: %d files unformatted over %s",
        len(unformatted_files),
        ", ".join(scanned),
    )
    return 1 if failed or unformatted_files else 0


if __name__ == "__main__":
    sys.exit(main())
