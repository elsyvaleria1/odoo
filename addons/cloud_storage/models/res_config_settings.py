from odoo import api, fields, models
from odoo.exceptions import UserError

DEFAULT_CLOUD_STORAGE_MIN_FILE_SIZE = 20_000_000


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cloud_storage_provider = fields.Selection(
        selection=[],
        string="Cloud Storage Provider for new attachments",
        config_parameter="cloud_storage_provider",
    )

    cloud_storage_min_file_size_mb = fields.Float(string="Minimum File Size (MB)")

    cloud_storage_min_file_size = fields.Integer(
        string="Minimum File Size (bytes)",
        default=DEFAULT_CLOUD_STORAGE_MIN_FILE_SIZE,
        config_parameter="cloud_storage_min_file_size",
        help="""webclient can upload files larger than the minimum file size
        (in bytes) as url attachments to the server and then upload the file to
        the cloud storage.""",
    )

    def _setup_cloud_storage_provider(self):
        pass

    def _get_cloud_storage_configuration(self):
        return {}

    def _check_cloud_storage_uninstallable(self):
        pass

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"]
        res["cloud_storage_min_file_size_mb"] = (
            int(
                ICP.get_param(
                    "cloud_storage_min_file_size", DEFAULT_CLOUD_STORAGE_MIN_FILE_SIZE
                )
            )
            / 1000000
        )
        return res

    def set_values(self):
        ICP = self.env["ir.config_parameter"]
        cloud_storage_configuration_before = self._get_cloud_storage_configuration()
        cloud_storage_provider_before = ICP.get_param("cloud_storage_provider")
        if (
            cloud_storage_provider_before
            and self.cloud_storage_provider != cloud_storage_provider_before
        ):
            self._check_cloud_storage_uninstallable()
        self.cloud_storage_min_file_size = int(
            self.cloud_storage_min_file_size_mb * 1000000
        )
        super().set_values()
        cloud_storage_configuration = self._get_cloud_storage_configuration()
        if not cloud_storage_configuration and self.cloud_storage_provider:
            raise UserError(
                self.env._("Please configure the Cloud Storage before enabling it")
            )
        if (
            cloud_storage_configuration
            and cloud_storage_configuration != cloud_storage_configuration_before
        ):
            self._setup_cloud_storage_provider()
