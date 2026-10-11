/** @odoo-module native */
const FIELDS_DEFAULT = [
    {
        types: ["integer", "float", "many2one_reference"],
        value: 0,
    },
    {
        types: ["char", "selection", "html"],
        value: "",
    },
    {
        types: ["boolean", "many2one"],
        value: false,
    },
    {
        types: ["datetime"],
        value: "2024-01-01 00:00:00",
    },
    {
        types: ["date"],
        value: "2024-01-01",
    },
    {
        types: ["binary"],
        value: null,
    },
    {
        types: ["one2many", "many2many"],
        value: "[]",
    },
];

function getFieldDefaultValue(field) {
    for (const fieldDefault of FIELDS_DEFAULT) {
        if (fieldDefault.types.includes(field.type)) {
            return fieldDefault.value;
        }
    }
    return null;
}

export function getCreateDict(model) {
    const value = {};
    for (const fieldName in model.fields) {
        if (model.fields[fieldName].required) {
            value[fieldName] = getFieldDefaultValue(model.fields[fieldName]);
        }
    }
    return value;
}

export function getCrudMethodsExamples(model) {
    return {
        create: {
            responseCode: `true`,
            request: {
                vals_list: [getCreateDict(model)],
            },
        },
        read: {
            request: {
                ids: [0, 1],
                fields: ["display_name", "name", "create_date"],
            },
        },
        search: {
            responseCode: `\
[
    1,
    2
]`,
            request: {
                domain: [["display_name", "ilike", "a%"]],
            },
        },
        search_count: {
            responseCode: `10`,
            request: {
                domain: [["display_name", "ilike", "a%"]],
            },
        },
        search_read: {
            responseCode: `10`,
            request: {
                domain: [["display_name", "ilike", "a%"]],
                fields: ["display_name"],
                limit: 20,
            },
        },
        unlink: {
            responseCode: `true`,
            request: {
                ids: [],
            },
        },
        write: {
            responseCode: `true`,
            request: {
                ids: [0],
                vals: {
                    display_name: "Dope New Name",
                },
            },
        },
        name_search: {
            request: {
                domain: [["display_name", "ilike", "a%"]],
            },
            responseCode: `\
[
    [
        1,
        "Record 1 Name"
    ],
    [
        2,
        "Record 2 Name"
    ]
]`,
        },
        read_group: {
            name: "read_group",
            request: {
                fields: ["id", "display_name", "write_date"],
                groupby: "write_date",
                domain: [["display_name", "ilike", "a%"]],
            },
        },
        formatted_read_group: {
            request: {
                domain: [["display_name", "ilike", "a%"]],
                groupby: ["create_date:month"],
                aggregates: ["__count"],
            },
        },
    };
}

const ANNOTATION_DEFAULTS = {
    domaintype: () => [["display_name", "ilike", "a%"]],
    dict: () => ({}),
    mapping: () => ({}),
    valuestype: () => ({}),
    list: () => [],
    sequence: () => [],
    collection: () => [],
    iterable: () => [],
    tuple: () => [],
    set: () => [],
    bool: () => false,
    int: () => 0,
    float: () => 0,
    complex: () => 0,
    str: () => "",
};

function annotationHead(annotation) {
    const match = /^\s*([A-Za-z_][\w.]*)/.exec(annotation ?? "");
    return match ? match[1].split(".").at(-1).toLowerCase() : "";
}

export function getParameterDefaultValue(name, parameter) {
    if ("default" in parameter) {
        return parameter.default;
    }
    const build = ANNOTATION_DEFAULTS[annotationHead(parameter.annotation)];
    if (build) {
        return build();
    }
    return /args/i.test(name) ? [] : "";
}
