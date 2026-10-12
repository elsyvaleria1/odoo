import logging

from odoo import api, fields, models, modules, tools
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class GeocoderProvider(models.Model):
    _name = "geocoder.provider"
    _description = "Geocoding Provider"

    tech_name = fields.Char(string="Technical Name")
    name = fields.Char()


class Geocoder(models.AbstractModel):
    _name = "geocoder"
    _description = "Geocoder"

    @api.model
    def _get_provider(self):
        prov_id = self.env.registry.settings.get(
            self.env, "geocoding.geo_provider", False
        )
        provider = self.env["geocoder.provider"]
        if prov_id:
            try:
                provider = self.env["geocoder.provider"].browse(int(prov_id))
            except ValueError:
                provider = self.env["geocoder.provider"]
        if not prov_id or not provider.exists():
            provider = self.env["geocoder.provider"].search([], limit=1)
        return provider

    @api.model
    def geo_query_address(
        self, street=None, zip_code=None, city=None, state=None, country=None
    ):
        provider = self._get_provider().tech_name
        formatter = self._get_geo_address_formatters().get(provider)
        if formatter:
            return formatter(street, zip_code, city, state, country)
        else:
            return self._geo_query_address_default(
                street=street,
                zip_code=zip_code,
                city=city,
                state=state,
                country=country,
            )

    @api.model
    def geo_find(self, addr, **kw):
        provider = self._get_provider().tech_name
        service = self._get_geo_services().get(provider)
        if not service:
            raise UserError(
                self.env._(
                    "Provider %s is not implemented for geolocation service.", provider
                )
            )
        try:
            result = service(addr, **kw)
        except UserError:
            raise
        except Exception:
            _logger.debug("Geolocalize call failed", exc_info=True)
            result = None
        return result

    @api.model
    def _get_geo_services(self) -> dict:
        return {
            "openstreetmap": self._call_openstreetmap,
            "googlemap": self._call_googlemap,
        }

    @api.model
    def _get_geo_address_formatters(self) -> dict:
        return {"googlemap": self._geo_query_address_googlemap}

    @api.model
    def _call_openstreetmap(self, addr, **kw) -> tuple | None:
        if not addr:
            _logger.info("invalid address given")
            return None
        url = "https://nominatim.openstreetmap.org/search"
        try:
            headers = {"User-Agent": "Odoo (http://www.odoo.com/contactus)"}
            response = self.env["ir.egress"].request(
                "GET",
                url,
                purpose="geocoding",
                headers=headers,
                params={"format": "json", "q": addr},
                timeout=10,
            )
            _logger.info("openstreetmap nominatim service called")
            if response.status_code != 200:
                _logger.warning(
                    "Request to openstreetmap failed.\nCode: %s\nContent: %s",
                    response.status_code,
                    response.content,
                )
                raise ValueError("Nominatim returned HTTP %s" % response.status_code)
            result = response.json()
        except (OSError, ValueError) as e:
            self._raise_query_error(e)
        if not result:
            return None
        geo = result[0]
        return float(geo["lat"]), float(geo["lon"])

    @api.model
    def _call_openstreetmap_reverse(self, lat, lon):
        if not (lat and lon):
            _logger.info("invalid latitude or longitude given")
            return None
        if tools.config["test_enable"] or modules.module.current_test:
            raise UserError(
                self.env._("OpenStreetMap calls disabled in testing environment.")
            )
        try:
            headers = {"User-Agent": "Odoo (http://www.odoo.com/contactus)"}
            response = self.env["ir.egress"].request(
                "GET",
                "https://nominatim.openstreetmap.org/reverse",
                purpose="geocoding",
                headers=headers,
                params={"format": "json", "lat": lat, "lon": lon},
                timeout=10,
            )
            _logger.info("openstreetmap nominatim service called")
            if response.status_code != 200:
                _logger.warning(
                    "Request to openstreetmap failed.\nCode: %s\nContent: %s",
                    response.status_code,
                    response.content,
                )
                raise ValueError("Nominatim returned HTTP %s" % response.status_code)
            result = response.json()
        except (OSError, ValueError) as e:
            self._raise_query_error(e)
        return result

    @api.model
    def _call_googlemap(self, addr, **kw) -> tuple | None:
        apikey = self.env["credential.credential"]._get_system_secret(
            "geocoding.google_map_api_key"
        )
        if not apikey:
            raise UserError(
                self.env._(
                    "API key for GeoCoding (Places) required.\n"
                    "Visit https://developers.google.com/maps/documentation/geocoding/get-api-key for more information."
                )
            )
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"sensor": "false", "address": addr, "key": apikey}
        if kw.get("force_country"):
            country = self.env["res.country"].search(
                [("name", "=", kw["force_country"])], limit=1
            )
            params["components"] = "country:%s" % (
                country.code if country else kw["force_country"]
            )
        try:
            response = self.env["ir.egress"].request(
                "GET", url, purpose="geocoding", params=params, timeout=10
            )
            if response.status_code != 200:
                _logger.warning(
                    "Request to Google Maps failed.\nCode: %s\nContent: %s",
                    response.status_code,
                    response.content,
                )
                raise ValueError("Google Maps returned HTTP %s" % response.status_code)
            result = response.json()
        except (OSError, ValueError) as e:
            self._raise_query_error(e)

        try:
            if result["status"] == "ZERO_RESULTS":
                return None
            if result["status"] != "OK":
                _logger.debug(
                    "Invalid Gmaps call: %s - %s",
                    result["status"],
                    result.get("error_message", ""),
                )
                error_msg = self.env._(
                    "Unable to geolocate, received the error:\n%s"
                    "\n\nGoogle made this a paid feature.\n"
                    "You should first enable billing on your Google account.\n"
                    "Then, go to Developer Console, and enable the APIs:\n"
                    "Geocoding, Maps Static, Maps Javascript.\n",
                    result.get("error_message"),
                )
                raise UserError(error_msg)
            geo = result["results"][0]["geometry"]["location"]
            return float(geo["lat"]), float(geo["lng"])
        except KeyError, IndexError, ValueError:
            _logger.debug(
                "Unexpected Gmaps API answer %s", result.get("error_message", "")
            )
            return None

    @api.model
    def _geo_query_address_default(
        self, street=None, zip_code=None, city=None, state=None, country=None
    ) -> str:
        address_list = [
            street,
            ("%s %s" % (zip_code or "", city or "")).strip(),
            state,
            country,
        ]
        return ", ".join(filter(None, address_list))

    @api.model
    def _geo_query_address_googlemap(
        self, street=None, zip_code=None, city=None, state=None, country=None
    ):
        return self._geo_query_address_default(
            street=street, zip_code=zip_code, city=city, state=state, country=country
        )

    def _raise_query_error(self, error) -> None:
        raise UserError(self.env._("Error with geolocation server: %s", error))

    def _get_localisation(self, latitude, longitude):
        city = request.geoip.city.name
        country_code = request.geoip.country_code
        postcode = False
        if not (city and country_code):
            result = self._call_openstreetmap_reverse(latitude, longitude)
            if result and (address := result.get("address")):
                country_code = country_code or address.get("country_code")
                city = city or (
                    address.get("city_district")
                    or address.get("town")
                    or address.get("village")
                    or address.get("city")
                )
                postcode = address.get("postcode")

        country = (
            self.env["res.country"].search(
                [("code", "=", country_code.upper())], limit=1
            )
            if country_code
            else False
        )

        res = postcode or ""
        if city:
            res += f" {city}" if res else city
        if country:
            res += f", {country.name}" if res else country.name

        return res or self.env._("Unknown")
