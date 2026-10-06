{
    "name": "Error Incidents on GitHub",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "summary": "Follow the pull requests that fix an incident, and hand each run a token for its repository alone",
    "description": "Links a pull request to the agent run that pushed its branch and to the incident that run works for, by the branch -- never by matching error signatures. The incident's chatter hears when the pull request opens, its checks pass or fail, and it is merged or closed. A run that names a repository is handed, with its lease, a GitHub App installation token limited to that repository and to the permissions a fix needs, which expires within the hour.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "agent_runner",
        "error_incident",
        "integration_github",
    ],
    "data": [
        "views/error_incident_views.xml",
        "views/agent_run_views.xml",
    ],
}
