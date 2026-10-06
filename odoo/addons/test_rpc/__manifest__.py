{
    "name": "RPC Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test RPC behaviour, including rpc path, error, authority keys",
    "description": "Run regression tests for RPC. Loaded test suites include ``TestRpcPath``, ``TestError``, ``TestAuthorityKeyRegistry``, ``TestAuthorityKeyDoors``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
        "rpc",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
