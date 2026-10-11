{
    "name": "Team Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test Team behaviour, including team usage, team install, access binds",
    "description": "Run regression tests for Team. Loaded test suites include ``TestTeamUsage``, ``TestSalesTeamRulesRemoved``, ``TestTeamAccessBind``.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "team",
    ],
    "data": [
        "security/test_team_security.xml",
        "security/ir.access.csv",
    ],
}
