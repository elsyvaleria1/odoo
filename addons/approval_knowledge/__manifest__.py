{
    "name": "Knowledge Article Access Requests",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Request article read or edit access through approval",
    "description": "Adds article access-request pages and an approval adapter that invites the requester with the granted role. The supplied category uses internal article editors and system administrators as reviewers; eligibility depends on the article request route and existing permissions.",
    "author": "AgroMarin",
    "license": "OEEL-1",
    "depends": [
        "approval",
        "knowledge",
    ],
    "data": [
        "data/approval_category_data.xml",
        "views/knowledge_templates.xml",
    ],
    "auto_install": True,
}
