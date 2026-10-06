{
    "name": "Applicant CV Extraction",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Recruitment",
    "summary": "Fill eligible applicant contact fields from extracted CV information",
    "description": "Adds CV extraction eligibility and contact-field mapping to applicants in the first applicable recruitment stage. Uses the shared extraction framework and preserves populated contact information through its write rules. Requires a source CV and usable extraction strategy; skill assignment is provided by a separate bridge.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "LGPL-3",
    "depends": [
        "hr_recruitment",
        "extract",
    ],
    "data": [
        "views/hr_applicant_views.xml",
    ],
}
