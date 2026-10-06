{
    "name": "Enterprise Digest Data",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Load additional digest configuration for enterprise applications",
    "description": "Extend the digest configuration through the supplied data records. Metric computation and email delivery are provided by the digest applications.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "web",
        "digest",
    ],
    "data": [
        "data/digest_data.xml",
    ],
    "auto_install": True,
}
