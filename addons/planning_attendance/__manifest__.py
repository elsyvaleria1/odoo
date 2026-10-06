{
    "name": "Planning and Attendance Comparison",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 50,
    "summary": "Compare planned shift hours with recorded employee attendance",
    "description": "Adds a planning and attendance analysis report and reporting menus. Comparisons use stored planning slots and attendance records; the addon does not record attendance or infer work performed outside those records.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "planning",
        "hr_attendance",
    ],
    "data": [
        "security/ir.access.csv",
        "reports/planning_attendance_analysis_report_views.xml",
        "views/planning_attendance_menus.xml",
    ],
    "auto_install": True,
}
