{
    "name": "Attachment Text Indexing",
    "version": "2.1",
    "category": "Hidden/Tools",
    "summary": "Extract searchable text from supported document attachments",
    "description": "Index text from PDF, office-document and spreadsheet attachments. Available formats depend on the installed extraction libraries; PDF extraction uses pdfminer.six.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "external_dependencies": {
        "python": [
            "defusedxml",
        ],
        "apt": {
            "defusedxml": "python3-defusedxml",
        },
    },
}
