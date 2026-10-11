#!/usr/bin/python
import pathlib
import re
import subprocess
from collections import Counter

cla_glob = "doc/cla/*/*.md"
cla = "".join(
    path.read_text(encoding="utf-8") for path in pathlib.Path().glob(cla_glob)
)
cla = cla.lower()


def cla_signed(email: str) -> bool:
    return bool(re.match(r".*(odoo|openerp|tinyerp).com$", email)) or email in cla


def blamestat(ext: str = "py") -> None:
    ok = 0
    okl: list[str] = []
    ko = 0
    kol: list[str] = []
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    counts: Counter[str] = Counter()
    for filename in listing.stdout.split("\0"):
        if not filename.endswith(f".{ext}"):
            continue
        blame = subprocess.run(
            ["git", "blame", "--line-porcelain", "HEAD", "--", filename],
            capture_output=True,
            text=True,
            check=True,
        )
        counts.update(
            line
            for line in blame.stdout.splitlines()
            if line.startswith("author-mail ")
        )
    for author, count in sorted(
        counts.items(), key=lambda item: (item[1], item[0]), reverse=True
    ):
        i = f"{count} {author}"
        mo = re.search(r"(\d+) author-mail <([^ @<]+@[^ @<]+)>", i)
        if mo:
            lines = int(mo.group(1))
            email = mo.group(2)
            if cla_signed(email):
                ok += lines
                okl.append(i)
            else:
                ko += lines
                kol.append(i)
    print("-" * 60)
    print("Stats for ", ext)
    print("-" * 60)
    print("\nCLA SIGNED %s/%s (%.0f%%)" % (ok, ok + ko, ok * 100.0 / (ok + ko)))
    for i in okl:
        print(i)

    print("\nCLA MISSING %s/%s (%.0f%%)\n" % (ko, ok + ko, ko * 100.0 / (ok + ko)))
    for i in kol:
        print(i)
    print()
    print()


blamestat("md")
blamestat("rst")
blamestat("py")
blamestat("js")
blamestat("xml")
blamestat("csv")
