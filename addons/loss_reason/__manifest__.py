{
    "name": "Loss Reason Catalog",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Maintain reusable loss reasons with application and company scope",
    "description": "Adds ordered, archivable loss-reason records, seed data and configuration views. Reasons can be shared or scoped to sales, purchases or tasks and a company. Consumer applications implement document closing, reason selection and reporting.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.access.csv",
        "data/loss_reason_data.xml",
        "views/loss_reason_views.xml",
    ],
}
