{
    "name": "Translation Import Tests",
    "version": "0.1",
    "category": "Hidden/Tests",
    "summary": "Test Translation Import behaviour, including export wizard, term count",
    "description": "Run regression tests for Translation Import. Loaded test suites include ``TestTranslationFlow``, ``TestImport``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.access.csv",
        "view.xml",
        "views/test_translation_import_menus.xml",
        "data/test_translation_import_data.xml",
        "data/test.translation.import.model1.csv",
        "data/test.translation.import.model1-translated.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "test_translation_import/static/src/xml/js_templates.xml",
        ],
    },
}
