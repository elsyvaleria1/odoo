import math
import re
import urllib
from functools import cache, wraps

from lxml import etree

from odoo.exceptions import UserError
from odoo.tools import OrderedSet
from odoo.tools.misc import file_path

DEFAULT_BIT_WORD_SIZE = 8


class EpcScheme:
    def __init__(self, env, name) -> None:
        """
        Parameters:
            env (Environment): the environment that translates the scheme's errors
            name (str): the name of the scheme to initialize. It MUST follows the GS1 URI convention
        """
        self.env = env
        self.name = EpcData.check_scheme_name(env, name)
        scheme_data = EpcData.get_scheme(self.name, as_dict=True)
        self.header = int(scheme_data["header_value"], 16)
        self.bit_size = int(scheme_data["bit_size"])
        table_name = scheme_data.get("partition_table", None)
        self.partition_table = EpcData.get_partition_table(table_name)
        if self.partition_table is None:
            raise UserError(
                env._(
                    "Partition table %(table_name)s not found, available tables are : %(table_list)s)",
                    table_name=table_name,
                    table_list=", ".join(EpcData.partition_table_names()),
                )
            )
        self.fields = []

        for field in scheme_data["fields_list"]["field"]:
            self.fields.append(EpcField(self, field["name"], int(field["bit_size"])))
            if field["name"] == "header":
                self.fields[-1].value = self.header
            if "ai" in field:
                self.fields[-1].ai = field["ai"]

    def encode(self, element_string, filter_value, company_prefix_length):
        if company_prefix_length and not 6 <= company_prefix_length <= 12:
            raise UserError(
                self.env._(
                    "An error occured: value of company_prefix_length (%(company_prefix_length)s) must be between 6 and 12 inclusive.",
                    company_prefix_length=company_prefix_length,
                )
            )
        ai_dict = EpcData.element_string_to_dict(element_string)
        partition_line = self.partition_table.get(company_prefix_length, None)
        next_values = None
        for field in self.fields:
            if field.name == "filter":
                field.value = filter_value
            elif field.name == "partition":
                if not partition_line:
                    raise UserError(
                        self.env._(
                            "An error occurred with field 'partition': no partition value can be found for the given company_prefix_length"
                        )
                    )
                # `next(x if cond else None for ...)` yields the FIRST item whatever it is, so
                # it returned None whenever the partition AI was not the first one in the
                # element string. The condition belongs in the generator's filter clause.
                to_process = next(
                    (
                        (key, value)
                        for key, value in ai_dict.items()
                        if key == self.partition_table["ai"]
                    ),
                    None,
                )
                if not to_process:  # The presence of the partition field is always linked to the mandatory presence of an AI to split data from in the element string
                    return self.env._(
                        "An error occured during parsing of element_string: AI code %(ai_code)s is missing for scheme %(scheme_name)s",
                        ai_code=self.partition_table["ai"],
                        scheme_name=self.name,
                    )
                next_values = EpcData.split_ai(to_process, company_prefix_length)
                field.value = partition_line["value"]
            elif next_values:
                # A size of 0 in the template means "set by the partition", which differs
                # per company prefix length: it is taken from the declared size each time.
                if field.declared_bit_size == 0:
                    field.bit_size = partition_line[
                        "left_bit" if field.name == "company_prefix" else "right_bit"
                    ]
                field.value = next_values.pop(0)
            elif field.ai and field.ai in ai_dict:
                field.value = ai_dict[field.ai]
            elif field.name != "header":
                return self.env._(
                    "An error occured with field '%(field_name)s': the corresponding AI '%(ai_code)s' was not found in the element_string",
                    field_name=field.name,
                    ai_code=field.ai,
                )

            try:
                field._encode()
            except Exception as e:
                message = self.env._(
                    "An error occurred with field '%(field_name)s': %(error_message)s",
                    field_name=field.name,
                    error_message=e,
                )
                if field.name in ("header", "filter", "partition"):
                    # When an exception happens on these fields, all incoming encoding using this scheme will fail or be corrupted
                    raise UserError(message) from e
                # Else, just warn the user for this specific data and let the process continue
                return message

        return str(self)

    def encode_partial(self, field_name, field_value) -> str:
        """To use with care: this method will not check the validity of the field value"""
        if field_name in ("header", "filter", "partition"):
            # Was `return Exception(...)`: callers use the return value as the EPC itself, so a
            # reserved field name came back as an exception *object* instead of failing.
            raise UserError(
                self.env._(
                    "Field '%(field_name)s' is a reserved field, you can't manually update its value with this method",
                    field_name=field_name,
                )
            )
        for field in self.fields:
            if field.name == field_name:
                field.value = field_value
                try:
                    field._encode()
                    return str(self)
                except UserError as e:
                    return self.env._(
                        "An error occurred with field '%(field_name)s': %(error_message)s",
                        field_name=field.name,
                        error_message=e,
                    )
        return self.env._("Field '%(field_name)s' not found", field_name=field_name)

    def __str__(self):
        total_size = EpcData.normalize_epc_length(
            sum(len(field.raw_value) for field in self.fields)
        )
        bit_string = "".join(field.raw_value for field in self.fields).ljust(
            total_size, "0"
        )
        return f"{int(bit_string, 2):x}"


