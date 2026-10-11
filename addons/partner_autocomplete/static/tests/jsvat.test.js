import { describe, expect, test } from "@odoo/hoot";

const ORACLE = [
    ["ATU82644408", "ATU82644408"],
    ["ATU04004288", false],
    ["BE6884820468", "BE6884820468"],
    ["BE6646866606", false],
    ["BG804000240", "BG804000240"],
    ["BG848042844", false],
    ["CHE262226264", "CHE262226264"],
    ["CHE626662202", false],
    ["CY48820642E", "CY48820642E"],
    ["CY46802862E", false],
    ["CZ84688068", "CZ84688068"],
    ["CZ80802002", false],
    ["DE180820044", "DE180820044"],
    ["DE142008866", false],
    ["DK60862044", "DK60862044"],
    ["DK24066666", false],
    ["EE10204888", false],
    ["EL428000000", "EL428000000"],
    ["EL242680260", false],
    ["ESD62670468", "ESD62670468"],
    ["ESA48624444", false],
    ["FI88400008", "FI88400008"],
    ["FI08684082", false],
    ["FR60828624262", "FR60828624262"],
    ["FR66862068866", false],
    ["GB826080482", "GB826080482"],
    ["GB866262842", false],
    ["XI626482080", "XI626482080"],
    ["XI804082024", false],
    ["HR46842622462", "HR46842622462"],
    ["HR68880642060", false],
    ["HU06860060", "HU06860060"],
    ["HU44886668", false],
    ["IE4242220B", "IE4242220B"],
    ["IE2822680A", false],
    ["IT24864000864", "IT24864000864"],
    ["IT22842804488", false],
    ["LV04066885244", "LV04066885244"],
    ["LV08840862066", false],
    ["LU60828862", "LU60828862"],
    ["LU68286226", false],
    ["MT18484402", "MT18484402"],
    ["MT12486604", false],
    ["NL082246488B01", "NL082246488B01"],
    ["NL444004640B01", false],
    ["NO666686268", "NO666686268"],
    ["NO662226022", false],
    ["PL8248060442", "PL8248060442"],
    ["PL6628466226", false],
    ["PT688408800", "PT688408800"],
    ["PT886064628", false],
    ["RO148826828", "RO148826828"],
    ["RO142262880", false],
    ["RS440084400", "RS440084400"],
    ["RS868060606", false],
    ["SI18028888", "SI18028888"],
    ["SI12320840", false],
    ["SE620088608001", "SE620088608001"],
    ["SE644040884001", false],
    ["gb 123 4567 82", "GB123456782"],
    ["XI123456782", "XI123456782"],
    ["GB123456782", "GB123456782"],
    ["XI123456783", false],
    ["CHE-116.281.710 MWST", "CHE116281710MWST"],
    ["", false],
    ["ZZ123456789", false],
    ["BE 0477.472.701", "BE0477472701"],
];

describe.current.tags("headless");

test("jsvat answers as the IIFE it replaced", async () => {
    const { checkVATNumber } = await import("jsvat");
    for (const [vat, expected] of ORACLE) {
        expect(checkVATNumber(vat)).toBe(expected, { message: vat });
    }
});

test("Northern Ireland numbers follow the GB check digits", async () => {
    const { checkVATNumber } = await import("jsvat");
    expect(checkVATNumber("XI123456782")).toBe("XI123456782");
    expect(checkVATNumber("XI123456783")).toBe(false);
    expect(checkVATNumber("GB123456783")).toBe(false);
});
