{
    "name": "Rule Scripts",
    "version": "19.0.1.1.0",
    "category": "Hidden/Tools",
    "summary": "Keep legal and business rules as dated, tested, versioned Python scripts",
    "description": "Stores rules as small Python scripts written in a restricted grammar: UPPERCASE literal constants and one evaluate(inputs, rules) function with no imports, no loops but for, no attribute names starting with an underscore, no method calls, and no clock, records or I/O. Each rule has dated versions; no two active versions of a rule overlap (a PostgreSQL exclusion constraint, with btree_gist), an active version is immutable, and activation requires every test of its dates to pass and its calls to name existing rules without a cycle. Callers evaluate a rule by code at a date, and can keep the evaluation behind a document's figure as a rule trace: the versions used, nested calls included, with inputs and value, read-only and created only through a privilege. Modules ship rules as files under rules/, loaded as versions on install and update; a local version is activated by a rule approver other than its author.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "security/rule_script_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/rule_script_version_views.xml",
        "views/rule_script_views.xml",
        "views/rule_script_test_views.xml",
        "views/rule_script_trace_views.xml",
        "data/menuitems.xml",
    ],
}
