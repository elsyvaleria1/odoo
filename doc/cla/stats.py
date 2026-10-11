#!/usr/bin/python
import pathlib
import re
import subprocess

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
    p = subprocess.Popen(
        "git ls-tree -r -z --name-only HEAD | grep -z '.%s$' | xargs -0 -n1 git blame --line-porcelain HEAD |grep  '^author-mail ' |sort |uniq -c|sort -nr"
        % ext,
        shell=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    for i in p.stdout.read().split("\n"):
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
