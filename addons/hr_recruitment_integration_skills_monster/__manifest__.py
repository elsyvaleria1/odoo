{
    "name": "Monster Job Posting Skills",
    "version": "1.0",
    "category": "Human Resources/Recruitment/Integration",
    "summary": "Include configured job skill names in Monster posting payloads",
    "description": "Extends the Monster posting wizard to add JobSkills entries from the job skill records when present. Posting transport and credentials are supplied by the Monster integration; this addon does not discover or assess candidate skills.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_recruitment_skills",
        "hr_recruitment_integration_monster",
    ],
    "auto_install": True,
}
