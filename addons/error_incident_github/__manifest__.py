{
    "name": "Error Incidents on GitHub",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "summary": "Follow the pull requests that fix an incident on the incident itself",
    "description": "Links a pull request to the agent run that pushed its branch and to the incident that run works for, by the branch -- never by matching error signatures. The incident's chatter hears when the pull request opens, its checks pass or fail, and it is merged or closed.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "agent_runner_github",
        "error_incident",
    ],
    "data": [
        "views/error_incident_views.xml",
    ],
}
