{
    "name": "Applicant CV Skill Extraction",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Recruitment",
    "summary": "Match extracted CV skill names to existing applicant skill catalog entries",
    "description": "Adds applicant skills from extraction results using exact case-insensitive catalog-name matching. Leaves existing applicant skills and levels unchanged, ignores unknown names and skips skills without a level; new entries use the default level or the first available level. CV reading comes from the extraction dependency.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "LGPL-3",
    "depends": [
        "extract_hr_recruitment",
        "hr_recruitment_skills",
    ],
    "auto_install": True,
}
