{
    "name": "Survey Lead Generation",
    "version": "1.0",
    "category": "Marketing/Surveys",
    "summary": "Create leads from survey responses containing configured lead-generating answers",
    "description": "Adds lead-generation flags to suggested answers and CRM settings to surveys. Completion of supported survey types creates leads for responses selecting a flagged answer, using response and survey values; also connects live-session completion and lead navigation.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "survey",
        "crm",
    ],
    "data": [
        "views/survey_question_views.xml",
        "views/survey_survey_views.xml",
        "views/survey_user_views.xml",
    ],
    "demo": [
        "demo/lead_qualification_survey_demo.xml",
        "demo/lead_qualification_answer_demo.xml",
    ],
    "auto_install": True,
}
