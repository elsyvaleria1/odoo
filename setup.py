#!/usr/bin/env python

import pathlib
import runpy

from setuptools import find_namespace_packages, setup

release = runpy.run_path(str(pathlib.Path(__file__).parent / "odoo" / "release.py"))
lib_name = "odoo"

LONG_DESCRIPTION = """\
Odoo is a complete ERP and CRM. The main features are accounting (analytic
and financial), stock management, sales and purchases management, tasks
automation, marketing campaigns, help desk, POS, etc. Technical features include
a distributed server, an object database, a dynamic GUI,
customizable reports, and XML-RPC interfaces.
"""

CLASSIFIERS = [
    "Development Status :: 5 - Production/Stable",
    "Programming Language :: Python",
]

setup(
    name="odoo",
    version=release["version"],
    description=release["description"],
    long_description=LONG_DESCRIPTION,
    url=release["url"],
    author=release["author"],
    author_email="info@odoo.com",
    classifiers=CLASSIFIERS,
    license="LGPL-3.0-only AND 0BSD",
    scripts=["setup/odoo"],
    packages=find_namespace_packages(include=["odoo*", "addons*"]),
    package_dir={"%s" % lib_name: "odoo"},
    include_package_data=True,
    install_requires=[
        "asn1crypto",
        "babel >= 1.0",
        "beautifulsoup4",
        "blake3",
        "cbor2",
        "cryptography",
        "cssselect2",
        "docutils",
        "fonttools",
        "geoip2",
        "idna",
        "lxml",
        "lxml_html_clean",
        "MarkupSafe",
        "maxminddb",
        "num2words",
        "orjson",
        "packaging",
        "pillow",
        "polib",
        "protobuf >= 6.31.0, < 8",
        "psutil",
        "psycopg[binary] >= 3.3.4",
        "psycopg-pool >= 3.3.1",
        "pyopenssl",
        "pypdf",
        "python-dateutil",
        "python-magic ; sys_platform != 'win32'",
        "reportlab",
        "rjsmin",
        "requests",
        "rl-renderPM ; sys_platform == 'win32'",
        "rlPyCairo",
        "urllib3",
        "weasyprint",
        "werkzeug",
        "xlsxwriter",
    ],
    python_requires=">=" + ".".join(map(str, release["MIN_PY_VERSION"])),
    extras_require={
        "ldap": ["python-ldap"],
        "pdf-raster": ["PyMuPDF"],
        "scaffold": ["Jinja2"],
        "addons": [
            "chardet",
            "defusedxml",
            "google-auth",
            "odfpy",
            "openpyxl",
            "pdfminer.six",
            "phonenumbers",
            "PyMuPDF",
            "python-ldap ; sys_platform != 'win32'",
            "python-stdnum",
            "qrcode",
            "vobject",
            "xlrd",
            "zeep",
        ],
    },
)
