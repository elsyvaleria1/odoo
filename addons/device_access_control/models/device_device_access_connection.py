from urllib.parse import urlparse

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.integration.tools import is_private_host


class DeviceDevice(models.Model):
    _inherit = "device.device"

    @api.model
    def _connection_fields(self):
        return super()._connection_fields() | {
            "access_connection_mode",
            "ehome_bridge_url",
            "ehome_device_id",
        }

    def _access_services(self) -> dict:
        return {
            "ehome": self.env.ref(
                "device_access_control.service_ehome_bridge", raise_if_not_found=False
            ),
            "direct": self.env.ref(
                "device_access_control.service_isapi_device", raise_if_not_found=False
            ),
        }

    def _dials_as_access_panel(self) -> bool:
        self.check_singleton()
        if self.access_connection_mode == "ehome":
            return bool(self.ehome_device_id)
        return bool(self.sudo().dial_credential_id)

    def _connection_service(self):
        self.check_singleton()
        if not self._dials_as_access_panel():
            return super()._connection_service()
        return self._access_services().get(self.access_connection_mode)

    def _connection_values(self, service) -> dict | None:
        self.check_singleton()
        if not self._dials_as_access_panel():
            return super()._connection_values(service)
        if not service:
            return None
        if self.access_connection_mode == "ehome":
            if not self.ehome_device_id:
                return None
            base_url = self._get_ehome_api_url()
            credential = self.env["credential.credential"]
        else:
            credential = self.sudo().dial_credential_id
            if not self.endpoint or not credential:
                return None
            base_url = f"https://{self.endpoint}"
            host = urlparse(base_url).hostname or ""
            if not service.verify_tls and not is_private_host(host):
                return None
        return {
            "name": self.name,
            "service_id": service.id,
            "credential_id": credential.id,
            "company_id": self.company_id.id,
            "environment": service.environment,
            "base_url": base_url,
            "active": self.active,
            "res_model": self._name,
            "res_id": self.id,
        }

    def _require_connection(self):
        connection = self._get_connection()
        if connection:
            return connection
        if (
            self.access_connection_mode == "direct"
            and self.endpoint
            and self.sudo().dial_credential_id
        ):
            raise UserError(
                self.env._(
                    "Refusing to call '%(host)s' with TLS verification disabled: it "
                    "is not a private-network host, so the panel's login would be "
                    "exposed to whoever answers.",
                    host=urlparse(f"https://{self.endpoint}").hostname or self.endpoint,
                )
            )
        return super()._require_connection()

    def http_read_data(self):
        # A dialled panel has no data at its connection's root, and an EHOME
        # bridge answers its root with a 404: reading a panel is checking that
        # it answers, the bridge's device list or the panel's deviceInfo.
        if not self.is_access_device:
            return super().http_read_data()
        if self.access_connection_mode == "ehome":
            self._check_ehome_connection()
        else:
            self._check_direct_connection()
        if self.connection_state != "connected":
            return None
        return {"connection_state": self.connection_state}
