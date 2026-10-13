import base64

from odoo import fields, models
from odoo.exceptions import UserError


class WizardL10nMxPostalCodeImport(models.TransientModel):
    _name = "wizard.l10n_mx.postal_code.import"
    _description = "Import the SEPOMEX Postal Code Catalogue"

    sepomex_file = fields.Binary(
        string="SEPOMEX catalogue",
        required=True,
        help="cpdescarga.txt as downloaded from Correos de México "
        "(https://www.correosdemexico.gob.mx/datosabiertos/cp/cpdescarga.txt). "
        "Its licence allows private use only, so each database imports it itself.",
    )
    sepomex_filename = fields.Char()

    def action_import(self) -> dict:
        self.check_singleton()
        content = base64.b64decode(self.sepomex_file)
        if b"d_codigo|" not in content[:4096]:
            raise UserError(
                self.env._(
                    "This is not the SEPOMEX catalogue: its header line starts "
                    "with d_codigo|. Download cpdescarga.txt from Correos de México."
                )
            )
        counts = (
            self.env["l10n_mx.postal_code"]
            .with_privilege(
                "l10n_mx_partner.privilege_maintain_l10n_mx_catalogue",
                reason="import the SEPOMEX catalogue",
            )
            ._import_sepomex(content)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("SEPOMEX catalogue imported"),
                "message": self.env._(
                    "%(created)s settlements created, %(linked)s linked to their "
                    "municipality, %(unknown)s rows with an unknown state skipped.",
                    created=counts["created"],
                    linked=counts["linked"],
                    unknown=counts["unknown_state"],
                ),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
