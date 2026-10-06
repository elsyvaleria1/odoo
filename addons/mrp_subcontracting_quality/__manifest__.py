{
    "name": "Subcontracting Quality Cleanup",
    "version": "1.0",
    "category": "Supply Chain/Quality",
    "summary": "Handle quality-check removal on subcontracting stock lines",
    "description": "Extend stock move line quality-check cleanup for subcontracting. Uses the manufacturing subcontracting and quality-control flows supplied by its dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "mrp_subcontracting",
        "quality_control",
    ],
    "auto_install": True,
}
