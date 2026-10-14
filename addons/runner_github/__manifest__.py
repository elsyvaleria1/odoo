{
    "name": "Runners on GitHub",
    "version": "19.0.2.0.0",
    "category": "Hidden/Tools",
    "summary": "Hand a runner job a token for its repository alone, and follow the pull request of the branch it pushed",
    "description": "A job that names a GitHub repository is handed, with its lease, an installation token of the company's GitHub App limited to that repository and to the permissions its kind needs, which expires within the hour. When it completes it reports the branch it pushed, and the pull request of that branch is linked to it -- whichever GitHub or the runner reports first. The modules that hand out work react to the link.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "runner",
        "integration_github",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "views/runner_job_views.xml",
    ],
}
