import datetime
import logging
import re
from itertools import islice
from urllib.parse import quote, urlencode

import requests
from dateutil.relativedelta import relativedelta
from lxml import etree
from zeep import Client
from zeep.helpers import serialize_object

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.datetime import timezone
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

from odoo.addons.account.tools import LegacyHTTPAdapter
from odoo.addons.iap.tools.iap_tools import iap_jsonrpc

BANXICO_DATE_FORMAT = "%d/%m/%Y"
PROXY_URL = "https://iap-services.odoo.com"
CBUAE_URL = "https://centralbank.ae/umbraco/Surface/Exchange/GetExchangeRateAllCurrency"
CBEGY_URL = "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates"
MAP_CURRENCIES = {
    "US Dollar": "USD",
    "UAE Dirham": "AED",
    "Argentine Peso": "ARS",
    "Australian Dollar": "AUD",
    "Azerbaijan manat": "AZN",
    "Bangladesh Taka": "BDT",
    "Bulgarian lev": "BGN",
    "Bahrani Dinar": "BHD",
    "Bahraini Dinar": "BHD",
    "Brunei Dollar": "BND",
    "Brazilian Real": "BRL",
    "Botswana Pula": "BWP",
    "Belarus Rouble": "BYN",
    "Canadian Dollar": "CAD",
    "Swiss Franc": "CHF",
    "Chilean Peso": "CLP",
    "Chinese Yuan - Offshore": "CNH",
    "Chinese Yuan": "CNY",
    "Colombian Peso": "COP",
    "Czech Koruna": "CZK",
    "Danish Krone": "DKK",
    "Algerian Dinar": "DZD",
    "Egypt Pound": "EGP",
    "Ethiopian birr": "ETB",
    "Euro": "EUR",
    "GB Pound": "GBP",
    "Pound Sterling": "GBP",
    "Hongkong Dollar": "HKD",
    "Croatian kuna": "HRK",
    "Hungarian Forint": "HUF",
    "Indonesia Rupiah": "IDR",
    "Israeli new shekel": "ILS",
    "Indian Rupee": "INR",
    "Iraqi dinar": "IQD",
    "Iceland Krona": "ISK",
    "Jordan Dinar": "JOD",
    "Jordanian Dinar": "JOD",
    "Japanese Yen": "JPY",
    "Japanese Yen 100": "JPY",
    "Kenya Shilling": "KES",
    "Korean Won": "KRW",
    "Kuwaiti Dinar": "KWD",
    "Kazakhstan Tenge": "KZT",
    "Lebanon Pound": "LBP",
    "Sri Lanka Rupee": "LKR",
    "Libyan dinar": "LYD",
    "Moroccan Dirham": "MAD",
    "Macedonia Denar": "MKD",
    "Mauritian rupee": "MUR",
    "Mexican Peso": "MXN",
    "Malaysia Ringgit": "MYR",
    "Nigerian Naira": "NGN",
    "Norwegian Krone": "NOK",
    "NewZealand Dollar": "NZD",
    "Omani Rial": "OMR",
    "Omani Riyal": "OMR",
    "Peru Sol": "PEN",
    "Philippine Piso": "PHP",
    "Pakistan Rupee": "PKR",
    "Polish Zloty": "PLN",
    "Qatari Riyal": "QAR",
    "Romanian leu": "RON",
    "Serbian Dinar": "RSD",
    "Russia Rouble": "RUB",
    "Saudi Riyal": "SAR",
    "Sudanese Pound": "SDG",
    "Singapore Dollar": "SGD",
    "Swedish Krona": "SEK",
    "Syrian pound": "SYP",
    "Thai Baht": "THB",
    "Turkmen manat": "TMT",
    "Tunisian Dinar": "TND",
    "Turkish Lira": "TRY",
    "Trin Tob Dollar": "TTD",
    "Taiwan Dollar": "TWD",
    "Tanzania Shilling": "TZS",
    "Uganda Shilling": "UGX",
    "Uruguayan Peso": "UYU",
    "Uzbekistani som": "UZS",
    "Vietnam Dong": "VND",
    "Caribbean Guilder": "XCG",
    "Yemen Rial": "YER",
    "South Africa Rand": "ZAR",
    "Zambian Kwacha": "ZMW",
}
_logger = logging.getLogger(__name__)


def xml2json_from_elementtree(el, preserve_whitespaces=False):
    res = {}
    if el.tag[0] == "{":
        ns, name = el.tag.rsplit("}", 1)
        res["tag"] = name
        res["namespace"] = ns[1:]
    else:
        res["tag"] = el.tag
    res["attrs"] = {}
    for k, v in el.items():
        res["attrs"][k] = v
    kids = []
    if el.text and (preserve_whitespaces or el.text.strip() != ""):
        kids.append(el.text)
    for kid in el:
        kids.append(xml2json_from_elementtree(kid, preserve_whitespaces))
        if kid.tail and (preserve_whitespaces or kid.tail.strip() != ""):
            kids.append(kid.tail)
    res["children"] = kids
    return res


