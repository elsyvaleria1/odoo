{
    "name": "Access Policy Tests",
    "version": "0.0.1",
    "category": "Hidden/Tests",
    "summary": "Test Access Policy behaviour, including ir access, verbs, separation of duties",
    "description": "Run regression tests for Access Policy. Loaded test suites include ``TestIrAccess``, ``TestAccessOperator``, ``TestDelegatedAccess``, ``TestRetiredAccessTables``, ``TestGroupsWithAccess``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "security/ir_access.xml",
    ],
}