class EpcField:
    def __init__(self, scheme, name, bit_size) -> None:
        self.scheme = scheme
        field_data = EpcData.get_field(name, as_dict=True)
        self.name = field_data["name"]
        self.encoding = field_data["encoding"]
        self.declared_bit_size = bit_size
        self.bit_size = bit_size
        self.value = 0
        self.raw_value = 0
        self.ai = None

    def _encode(self):
        method_name = f"_encode_{self.encoding}"
        encoder = {
            "integer": self._encode_integer,
            "string": self._encode_string,
            "partition_table": self._encode_partition_table,
        }.get(self.encoding)
        if encoder:
            try:
                self.raw_value = encoder()
            except Exception as e:
                raise UserError(
                    self.scheme.env._(
                        "An error occurred with method '%(method_name)s': %(error_message)s",
                        method_name=method_name,
                        error_message=e,
                    )
                ) from e
        else:
            raise AttributeError(f"The encoding '{self.encoding}' is not supported.")

    def _encode_integer(self):
        return EpcData.write_bits(int(self.value), self.bit_size)

    def _encode_string(self):
        self._check_character_set()
        formatted_value = self.ascii_to_bits(urllib.parse.unquote(self.value))
        return EpcData.write_bits(
            formatted_value,
            self.bit_size,
            word_size_write=7,
            pad_side="right",
        )

    def _encode_partition_table(self):
        return self._encode_integer()

    def ascii_to_bits(self, input_string):
        return int.from_bytes(input_string.encode("ascii"), byteorder="big")

    def _check_character_set(self) -> None:
        # c.f. [TDS 2.1] §A
        # Allowed characters: A-Z, a-z, 0-9, !"%&'()*+,-./_:;<=>?
        # Notice some special characters are not allowed, even if they're part of ASCII : (Space) @#$[]^`{|}~
        invalid_chars = OrderedSet(
            "".join(re.findall(r'[^A-Za-z0-9!"%&\'()*+,\-./_:;<=>?]', self.value))
        )
        if invalid_chars:
            raise UserError(
                self.scheme.env._(
                    "Value to encode contains invalid character(s): %(invalid_chars)s",
                    invalid_chars="`" + "`, `".join(invalid_chars) + "`",
                )
            )


