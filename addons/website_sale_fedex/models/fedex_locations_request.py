import json
import logging

from zeep import Client, Settings, helpers
from zeep.exceptions import Fault

from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.tools.misc import file_path

from odoo.addons.delivery_fedex.models.fedex_request import (
    STATECODE_REQUIRED_COUNTRIES,
    FedexRequest,
    LogPlugin,
    remove_accents,
)

_debug = DebugLog(__name__)


class AllStringEncoder(json.JSONEncoder):
    def default(self, obj):
        if not isinstance(obj, dict) and not isinstance(obj, list):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


class FEDEXLocationsRequest(FedexRequest):
    def __init__(
        self, debug_logger, request_type="locs", prod_environment=False
    ) -> None:
        super().__init__(debug_logger, request_type, prod_environment)
        wsdl_folder = "prod" if prod_environment else "test"
        wsdl_path = file_path(
            f"website_sale_fedex/api/{wsdl_folder}/LocationsService_v12.wsdl"
        )
        self._start_locs_transaction(wsdl_path)

    def _start_locs_transaction(self, wsdl_path) -> None:
        settings = Settings(strict=False)
        self.client = Client(
            "file:///%s" % wsdl_path.lstrip("/"),
            plugins=[LogPlugin(self.debug_logger)],
            settings=settings,
        )
        self.factory = self.client.type_factory("ns0")
        self.VersionId = self.factory.VersionId()
        self.VersionId.ServiceId = "locs"
        self.VersionId.Major = "12"
        self.VersionId.Intermediate = "0"
        self.VersionId.Minor = "0"

    def set_locs_details(self, carrier, ship_to) -> None:
        self.LocationsSearchCriterion = "ADDRESS"

        self.Address = self.factory.Address()
        self.Address.City = remove_accents(ship_to.city)
        if ship_to.country_id.code in STATECODE_REQUIRED_COUNTRIES:
            self.Address.StateOrProvinceCode = ship_to.state_id.code
        else:
            self.Address.StateOrProvinceCode = ""
        self.Address.PostalCode = ship_to.zip
        self.Address.CountryCode = ship_to.country_id.code

        self.MultipleMatchesAction = "RETURN_ALL"

        self.SortDetail = self.factory.LocationSortDetail()
        self.SortDetail.Criterion = "DISTANCE"
        self.SortDetail.Order = "LOWEST_TO_HIGHEST"

        self.Constraints = self.factory.SearchLocationConstraints()
        self.Constraints.RadiusDistance = self.factory.Distance()
        self.Constraints.RadiusDistance.Value = carrier.fedex_locations_radius_value
        self.Constraints.RadiusDistance.Units = (
            carrier.fedex_locations_radius_unit.name.upper()
        )

    def process_locs(self, env):
        _logger = logging.getLogger(__name__)
        try:
            self.response = self.client.service.searchLocations(
                WebAuthenticationDetail=self.WebAuthenticationDetail,
                ClientDetail=self.ClientDetail,
                TransactionDetail=self.TransactionDetail,
                Version=self.VersionId,
                LocationsSearchCriterion=self.LocationsSearchCriterion,
                Address=self.Address,
                MultipleMatchesAction=self.MultipleMatchesAction,
                SortDetail=self.SortDetail,
                Constraints=self.Constraints,
            )

            if self.response.HighestSeverity not in {"ERROR", "FAILURE"}:
                response = self.response["AddressToLocationRelationships"][0][
                    "DistanceAndLocationDetails"
                ]
                response = helpers.serialize_object(response, dict)
            else:
                raise UserError(
                    "\n".join(
                        ("%s: %s" % (n.Code, n.Message))
                        for n in self.response.Notifications
                        if (n.Severity in {"ERROR", "FAILURE"})
                    )
                )
            if any(n.Severity == "WARNING" for n in self.response.Notifications):
                _logger.warning(
                    "\n".join(
                        ("%s: %s" % (n.Code, n.Message))
                        for n in self.response.Notifications
                        if n.Severity == "WARNING"
                    )
                )

        except Fault as fault:
            _debug.logic("fedex_locations_failed", reason="soap_fault")
            raise UserError(
                env._("There was an error retrieving Fedex localisations:\n%s", fault)
            ) from fault
        except OSError as err:
            _debug.logic("fedex_locations_failed", reason="unreachable")
            raise UserError(env._("Fedex Server Not Found")) from err
        except ValueError as err:
            raise UserError(
                env._("No Fedex pick-up points available for that shipping address")
            ) from err
        return self._normalize_response(response)

    def _normalize_response(self, response):
        return json_loads(json.dumps(response, cls=AllStringEncoder))
