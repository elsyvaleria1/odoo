from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(
        cr,
        "agro_surface_l10n_mx_map_account_marin",
        "l10n_mx_agro_surface_map_account_marin",
    )
    rename_module(
        cr,
        "approval_account_l10n_mx_edi_telegram",
        "l10n_mx_edi_approval_account_telegram",
    )
    rename_module(
        cr, "agro_surface_l10n_mx_map_account", "l10n_mx_agro_surface_map_account"
    )
    rename_module(
        cr, "agro_surface_l10n_mx_map_threed", "l10n_mx_agro_surface_map_threed"
    )
    rename_module(cr, "approval_account_l10n_mx_edi", "l10n_mx_edi_approval_account")
    rename_module(cr, "document_l10n_be_hr_payroll", "l10n_be_hr_payroll_document")
    rename_module(cr, "document_l10n_ch_hr_payroll", "l10n_ch_hr_payroll_document")
    rename_module(cr, "document_l10n_hk_hr_payroll", "l10n_hk_hr_payroll_document")
    rename_module(cr, "document_l10n_ke_hr_payroll", "l10n_ke_hr_payroll_document")
    rename_module(cr, "agro_surface_l10n_mx_map", "l10n_mx_agro_surface_map")
    rename_module(cr, "agro_surface_l10n_mx", "l10n_mx_agro_surface")
    rename_module(cr, "document_l10n_mx_edi", "l10n_mx_edi_sat_import")
    rename_module(cr, "geoengine_l10n_mx", "l10n_mx_geoengine")
    rename_module(cr, "partner_l10n_mx", "l10n_mx_partner")