class EpcData:
    @classmethod
    def element_string_to_dict(cls, element_string):
        """Extracts a list of tuples from an element string."""
        return dict(
            re.findall(r"(?:\(\s*(\d{2,4})\s*\)\s*([^\(\)\s]+)?)", element_string)
        )

    @classmethod
    def split_ai(cls, element, company_prefix_length) -> list | None:
        """With Schemes from TDS < 2.0, EPC encoding need to separate the company prefix
        from the other values it is associated with in the AI code.
        It may also be necessary to rearrange some digits depending on the AI code.
        See TDS 2.1 § 7

        input : single ai code as tuple eg ('01', '12345')
        output : list of 2 to 4 elements (e.g. ITIP scheme extract 4 data from a single (8006) AI code)

        Remaining AI : scheme -> number of elements
        00   : sscc  -> 2; 414  : sgln  -> 2; 8003 : grai  -> 3; 8004 : giai  -> 2; 8018 : gsrn  -> 2
        8017 : gsrnp -> 2; 253  : gdti  -> 3; 8010 : cpi   -> 2; 255  : sgcn  -> 3; 8006 : itip  -> 4
        ?Not related to a binary scheme : (401  : ginc -> 2; 402  : gsin -> 2; 417  : pgln -> 2)
        """
        if element[0] == "01":
            # GTIN "A.BBBBBBB.CCCCC.D" -> [CompanyPrefix: BBBBBBB, ItemRef with indicator: ACCCCC]
            value = element[
                1
            ].rjust(
                14, "0"
            )  # Enforce length to be 14 as required by GS1 specification for consistent result
            return [
                value[1 : 1 + company_prefix_length],
                value[0:1] + value[1 + company_prefix_length : -1],
            ]
        return None

    @classmethod
    def write_bits(
        cls,
        value,
        length,
        pad_side="left",
        pad_char="0",
        word_size_write=DEFAULT_BIT_WORD_SIZE,
        word_size_read=DEFAULT_BIT_WORD_SIZE,
        word_pad_side="left",
        word_pad_char="0",
    ):
        """Return the binary representation of ``value`` on ``length`` bits.

        ``write_bits(5, 8)`` gives ``'00000101'``.

        :param int value: integer to convert
        :param int length: length of the binary representation; the string is
            padded up to it
        :param str pad_side: side on which the whole string is padded, ``'left'``
            or ``'right'``
        :param str pad_char: padding character for the whole string, ``'0'`` or ``'1'``
        :param int word_size_write: bits written per word, in ``[1, 8]``. EPC
            nomenclatures encode their inputs (ASCII, ...) on 8-bit words.
        :param int word_size_read: bits each word of ``value`` is read on
        :param str word_pad_side: side on which each word is padded, ``'left'`` or
            ``'right'``
        :param str word_pad_char: padding character for each word, ``'0'`` or ``'1'``
        :return: the padded binary representation
        :rtype: str
        :raises ValueError: if ``value`` cannot be represented on ``length`` bits,
            or an argument is out of its domain
        """
        # This check used to sit *below* `value.bit_length()`, so a non-int raised AttributeError
        # before ever reaching it — and its own message passed a positional argument to a
        # named-placeholder format string, which raises "format requires a mapping". Both the
        # order and the call are fixed here.
        if not isinstance(value, int):
            raise ValueError(f"Value '{value}' must be an integer")
        if length <= 0:
            raise ValueError("Length must be a positive integer")
        if word_size_write <= 0:
            raise ValueError("Word size must be a positive integer")
        tot_bits = value.bit_length()
        if tot_bits > length:
            raise ValueError(f"Value {value} cannot be represented with {length} bits")
        if pad_side not in ["left", "right"]:
            raise ValueError(f"Invalid pad_side '{pad_side}'. Use 'left' or 'right'.")
        if word_pad_side not in ["left", "right"]:
            raise ValueError(
                f"Invalid word_pad_side '{word_pad_side}'. Use 'left' or 'right'."
            )
        if pad_char not in ["0", "1"]:
            raise ValueError(f"Invalid pad_char '{pad_char}'. Use '0' or '1'.")
        if word_pad_char not in ["0", "1"]:
            raise ValueError(
                f"Invalid word_pad_char '{word_pad_char}'. Use '0' or '1'."
            )

        if length <= word_size_write or word_size_write == word_size_read:
            bit_string = f"{value:{pad_char}{length}b}"
        else:
            smaller = word_size_write < word_size_read
            word_number = math.ceil(tot_bits / word_size_read)
            normalized_bits = word_number * word_size_read
            default_bit_string = f"{value:{0}{normalized_bits}b}"
            bit_array = []
            for i in range(word_number):
                word = default_bit_string[word_size_read * i : word_size_read * (i + 1)]
                if smaller:
                    if int(word[: word_size_read - word_size_write], 2) != 0:
                        raise ValueError(
                            f"Binary value {word} cannot be represented with {word_size_write} bits"
                        )
                    bit_array.append(word[word_size_read - word_size_write :])
                elif word_pad_side == "left":
                    bit_array.append(word.rjust(word_size_write, word_pad_char))
                else:
                    bit_array.append(word.ljust(word_size_write, word_pad_char))
            bit_string = "".join(bit_array)

        if pad_side == "left":
            padded_bit_string = bit_string.rjust(
                length, pad_char
            )  # May seem confusing but rjust = right justify, so it means that the string is padded on the left
        else:
            padded_bit_string = bit_string.ljust(length, pad_char)

        return padded_bit_string

    @classmethod
    def normalize_epc_length(cls, raw_length):
        # EPC encoding must have a multiple of 16 bits.
        # c.f. [TDS  2.1], §15.1.1
        return raw_length + cls._missing_epc_bit(raw_length)

    @classmethod
    def _missing_epc_bit(cls, raw_length):
        remainder = raw_length % 16
        return (16 - remainder) if remainder else 0

    @classmethod
    def xml_to_dict(cls, func):
        """Extend the function with the as_dict parameter to return the XML element as a list of dicts when set to True"""

        @wraps(func)
        def wrapper_func(*args, **kwargs):
            as_dict = kwargs.pop("as_dict", False)
            xml_element = func(*args, **kwargs)
            if as_dict:
                return cls._parse_xml_as_dict(xml_element)
            return xml_element

        return wrapper_func

    @classmethod
    @cache
    def _xml_tree(cls):
        return etree.parse(file_path("stock_barcode/data/epc_template.xml"))

    @classmethod
    @cache
    def scheme_names(cls):
        """Every scheme the template defines. Frozen because it is what bounds the caches
        below: their keys used to come straight off the wire (`/stock_barcode/get_epc` takes
        `scheme_name` from the client), so an unbounded `@cache` grew one entry per distinct
        string an authenticated caller cared to send."""
        return frozenset(cls._xml_tree().xpath("//epc_template/schemes/scheme/@name"))

    @classmethod
    def check_scheme_name(cls, env, scheme_name):
        if scheme_name not in cls.scheme_names():
            raise UserError(
                env._(
                    "Unknown EPC scheme %(scheme_name)s. Known schemes are: %(scheme_list)s",
                    scheme_name=scheme_name,
                    scheme_list=", ".join(sorted(cls.scheme_names())),
                )
            )
        return scheme_name

    @classmethod
    @cache
    def get_scheme(cls, scheme_name):
        # `scheme_name` is checked against `scheme_names()` before it gets here, so it can no
        # longer alter the XPath expression it is interpolated into.
        if scheme_name not in cls.scheme_names():
            raise ValueError(f"Unknown EPC scheme {scheme_name!r}")
        return cls._xml_tree().xpath(
            f"//epc_template/schemes/scheme[@name='{scheme_name}']"
        )

    @classmethod
    def partition_table_names(cls):
        return cls._xml_tree().xpath(
            "//epc_template/partition_tables/partition_table/@name"
        )

    @classmethod
    @cache
    def get_partition_table(cls, table_name):
        if not table_name:
            return {}
        partition_table = cls._parse_xml_as_dict(
            cls._xml_tree().xpath(
                f"//epc_template/partition_tables/partition_table[@name='{table_name}']"
            )
        )
        if not partition_table:
            return None
        res = {"ai": partition_table["ai_required"]}
        res.update(
            {
                int(key["left_digit"]): {
                    "value": int(key["value"]),
                    "left_bit": int(key["left_bit"]),
                    "right_bit": int(key["right_bit"]),
                    "right_digit": int(key["right_digit"]),
                }
                for key in partition_table["key"]
            }
        )
        return res

    @classmethod
    @cache
    def get_field(cls, field_name):
        return cls._xml_tree().xpath(
            f"//epc_template/fields/field[@name='{field_name}']"
        )

    @classmethod
    def _parse_xml_as_dict(cls, element):
        """Return a list of dicts"""

        def _element_to_dict(elem):
            node = {}
            # Process element's attributes
            if elem.attrib:
                node.update((k, v) for k, v in elem.attrib.items())
            # Process element's children
            for child in elem:
                child_dict = _element_to_dict(child)
                if child.tag not in node:
                    node[child.tag] = child_dict
                else:
                    if not isinstance(node[child.tag], list):
                        node[child.tag] = [node[child.tag]]
                    node[child.tag].append(child_dict)
            # Process element's text content
            if elem.text and elem.text.strip():
                text = elem.text.strip()
                if node:
                    node["text"] = text
                else:
                    node = text
            return node

        if not element:
            return None
        if isinstance(element, list) and len(element) > 1:
            return [_element_to_dict(elem) for elem in element]
        return _element_to_dict(element[0])


# Apply xml_to_dict after @classmethod using an explicit wrapping step.
EpcData.get_scheme = EpcData.xml_to_dict(EpcData.get_scheme)
EpcData.get_field = EpcData.xml_to_dict(EpcData.get_field)