CURRENCY_PROVIDER_SELECTION = [
    ([], "ecb", "European Central Bank"),
    (["IN", "SA"], "xe_com", "xe.com"),
    (["AE"], "cbuae", "[AE] Central Bank of the UAE"),
    (["BG"], "bnb", "[BG] Bulgaria National Bank"),
    (["BR"], "bbr", "[BR] Central Bank of Brazil"),
    (["CA"], "boc", "[CA] Bank of Canada"),
    (["CH"], "fta", "[CH] Federal Tax Administration of Switzerland"),
    (["CL"], "mindicador", "[CL] Central Bank of Chile via mindicador.cl"),
    (["CO"], "banrepco", "[CO] Bank of the Republic"),
    (["CZ"], "cnb", "[CZ] Czech National Bank"),
    (["EG"], "cbegy", "[EG] Central Bank of Egypt"),
    (["GT"], "banguat", "[GT] Bank of Guatemala"),
    (["HU"], "mnb", "[HU] Magyar Nemzeti Bank"),
    (["ID"], "bi", "[ID] Bank Indonesia"),
    (["IT"], "boi", "[IT] Bank of Italy"),
    (["MX"], "banxico", "[MX] Bank of Mexico"),
    (["MY"], "bnm", "[MY] Bank Negara Malaysia"),
    (["PE"], "bcrp", "[PE] SUNAT (replaces Bank of Peru)"),
    (["PL"], "nbp", "[PL] National Bank of Poland"),
    (["RO"], "bnr", "[RO] National Bank of Romania"),
    (["SE"], "srb", "[SE] Sveriges Riksbank"),
    (["SI"], "bsi", "[SI] Bank of Slovenia"),
    (["TH"], "bot", "[TH] Bank of Thailand"),
    (["TR"], "tcmb", "[TR] Central Bank of the Republic of Türkiye"),
    (["UK"], "hmrc", "[UK] HM Revenue & Customs"),
    (["UY"], "bcu", "[UY] Uruguayan Central Bank"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    currency_interval_unit = fields.Selection(
        selection=[
            ("manually", "Manually"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
        ],
        string="Interval Unit",
        default="manually",
        required=True,
    )
    currency_next_execution_date = fields.Date(string="Next Execution Date")
    currency_provider = fields.Selection(
        selection=[
            (provider_code, desc)
            for dummy, provider_code, desc in CURRENCY_PROVIDER_SELECTION
        ],
        string="Service Provider",
        compute="_compute_currency_provider",
        store=True,
        readonly=False,
    )

    @api.depends("country_id")
    def _compute_currency_provider(self) -> None:
        code_providers = {
            country: provider_code
            for countries, provider_code, dummy in CURRENCY_PROVIDER_SELECTION
            for country in countries
        }
        for record in self:
            record.currency_provider = code_providers.get(record.country_id.code, "ecb")

    def update_currency_rates(self):
        active_currencies = self.env["res.currency"].search([])
        rslt = True
        for currency_provider, companies in self._group_by_provider().items():
            parse_function = companies._get_currency_provider_parsers()[
                currency_provider
            ]
            try:
                parse_results = parse_function(active_currencies)
                companies._create_currency_rates(parse_results)
            except Exception as error:
                if self.env.context.get("suppress_errors"):
                    _logger.warning(error)
                    _logger.warning(
                        "Unable to connect to the online exchange rate platform %s. The web service may be temporarily down. Please try again in a moment.",
                        currency_provider,
                    )
                    rslt = False
                elif isinstance(error, UserError):
                    raise
                else:
                    raise UserError(
                        self.env._(
                            "Unable to connect to the online exchange rate platform %s. The web service may be temporarily down. Please try again in a moment.",
                            currency_provider,
                        )
                    ) from error
        return rslt

    def _get_currency_provider_parsers(self) -> dict:
        return {
            "ecb": self._parse_ecb_data,
            "xe_com": self._parse_xe_com_data,
            "cbuae": self._parse_cbuae_data,
            "bnb": self._parse_bnb_data,
            "bbr": self._parse_bbr_data,
            "boc": self._parse_boc_data,
            "fta": self._parse_fta_data,
            "mindicador": self._parse_mindicador_data,
            "banrepco": self._parse_banrepco_data,
            "cnb": self._parse_cnb_data,
            "cbegy": self._parse_cbegy_data,
            "banguat": self._parse_banguat_data,
            "mnb": self._parse_mnb_data,
            "bi": self._parse_bi_data,
            "boi": self._parse_boi_data,
            "banxico": self._parse_banxico_data,
            "bnm": self._parse_bnm_data,
            "bcrp": self._parse_bcrp_data,
            "nbp": self._parse_nbp_data,
            "bnr": self._parse_bnr_data,
            "srb": self._parse_srb_data,
            "bsi": self._parse_bsi_data,
            "bot": self._parse_bot_data,
            "tcmb": self._parse_tcmb_data,
            "hmrc": self._parse_hmrc_data,
            "bcu": self._parse_bcu_data,
        }

    def _group_by_provider(self):
        rslt = {}
        for company in self:
            if not company.currency_provider:
                continue

            if rslt.get(company.currency_provider):
                rslt[company.currency_provider] += company
            else:
                rslt[company.currency_provider] = company
        return rslt

    def _create_currency_rates(self, parsed_data) -> None:
        Currency = self.env["res.currency"]
        CurrencyRate = self.env["res.currency.rate"]

        for company in self:
            rate_info = parsed_data.get(company.currency_id.name, None)

            if not rate_info:
                msg = self.env._(
                    "Your main currency (%s) is not supported by this exchange rate provider. Please choose another one.",
                    company.currency_id.name,
                )
                if self.env.context.get("suppress_errors"):
                    _logger.warning(msg)
                    continue
                raise UserError(msg)

            base_currency_rate = rate_info[0]

            for currency, (rate, date_rate) in parsed_data.items():
                rate_value = rate / base_currency_rate

                currency_object = Currency.search([("name", "=", currency)])
                if currency_object:
                    already_existing_rate = CurrencyRate.search(
                        [
                            ("currency_id", "=", currency_object.id),
                            ("name", "=", date_rate),
                            ("company_id", "=", company.id),
                        ]
                    )
                    if already_existing_rate:
                        already_existing_rate.rate = rate_value
                    else:
                        CurrencyRate.create(
                            {
                                "currency_id": currency_object.id,
                                "rate": rate_value,
                                "name": date_rate,
                                "company_id": company.id,
                            }
                        )

    @api.model
    def _parse_bsi_data(self, available_currencies):

        bsi_url = "https://api.bsi.si/"
        endpoints = ["exchange/daily", "exchange/exotic"]
        available_currency_names = available_currencies.mapped("name")
        currency_rates_entries = []
        rates = {}

        session = self.env["ir.egress"].session(purpose="currency_rate_live")
        for endpoint in endpoints:
            try:
                response = session.get(f"{bsi_url}{endpoint}", timeout=30)
                response.raise_for_status()
                currency_rates_entries.extend(response.json().get("data", []))
            except requests.RequestException as e:
                _logger.error(e)

        for currency_rate_entry in currency_rates_entries:
            currency_code = currency_rate_entry.get("code")
            rate = currency_rate_entry.get("value")
            date = currency_rate_entry.get("date")

            if not (currency_code and rate and date):
                continue
            date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()

            if currency_code in available_currency_names and rate:
                rates[currency_code] = (float(rate), date_obj)

        rates["EUR"] = (1.0, datetime.datetime.now().date())
        return rates

    def _parse_fta_data(self, available_currencies):
        request_url = (
            "https://www.backend-rates.bazg.admin.ch/api/xmldaily?d=today&locale=en"
        )
        response = self.env["ir.egress"].request(
            "GET", request_url, purpose="currency_rate_live", timeout=30
        )
        response.raise_for_status()

        rates_dict = {}
        available_currency_names = available_currencies.mapped("name")
        xml_tree = etree.fromstring(response.content)
        data = xml2json_from_elementtree(xml_tree)
        date_elem = xml_tree.xpath("//*[local-name() = 'datum']")[0]
        date_rate = datetime.datetime.strptime(
            date_elem.text.split(",")[0], "%d.%m.%Y"
        ).date()
        for child_node in data["children"]:
            if child_node["tag"] == "devise":
                currency_code = child_node["attrs"]["code"].upper()

                if currency_code in available_currency_names:
                    currency_xml = None
                    rate_xml = None

                    for sub_child in child_node["children"]:
                        if sub_child["tag"] == "waehrung":
                            currency_xml = sub_child["children"][0]
                        elif sub_child["tag"] == "kurs":
                            rate_xml = sub_child["children"][0]
                        if currency_xml and rate_xml:
                            break

                    rates_dict[currency_code] = (
                        float(re.search(r"\d+", currency_xml).group())
                        / float(rate_xml),
                        date_rate,
                    )

        if "CHF" in available_currency_names:
            rates_dict["CHF"] = (1.0, date_rate)

        return rates_dict

    def _parse_ecb_data(self, available_currencies):
        request_url = "http://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
        response = self.env["ir.egress"].request(
            "GET", request_url, purpose="currency_rate_live", timeout=30
        )
        response.raise_for_status()

        xmlstr = etree.fromstring(response.content)
        data = xml2json_from_elementtree(xmlstr)
        node = data["children"][2]["children"][0]
        xmldate = fields.Date.to_date(node["attrs"]["time"])
        available_currency_names = available_currencies.mapped("name")
        rslt = {
            x["attrs"]["currency"]: (float(x["attrs"]["rate"]), xmldate)
            for x in node["children"]
            if x["attrs"]["currency"] in available_currency_names
        }

        if rslt and "EUR" in available_currency_names:
            rslt["EUR"] = (1.0, xmldate)

        return rslt

    def _parse_cbuae_data(self, available_currencies):
        headers = {
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.centralbank.ae/en/forex-eibor/exchange-rates/",
        }

        response = self.env["ir.egress"].request(
            "GET", CBUAE_URL, purpose="currency_rate_live", headers=headers, timeout=30
        )
        response.raise_for_status()

        htmlelem = etree.fromstring(
            response.content, etree.HTMLParser(encoding="utf-8")
        )
        rates_entries = htmlelem.xpath("//table/tbody//tr")
        date_elem = htmlelem.xpath("//div[@class='row mb-4']/div/p[last()]")[0]
        date_rate = datetime.datetime.strptime(
            date_elem.text.strip(), "Last updated:\r\n\r\n%A %d %B %Y %I:%M:%S %p"
        ).date()
        available_currency_names = set(available_currencies.mapped("name"))
        rslt = {}
        for rate_entry in rates_entries:
            currency_code = MAP_CURRENCIES.get(rate_entry[1].text)
            rate = float(rate_entry[2].text)
            if currency_code in available_currency_names:
                rslt[currency_code] = (1.0 / rate, date_rate)

        if "AED" in available_currency_names:
            rslt["AED"] = (1.0, date_rate)
        return rslt

    def _parse_cbegy_data(self, available_currencies):
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.41 Safari/537.36",
        }
        fetched_data = self.env["ir.egress"].request(
            "GET", CBEGY_URL, purpose="currency_rate_live", headers=headers, timeout=30
        )
        fetched_data.raise_for_status()

        htmlelem = etree.fromstring(fetched_data.content, etree.HTMLParser())
        rates_entries = htmlelem.xpath("//table/tbody/tr")
        date_text = htmlelem.xpath("//p[contains(.,'Rates for Date')]/text()")[1]
        date_rate = datetime.datetime.strptime(
            date_text.strip(), "Rates for Date: %d/%m/%Y"
        ).date()
        available_currency_names = set(available_currencies.mapped("name"))
        rslt = {}
        for rate_entry in rates_entries:
            currency_code = MAP_CURRENCIES.get(rate_entry[0].text.strip())
            rate = (float(rate_entry[1].text) + float(rate_entry[2].text)) / 2
            if currency_code in available_currency_names:
                rslt[currency_code] = (1.0 / rate, date_rate)

        if "EGP" in available_currency_names:
            rslt["EGP"] = (1.0, date_rate)
        return rslt

    def _parse_banguat_data(self, available_currencies):
        available_currency_names = available_currencies.mapped("name")
        if (
            "GTQ" not in available_currency_names
            or "USD" not in available_currency_names
        ):
            raise UserError(
                self.env._(
                    "The selected exchange rate provider requires the GTQ and USD currencies to be active."
                )
            )

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
        }
        body = """<?xml version="1.0" encoding="utf-8"?>
            <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
                <soap12:Body>
                    <TipoCambioDia xmlns="http://www.banguat.gob.gt/variables/ws/"/>
                </soap12:Body>
            </soap12:Envelope>
        """
        res = self.env["ir.egress"].request(
            "POST",
            "https://www.banguat.gob.gt/variables/ws/TipoCambio.asmx",
            purpose="currency_rate_live",
            data=body,
            headers=headers,
            timeout=10,
        )
        res.raise_for_status()

        xml_tree = etree.fromstring(res.content)

        rslt = {}
        date_rate = xml_tree.xpath(
            ".//*[local-name()='VarDolar']/*[local-name()='fecha']/text()"
        )[0]
        if date_rate:
            date_rate = datetime.datetime.strptime(date_rate, "%d/%m/%Y").date()
            rslt["GTQ"] = (1.0, date_rate)
            rate = (
                xml_tree.xpath(
                    ".//*[local-name()='VarDolar']/*[local-name()='referencia']/text()"
                )[0]
                or 0.0
            )
            if rate:
                rate = 1.0 / float(rate)
                rslt["USD"] = (rate, date_rate)
        return rslt

    def _parse_hmrc_data(self, available_currencies):
        first_of_month = fields.Date.context_today(
            self.with_context(tz="Europe/London")
        ).replace(day=1)
        formatted_date = first_of_month.strftime("%Y-%m")

        request_url = f"https://www.trade-tariff.service.gov.uk/api/v2/exchange_rates/files/monthly_xml_{formatted_date}.xml"
        response = self.env["ir.egress"].request(
            "GET", request_url, purpose="currency_rate_live", timeout=10
        )
        response.raise_for_status()

        xml_tree = etree.fromstring(response.content)
        available_currency_names = available_currencies.mapped("name")
        rslt = {
            node.find("currencyCode").text: (
                float(node.find("rateNew").text),
                first_of_month,
            )
            for node in xml_tree.iterfind("exchangeRate")
            if node.find("currencyCode").text in available_currency_names
        }

        if rslt and "GBP" in available_currency_names:
            rslt["GBP"] = (1.0, first_of_month)

        return rslt

    def _parse_bbr_data(self, available_currencies):

        def _get_currency_exchange_rate(session, cur, date):
            query_params = {
                "@moeda": ("'%s'" % cur),
                "@dataCotacao": ("'%s'" % date),
                "$top": "1",
                "$orderby": "dataHoraCotacao desc",
                "$format": "json",
                "$select": "cotacaoCompra",
            }
            encoded_params = urlencode(query_params, safe="@$'", quote_via=quote)
            request_url = "https://olinda.bcb.gov.br/olinda/service/PTAX/version/v1/odata/ExchangeRateDate(moeda=@moeda,dataCotacao=@dataCotacao)"
            response = session.get(request_url, params=encoded_params, timeout=10)
            response.raise_for_status()
            if "application/json" not in response.headers.get("Content-Type", ""):
                raise ValueError("Should be json")
            data = response.json()

            if not data["value"]:
                return None
            return data["value"][0]["cotacaoCompra"]

        session = self.env["ir.egress"].session(purpose="currency_rate_live")
        request_url = "https://olinda.bcb.gov.br/olinda/service/PTAX/version/v1/odata/Currencies?$top=100&$format=json"
        response = session.get(request_url, timeout=10)
        response.raise_for_status()
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError("Should be json")
        data = response.json()
        available_currency_names = available_currencies.mapped("name")
        currencies = [
            val["simbolo"]
            for val in data["value"]
            if val["simbolo"] in available_currency_names
        ]

        date_rate = datetime.datetime.now(timezone("America/Sao_Paulo"))

        rslt = {}
        for currency in currencies:
            rate = None
            while not rate:
                rate = _get_currency_exchange_rate(
                    session, currency, date_rate.strftime("%m-%d-%Y")
                )
                if not rate:
                    date_rate -= datetime.timedelta(days=1)

            rslt[currency] = (1.0 / rate, date_rate)

        if "BRL" in available_currency_names:
            rslt["BRL"] = (1.0, date_rate)

        return rslt

    def _parse_boc_data(self, available_currencies):
        available_currency_names = available_currencies.mapped("name")

        request_url = (
            "http://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/json"
        )
        response = self.env["ir.egress"].request(
            "GET", request_url, purpose="currency_rate_live", timeout=30
        )
        response.raise_for_status()
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError("Should be json")
        data = response.json()

        last_observation_date = max(obs["d"] for obs in data["observations"])
        last_obs = next(
            obs for obs in data["observations"] if obs["d"] == last_observation_date
        )
        last_obs.update({"FXCADCAD": {"v": "1"}})
        date_rate = datetime.datetime.strptime(last_observation_date, "%Y-%m-%d").date()
        rslt = {}
        if "CAD" in available_currency_names:
            rslt["CAD"] = (1, date_rate)

        for currency_name in available_currency_names:
            currency_obs = last_obs.get(f"FX{currency_name}CAD", None)
            if currency_obs is not None:
                rslt[currency_name] = (1.0 / float(currency_obs["v"]), date_rate)

        return rslt

    def _parse_banxico_data(self, available_currencies):
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {"provider": "banxico"},
            }
            response = (
                self.env["ir.egress"]
                .request(
                    "GET",
                    f"{PROXY_URL}/api/currency_rate/1/get_currency_rates",
                    purpose="currency_rate_live",
                    json=payload,
                    headers={"content-type": "application/json"},
                    timeout=30,
                )
                .json()
            )

            if response.get("error"):
                return False
            series = response["result"]
        except requests.RequestException as e:
            _logger.error(e)
            return False

        available_currency_names = available_currencies.mapped("name")
        rslt = {
            "MXN": (1.0, fields.Date.today().strftime(DEFAULT_SERVER_DATE_FORMAT)),
        }
        foreigns = {
            "SF46410": "EUR",
            "SF60632": "CAD",
            "SF46406": "JPY",
            "SF46407": "GBP",
            "SF60653": "USD",
            "SF290383": "CNY",
        }
        for index, currency in foreigns.items():
            if not series.get(index, False):
                continue
            if currency not in available_currency_names:
                continue

            serie = series[index]
            for rate in serie:
                try:
                    foreign_mxn_rate = float(serie[rate])
                except ValueError, TypeError:
                    continue
                foreign_rate_date = datetime.datetime.strptime(
                    rate, BANXICO_DATE_FORMAT
                ).strftime(DEFAULT_SERVER_DATE_FORMAT)
                rslt[currency] = (1.0 / foreign_mxn_rate, foreign_rate_date)
        return rslt

    def _parse_xe_com_data(self, available_currencies):
        iap_proxy_url = self.env.registry.settings.get(
            self.env, "currency_rate_live.iap_proxy_url", PROXY_URL
        )
        currency_data = iap_jsonrpc(
            f"{iap_proxy_url}/api/currency_rate/1/get_currency_rates",
            params={"provider": "xe_com"},
            env=self.env,
        )
        available_currency_names = available_currencies.mapped("name")
        rslt = {}

        for timestamp, rates in currency_data.items():
            for currency, rate in rates.items():
                if currency in available_currency_names and rate:
                    date_rate = datetime.datetime.strptime(
                        timestamp, "%Y-%m-%dT%H:%M:%SZ"
                    )
                    rslt[currency] = (
                        rate,
                        date_rate.strftime(DEFAULT_SERVER_DATE_FORMAT),
                    )

        return rslt

    def _parse_bnr_data(self, available_currencies):
        request_url = "https://www.bnr.ro/nbrfxrates.xml"
        response = self.env["ir.egress"].request(
            "GET", request_url, purpose="currency_rate_live", timeout=30
        )
        response.raise_for_status()

        xmlstr = etree.fromstring(response.content)
        data = xml2json_from_elementtree(xmlstr)
        available_currency_names = available_currencies.mapped("name")
        rate_date = fields.Date.today()
        rslt = {}
        rates_node = data["children"][1]["children"][2]
        if rates_node:
            rate_date = (
                datetime.datetime.strptime(
                    rates_node["attrs"]["date"], DEFAULT_SERVER_DATE_FORMAT
                )
                + datetime.timedelta(days=1)
            ).strftime(DEFAULT_SERVER_DATE_FORMAT)
            for x in rates_node["children"]:
                if x["attrs"]["currency"] in available_currency_names:
                    rslt[x["attrs"]["currency"]] = (
                        float(x["attrs"].get("multiplier", "1"))
                        / float(x["children"][0]),
                        rate_date,
                    )
        if rslt and "RON" in available_currency_names:
            rslt["RON"] = (1.0, rate_date)
        return rslt

    def _parse_srb_data(self, available_currencies):
        response = self.env["ir.egress"].request(
            "GET",
            "https://api.riksbank.se/swea/v1/Observations/Latest/ByGroup/130",
            purpose="currency_rate_live",
            timeout=30,
        )
        response.raise_for_status()

        if "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError("Response should be in JSON format")

        data_json = response.json()
        available_currency_names = set(available_currencies.mapped("name"))
        rslt = {}

        series_data = {item["seriesId"]: item for item in data_json}

        for currency in available_currency_names:
            if currency == "SEK":
                rslt[currency] = (
                    1.0,
                    datetime.datetime.now(timezone("Europe/Stockholm")).strftime(
                        DEFAULT_SERVER_DATE_FORMAT
                    ),
                )
                continue

            line_json = series_data.get(f"SEK{currency}PMI")

            if (
                not line_json
                or not isinstance(line_json["value"], (int, float))
                or line_json["value"] == 0
            ):
                continue
            date = datetime.datetime.strptime(line_json["date"], "%Y-%m-%d").strftime(
                DEFAULT_SERVER_DATE_FORMAT
            )
            rslt[currency] = (1.0 / line_json["value"], date)

        return rslt

    def _parse_bcrp_data(self, available_currencies):

        result = {}
        available_currency_names = available_currencies.mapped("name")
        if (
            "PEN" not in available_currency_names
            or "USD" not in available_currency_names
        ):
            return result
        result["PEN"] = (
            1.0,
            fields.Date.context_today(self.with_context(tz="America/Lima")),
        )
        url_format = "https://www.sunat.gob.pe/a/txt/tipoCambio.txt"
        try:
            res = self.env["ir.egress"].request(
                "GET", url_format, purpose="currency_rate_live", timeout=10
            )
            res.raise_for_status()
            line = res.text.splitlines()[0] or ""
        except Exception:
            _logger.exception("SUNAT exchange rate request failed")
            return result
        sunat_value = line.split("|")
        try:
            rate = float(sunat_value[2])
        except ValueError as e:
            _logger.error(e)
            return result
        rate = 1.0 / rate if rate else 0
        date_rate_str = sunat_value[0]
        date_rate = datetime.datetime.strptime(date_rate_str, "%d/%m/%Y").strftime(
            DEFAULT_SERVER_DATE_FORMAT
        )
        result["USD"] = (rate, date_rate)
        return result

    def _parse_mindicador_data(self, available_currencies):
        logger = _logger.getChild("mindicador")
        icp = self.env["ir.config_parameter"].sudo()
        server_url = icp.get_param("mindicador_api_url")
        if not server_url:
            server_url = "https://mindicador.cl/api"
            icp.set_param("mindicador_api_url", server_url)
        foreigns = {
            "USD": "dolar",
            "EUR": "euro",
            "UF": "uf",
            "UTM": "utm",
        }
        available_currency_names = available_currencies.mapped("name")
        logger.debug(
            "mindicador: available currency names: %s", available_currency_names
        )
        today_date = fields.Date.context_today(self.with_context(tz="America/Santiago"))
        rslt = {
            "CLP": (1.0, fields.Date.to_string(today_date)),
        }
        request_date = today_date.strftime("%d-%m-%Y")
        for index, currency in foreigns.items():
            if index not in available_currency_names:
                logger.debug("Index %s not in available currency name", index)
                continue
            url = server_url + "/%s/%s" % (currency, request_date)
            res = self.env["ir.egress"].request(
                "GET", url, purpose="currency_rate_live", timeout=30
            )
            res.raise_for_status()
            if "html" in res.text:
                raise ValueError("Should be json")
            data_json = res.json()
            if not data_json["serie"]:
                continue
            date = data_json["serie"][0]["fecha"][:10]
            rate = data_json["serie"][0]["valor"]
            rslt[index] = (1.0 / rate, date)
        return rslt

    def _parse_banrepco_data(self, available_currencies) -> dict:
        res = self.env["ir.egress"].request(
            "GET",
            "https://totoro.banrep.gov.co/nsi-jax-ws/rest/data/ESTAT,DF_TRM_DAILY_LATEST,1.0/all/ALL",
            purpose="currency_rate_live",
            timeout=10,
        )
        res.raise_for_status()
        tree = etree.fromstring(res.content)

        generic_ns = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic"
        rate = float(tree.find(f".//{{{generic_ns}}}ObsValue").get("value"))

        time_period = tree.find(f".//{{{generic_ns}}}ObsDimension").get("value")
        date = fields.Date.to_string(datetime.datetime.strptime(time_period, "%Y%m%d"))

        return {"COP": (1, date), "USD": (1.0 / rate, date)}

    def _parse_tcmb_data(self, available_currencies):
        server_url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        available_currency_names = set(available_currencies.mapped("name"))

        session = self.env["ir.egress"].session(purpose="currency_rate_live")
        session.mount("https://", LegacyHTTPAdapter())

        res = session.get(server_url, timeout=30)
        res.raise_for_status()

        root = etree.fromstring(res.text.encode())
        rate_date = fields.Date.to_string(
            datetime.datetime.strptime(root.attrib["Date"], "%m/%d/%Y")
        )
        rslt = {
            currency.attrib["Kod"]: (
                2
                / (
                    float(currency.find("ForexBuying").text)
                    + float(currency.find("ForexSelling").text)
                ),
                rate_date,
            )
            for currency in root
            if currency.attrib["Kod"] in available_currency_names
        }
        rslt["TRY"] = (1.0, rate_date)

        return rslt

    def _parse_nbp_data(self, available_currencies):

        request_url = "https://api.nbp.pl/api/exchangerates/tables/{}/?format=json"
        requested_currency_codes = available_currencies.mapped("name")
        result = {}

        for table_type in ["A", "B"]:
            if not requested_currency_codes:
                break

            response = self.env["ir.egress"].request(
                "GET",
                request_url.format(table_type),
                purpose="currency_rate_live",
                timeout=10,
            )
            response.raise_for_status()
            response_data = response.json()
            for exchange_table in response_data:
                table_date = datetime.datetime.strptime(
                    exchange_table["effectiveDate"], "%Y-%m-%d"
                ).date()

                table_date += relativedelta(days=1)

                if "PLN" not in result and "PLN" in requested_currency_codes:
                    result["PLN"] = (1.0, table_date)

                for rec in exchange_table["rates"]:
                    if rec["code"] in requested_currency_codes:
                        result[rec["code"]] = (1.0 / rec["mid"], table_date)
                        requested_currency_codes.remove(rec["code"])

        return result

    def _parse_cnb_data(self, available_currencies):
        request_url = "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/denni_kurz.txt"
        response = self.env["ir.egress"].request(
            "GET", request_url, purpose="currency_rate_live", timeout=3
        )
        response.raise_for_status()
        response = str(response.content, "UTF-8")

        last_update = fields.Date.to_date(
            datetime.datetime.strptime(response.split(" ")[0], "%d.%m.%Y")
        )
        rates_lines = response.split("\n")[2:-1]
        available_currency_names = available_currencies.mapped("name")
        rslt = {}
        for rate_line in rates_lines:
            _country, _currency, amount, code, rate = rate_line.replace(",", ".").split(
                "|"
            )
            if code in available_currency_names:
                rslt[code] = (float(amount) / float(rate), last_update)

        if rslt and "CZK" in available_currency_names:
            rslt["CZK"] = (1.0, last_update)
        return rslt

    def _get_bcu_currencies_mapping(self) -> dict:
        return {
            "ARS": 501,
            "AUD": 105,
            "BRL": 1001,
            "CAD": 2309,
            "CHF": 5900,
            "CLP": 1300,
            "CNY": 4150,
            "COP": 5500,
            "DKK": 1800,
            "EUR": 1111,
            "GBP": 2700,
            "HKD": 5100,
            "HUF": 4300,
            "INR": 5700,
            "ISK": 4900,
            "JPY": 3600,
            "KRW": 5300,
            "MXN": 4200,
            "MYR": 5600,
            "NOK": 4600,
            "NZD": 1490,
            "PEN": 4000,
            "PYG": 4800,
            "RUB": 5400,
            "SEK": 5800,
            "TRY": 4400,
            "USD": 2225,
            "UYI": 9800,
            "VEF": 6200,
            "ZAR": 1620,
        }

    def _parse_bcu_data(self, available_currencies):
        iso_to_moneda_map = self._get_bcu_currencies_mapping()
        if not (
            to_sync_currencies := available_currencies.filtered(
                lambda c: c.name in iso_to_moneda_map
            )
        ):
            raise UserError(
                self.env._("No available currency rate could be updated from the BCU.")
            )
        moneda_to_iso_map = {v: k for k, v in iso_to_moneda_map.items()}

        wsdl = "https://cotizaciones.bcu.gub.uy/wscotizaciones/servlet/%s/service.asmx?WSDL"
        date_api_client = Client(wsdl % "awsultimocierre")
        rate_api_client = Client(wsdl % "awsbcucotizaciones")

        _logger.info("Getting the date of the last currency rate update from the BCU.")
        last_closing_date = date_api_client.service.Execute()

        to_sync_codes = sorted(to_sync_currencies.mapped("name"))
        _logger.info(
            "Getting the currency rates for (%s) from the BCU.",
            ", ".join(to_sync_codes),
        )
        Entrada = rate_api_client.type_factory("ns0").wsbcucotizacionesin(
            Moneda={
                "item": to_sync_currencies.mapped(lambda x: iso_to_moneda_map[x.name])
            },
            FechaDesde=last_closing_date,
            FechaHasta=last_closing_date,
            Grupo=0,
        )
        response = rate_api_client.service.Execute(Entrada)
        if response.respuestastatus.codigoerror:
            error_message = response.respuestastatus.mensaje
            raise UserError(
                self.env._(
                    "Error updating the currency rates from the BCU: %s.", error_message
                )
            )

        rate_date = last_closing_date + relativedelta(days=1)
        res = {"UYU": (1.0, rate_date)}
        for rate_values in response.datoscotizaciones["datoscotizaciones.dato"]:
            iso_code = moneda_to_iso_map[rate_values.Moneda]
            rate = 1.0 / serialize_object(rate_values.TCV)
            res[iso_code] = (rate, rate_date)

        _logger.info("Currency rates have been downloaded from the BCU.")
        return res

    def _parse_bnb_data(self, available_currencies):
        request_url = "https://www.bnb.bg/Statistics/StExternalSector/StExchangeRates/StERForeignCurrencies/index.htm?download=xml&search=&lang=EN"

        try:
            response = self.env["ir.egress"].request(
                "GET", request_url, purpose="currency_rate_live", timeout=10
            )
            response.raise_for_status()
            rowset = etree.fromstring(response.content)
        except requests.RequestException, etree.ParseError:
            return False

        available_currency_names = available_currencies.mapped("name")
        result = {}

        for row in islice(rowset.iterfind(".//ROW"), 1, None):
            code = row.findtext("CODE")
            rate = row.findtext("REVERSERATE")
            curr_date = datetime.datetime.strptime(
                row.findtext("CURR_DATE"), "%d.%m.%Y"
            ).date()

            if code in available_currency_names and rate:
                result[code] = (float(rate), curr_date)

        if result and "EUR" in available_currency_names:
            result["EUR"] = (1.0, curr_date)
        return result

    def _parse_bot_data(self, available_currencies):
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "provider": "Bank of Thailand",
                },
            }
            response = (
                self.env["ir.egress"]
                .request(
                    "POST",
                    f"{PROXY_URL}/api/currency_rate/1/get_currency_rates",
                    purpose="currency_rate_live",
                    json=payload,
                    timeout=30,
                )
                .json()
            )

            if response.get("error"):
                return False
            series = response["result"]
        except requests.RequestException as e:
            _logger.error(e)
            return False

        available_currency_names = available_currencies.mapped("name")
        result = {}

        for currency, data_detail in series.items():
            period = data_detail["period"]
            rate = float(data_detail["rate"])
            if currency in available_currency_names and rate:
                result[currency] = (1.0 / rate, period)

        if result and "THB" in available_currency_names and period:
            result["THB"] = (1.0, period)

        return result

    def _parse_boi_data(self, available_currencies):
        url = "https://tassidicambio.bancaditalia.it/terzevalute-wf-web/rest/v1.0/latestRates?lang=en"
        result = {}

        try:
            response = self.env["ir.egress"].request(
                "GET",
                url,
                purpose="currency_rate_live",
                headers={"Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
        except Exception:
            _logger.exception("Bank Negara Malaysia exchange rate request failed")
            return result

        curr_iso_codes = available_currencies.mapped("name")
        curr_list = response.json()["latestRates"]

        for curr in curr_list:
            if curr["isoCode"] in curr_iso_codes:
                date = fields.Date.to_date(curr["referenceDate"])
                try:
                    result[curr["isoCode"]] = (float(curr["eurRate"]), date)
                except ValueError:
                    continue

        return result

    @api.model
    def _parse_bnm_data(self, available_currencies):
        request_url = "https://api.bnm.gov.my/public/exchange-rate"
        request_headers = {
            "accept": "application/vnd.BNM.API.v1+json",
        }

        response = self.env["ir.egress"].request(
            "GET",
            request_url,
            purpose="currency_rate_live",
            headers=request_headers,
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()

        data = result.get("data")
        if not data:
            return False

        available_currency_names = available_currencies.mapped("name")
        result = {}

        date = datetime.datetime.now()
        for currency in data:
            currency_code = currency["currency_code"]
            if currency_code in available_currency_names:
                date = datetime.datetime.strptime(
                    currency["rate"]["date"], "%Y-%m-%d"
                ).date()
                rate = (1 / currency["rate"]["middle_rate"]) * currency["unit"]
                result[currency_code] = (float(rate), date)

        if result and "MYR" not in result:
            result["MYR"] = (1.0, date)

        return result

    @api.model
    def _parse_bi_data(self, available_currencies):
        request_url = "https://www.bi.go.id/biwebservice/wskursbi.asmx/getSubKursLokal4"
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        }

        def _fetched_bi_currency_tables(start_date):
            response = self.env["ir.egress"].request(
                "GET",
                request_url,
                purpose="currency_rate_live",
                headers=headers,
                params={"startdate": start_date},
                timeout=10,
            )
            response.raise_for_status()
            xml_tree = etree.fromstring(response.content)
            return xml_tree.xpath("//Table")

        currency_tables = []
        current_datetime = datetime.datetime.now(timezone("Asia/Jakarta"))
        request_date = current_datetime.date()

        if current_datetime.hour >= 8:
            currency_tables = _fetched_bi_currency_tables(request_date.isoformat())

        if not currency_tables:
            request_date = (current_datetime - relativedelta(days=1)).date()
            currency_tables = _fetched_bi_currency_tables(request_date.isoformat())

        result = {}
        available_currency_names = available_currencies.mapped("name")
        for table in currency_tables:
            currency_code = table.xpath("normalize-space(.//mts_subkurslokal)")
            if currency_code in available_currency_names:
                selling_rate = table.xpath("number(.//jual_subkurslokal)")
                buying_rate = table.xpath("number(.//beli_subkurslokal)")
                middle_rate = (selling_rate + buying_rate) / 2

                unit = table.xpath("number(.//nil_subkurslokal)")

                rate = (1 / middle_rate) * unit
                result[currency_code] = (rate, request_date)

        if "IDR" not in result:
            result["IDR"] = (1.0, request_date)

        return result

    @api.model
    def _parse_mnb_data(self, available_currencies):
        request_url = "http://www.mnb.hu/arfolyamok.asmx?wsdl"
        client = Client(request_url)
        rates_el = etree.fromstring(client.service.GetCurrentExchangeRates())

        result = {}
        try:
            date = datetime.datetime.strptime(
                rates_el.find("./Day").attrib["date"], "%Y-%m-%d"
            )
            rates = {
                rate_el.attrib["curr"]: int(rate_el.attrib["unit"])
                / float(rate_el.text.replace(",", "."))
                for rate_el in rates_el.findall(".//Rate")
            }
        except AttributeError, ValueError:
            return result

        for curr in available_currencies.mapped("name") & rates.keys():
            result[curr] = (rates[curr], date)

        if "HUF" not in result:
            result["HUF"] = (1.0, date)
        return result

    @api.model
    def run_update_currency(self) -> None:
        records = self.search(
            [
                ("currency_next_execution_date", "<=", fields.Date.today()),
                ("parent_id", "=", False),
            ]
        )
        if records:
            to_update = self.env["res.company"]
            for record in records:
                if record.currency_interval_unit == "daily":
                    next_update = relativedelta(days=+1)
                elif record.currency_interval_unit == "weekly":
                    next_update = relativedelta(weeks=+1)
                elif record.currency_interval_unit == "monthly":
                    next_update = relativedelta(months=+1)
                else:
                    record.currency_next_execution_date = False
                    continue
                record.currency_next_execution_date = (
                    datetime.date.today() + next_update
                )
                to_update += record
            to_update.with_context(suppress_errors=True).update_currency_rates()


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    currency_interval_unit = fields.Selection(
        related="company_id.currency_interval_unit",
        readonly=False,
    )
    currency_provider = fields.Selection(
        related="company_id.currency_provider",
        readonly=False,
    )
    currency_next_execution_date = fields.Date(
        related="company_id.currency_next_execution_date",
        readonly=False,
    )

    @api.onchange("currency_interval_unit")
    def onchange_currency_interval_unit(self) -> None:
        if self.company_id.currency_next_execution_date:
            return
        if self.currency_interval_unit == "daily":
            next_update = relativedelta(days=+1)
        elif self.currency_interval_unit == "weekly":
            next_update = relativedelta(weeks=+1)
        elif self.currency_interval_unit == "monthly":
            next_update = relativedelta(months=+1)
        else:
            self.currency_next_execution_date = False
            return
        self.currency_next_execution_date = datetime.date.today() + next_update

    def update_currency_rates_manually(self) -> None:
        self.check_singleton()
        self.company_id.update_currency_rates()
