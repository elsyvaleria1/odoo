
    const vatexp = [];


    vatexp.push(/^(AT)U(\d{8})$/);
    vatexp.push(/^(BE)(\d{9,10})$/);
    vatexp.push(/^(BG)(\d{9,10})$/);
    vatexp.push(/^(CHE)(\d{9})(MWST|TVA|IVA)?$/);
    vatexp.push(/^(CY)([0-59]\d{7}[A-Z])$/);
    vatexp.push(/^(CZ)(\d{8,10})(\d{3})?$/);
    vatexp.push(/^(DE)([1-9]\d{8})$/);
    vatexp.push(/^(DK)(\d{8})$/);
    vatexp.push(/^(EE)(10\d{7})$/);
    vatexp.push(/^(EL)(\d{9})$/);
    vatexp.push(/^(ES)([A-Z]\d{8})$/);
    vatexp.push(/^(ES)([A-HN-SW]\d{7}[A-J])$/);
    vatexp.push(/^(ES)([0-9YZ]\d{7}[A-Z])$/);
    vatexp.push(/^(ES)([KLMX]\d{7}[A-Z])$/);
    vatexp.push(/^(EU)(\d{9})$/);
    vatexp.push(/^(FI)(\d{8})$/);
    vatexp.push(/^(FR)(\d{11})$/);
    vatexp.push(/^(FR)([A-HJ-NP-Z]\d{10})$/);
    vatexp.push(/^(FR)(\d[A-HJ-NP-Z]\d{9})$/);
    vatexp.push(/^(FR)([A-HJ-NP-Z]{2}\d{9})$/);
    vatexp.push(/^(GB|XI)(\d{9})$/);
    vatexp.push(/^(GB|XI)(\d{12})$/);
    vatexp.push(/^(GB)(GD\d{3})$/);
    vatexp.push(/^(GB)(HA\d{3})$/);
    vatexp.push(/^(HR)(\d{11})$/);
    vatexp.push(/^(HU)(\d{8})$/);
    vatexp.push(/^(IE)(\d{7}[A-W])$/);
    vatexp.push(/^(IE)([7-9][A-Z\*\+)]\d{5}[A-W])$/);
    vatexp.push(/^(IE)(\d{7}[A-W][AH])$/);
    vatexp.push(/^(IT)(\d{11})$/);
    vatexp.push(/^(LV)(\d{11})$/);
    vatexp.push(/^(LT)(\d{9}|\d{12})$/);
    vatexp.push(/^(LU)(\d{8})$/);
    vatexp.push(/^(MT)([1-9]\d{7})$/);
    vatexp.push(/^(NL)(\d{9})B\d{2}$/);
    vatexp.push(/^(NO)(\d{9})$/);
    vatexp.push(/^(PL)(\d{10})$/);
    vatexp.push(/^(PT)(\d{9})$/);
    vatexp.push(/^(RO)([1-9]\d{1,9})$/);
    vatexp.push(/^(RU)(\d{10}|\d{12})$/);
    vatexp.push(/^(RS)(\d{9})$/);
    vatexp.push(/^(SI)([1-9]\d{7})$/);
    vatexp.push(/^(SK)([1-9]\d[2346-9]\d{7})$/);
    vatexp.push(/^(SE)(\d{10}01)$/);

    export function checkVATNumber(toCheck) {
        var VATNumber = toCheck.toUpperCase();

        VATNumber = VATNumber.replace(/(\s|-|\.)+/g, '');

        var valid = false;

        for (var i = 0; i < vatexp.length; i++) {

            if (vatexp[i].test(VATNumber)) {

                const [, cCode, cNumber] = vatexp[i].exec(VATNumber);

                if (CHECK_DIGIT[cCode](cNumber)) valid = VATNumber;

                break;
            }
        }

        return valid;
    }

    function ATVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [1, 2, 1, 2, 1, 2, 1];
        var temp = 0;

        for (var i = 0; i < 7; i++) {
            temp = Number(vatnumber.charAt(i)) * multipliers[i];
            if (temp > 9)
                total += Math.floor(temp / 10) + temp % 10;
            else
                total += temp;
        }

        total = 10 - (total + 4) % 10;
        if (total == 10) total = 0;

        if (total == vatnumber.slice(7, 8))
            return true;
        else
            return false;
    }

    function BEVATCheckDigit(vatnumber) {


        if (vatnumber.length == 9) vatnumber = "0" + vatnumber;

        if (97 - vatnumber.slice(0, 8) % 97 == vatnumber.slice(8, 10))
            return true;
        else
            return false;
    }

    function BGVATCheckDigit(vatnumber) {
        var temp, total, multipliers, i;


        if (vatnumber.length == 9) {
            total = 0;

            temp = 0;
            for (i = 0; i < 8; i++) temp += Number(vatnumber.charAt(i)) * (i + 1);

            total = temp % 11;
            if (total != 10) {
                if (total == vatnumber.slice(8))
                    return true;
                else
                    return false;
            }

            temp = 0;
            for (i = 0; i < 8; i++) temp += Number(vatnumber.charAt(i)) * (i + 3);

            total = temp % 11;
            if (total == 10) total = 0;
            if (total == vatnumber.slice(8))
                return true;
            else
                return false;
        }

        if ((/^\d\d[0-5]\d[0-3]\d\d{4}$/).test(vatnumber)) {

            var month = Number(vatnumber.slice(2, 4));
            if ((month > 0 && month < 13) || (month > 20 && month < 33) || (month > 40 && month < 53)) {

                multipliers = [2, 4, 8, 5, 10, 9, 7, 3, 6];
                total = 0;
                for (i = 0; i < 9; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

                total = total % 11;
                if (total == 10) total = 0;

                if (total == vatnumber.substr(9, 1)) return true;
            }
        }


        multipliers = [21, 19, 17, 13, 11, 9, 7, 3, 1];
        total = 0;
        for (i = 0; i < 9; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        if (total % 10 == vatnumber.substr(9, 1)) return true;


        multipliers = [4, 3, 2, 7, 6, 5, 4, 3, 2];
        total = 0;
        for (i = 0; i < 9; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 11 - total % 11;
        if (total == 10) return false;
        if (total == 11) total = 0;

        if (total == vatnumber.substr(9, 1))
            return true;
        else
            return false;
    }

    function CHEVATCheckDigit(vatnumber) {


        var multipliers = [5, 4, 3, 2, 7, 6, 5, 4];
        var total = 0;
        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 11 - total % 11;
        if (total == 10) return false;
        if (total == 11) total = 0;

        if (total == vatnumber.substr(8, 1))
            return true;
        else
            return false;
    }

    function CYVATCheckDigit(vatnumber) {


        if (Number(vatnumber.slice(0, 2) == 12)) return false;

        var total = 0;
        for (var i = 0; i < 8; i++) {
            var temp = Number(vatnumber.charAt(i));
            if (i % 2 == 0) {
                switch (temp) {
                    case 0:
                        temp = 1;
                        break;
                    case 1:
                        temp = 0;
                        break;
                    case 2:
                        temp = 5;
                        break;
                    case 3:
                        temp = 7;
                        break;
                    case 4:
                        temp = 9;
                        break;
                    default:
                        temp = temp * 2 + 3;
                }
            }
            total += temp;
        }

        total = total % 26;
        total = String.fromCharCode(total + 65);

        if (total == vatnumber.substr(8, 1))
            return true;
        else
            return false;
    }

    function CZVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [8, 7, 6, 5, 4, 3, 2];

        var czexp = new Array();
        czexp[0] = (/^\d{8}$/);
        czexp[1] = (/^[0-5][0-9][0|1|5|6][0-9][0-3][0-9]\d{3}$/);
        czexp[2] = (/^6\d{8}$/);
        czexp[3] = (/^\d{2}[0-3|5-8][0-9][0-3][0-9]\d{4}$/);
        var i = 0;
        var a;

        if (czexp[0].test(vatnumber)) {

            for (i = 0; i < 7; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

            total = 11 - total % 11;
            if (total == 10) total = 0;
            if (total == 11) total = 1;

            if (total == vatnumber.slice(7, 8))
                return true;
            else
                return false;
        }

        else if (czexp[1].test(vatnumber)) {
            if (Number(vatnumber.slice(0, 2)) > 62) return false;
            return true;
        }

        else if (czexp[2].test(vatnumber)) {

            for (i = 0; i < 7; i++) total += Number(vatnumber.charAt(i + 1)) * multipliers[i];

            if (total % 11 == 0)
                a = total + 11;
            else
                a = Math.ceil(total / 11) * 11;
            var pointer = a - total;

            var lookup = [8, 7, 6, 5, 4, 3, 2, 1, 0, 9, 8];
            if (lookup[pointer - 1] == vatnumber.slice(8, 9))
                return true;
            else
                return false;
        }

        else if (czexp[3].test(vatnumber)) {
            var temp = Number(vatnumber.slice(0, 2)) + Number(vatnumber.slice(2, 4)) + Number(vatnumber.slice(4, 6)) + Number(vatnumber.slice(6, 8)) + Number(vatnumber.slice(8));
            if (temp % 11 == 0 && Number(vatnumber) % 11 == 0)
                return true;
            else
                return false;
        }

        return false;
    }

    function DEVATCheckDigit(vatnumber) {


        var product = 10;
        var sum = 0;
        var checkdigit = 0;
        for (var i = 0; i < 8; i++) {

            sum = (Number(vatnumber.charAt(i)) + product) % 10;
            if (sum == 0) {
                sum = 10;
            }
            product = (2 * sum) % 11;
        }

        if (11 - product == 10) {
            checkdigit = 0;
        } else {
            checkdigit = 11 - product;
        }

        if (checkdigit == vatnumber.slice(8, 9))
            return true;
        else
            return false;
    }

    function DKVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [2, 7, 6, 5, 4, 3, 2, 1];

        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = total % 11;

        if (total == 0)
            return true;
        else
            return false;
    }

    function EEVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [3, 7, 1, 3, 7, 1, 3, 7];

        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 10 - total % 10;
        if (total == 10) total = 0;

        if (total == vatnumber.slice(8, 9))
            return true;
        else
            return false;
    }

    function ELVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [256, 128, 64, 32, 16, 8, 4, 2];

        if (vatnumber.length == 8) {
            vatnumber = "0" + vatnumber;
        }

        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = total % 11;
        if (total > 9) {
            total = 0;
        }

        if (total == vatnumber.slice(8, 9))
            return true;
        else
            return false;
    }

    function ESVATCheckDigit(vatnumber) {


        var total = 0;
        var temp = 0;
        var multipliers = [2, 1, 2, 1, 2, 1, 2];
        var esexp = new Array();
        esexp[0] = (/^[A-H|J|U|V]\d{8}$/);
        esexp[1] = (/^[A-H|N-S|W]\d{7}[A-J]$/);
        esexp[2] = (/^[0-9|Y|Z]\d{7}[A-Z]$/);
        esexp[3] = (/^[K|L|M|X]\d{7}[A-Z]$/);
        var i = 0;

        if (esexp[0].test(vatnumber)) {

            for (i = 0; i < 7; i++) {
                temp = Number(vatnumber.charAt(i + 1)) * multipliers[i];
                if (temp > 9)
                    total += Math.floor(temp / 10) + temp % 10;
                else
                    total += temp;
            }
            total = 10 - total % 10;
            if (total == 10) {
                total = 0;
            }

            if (total == vatnumber.slice(8, 9))
                return true;
            else
                return false;
        }

        else if (esexp[1].test(vatnumber)) {

            for (i = 0; i < 7; i++) {
                temp = Number(vatnumber.charAt(i + 1)) * multipliers[i];
                if (temp > 9)
                    total += Math.floor(temp / 10) + temp % 10;
                else
                    total += temp;
            }

            total = 10 - total % 10;
            total = String.fromCharCode(total + 64);

            if (total == vatnumber.slice(8, 9))
                return true;
            else
                return false;
        }

        else if (esexp[2].test(vatnumber)) {
            var tempnumber = vatnumber;
            if (tempnumber.substring(0, 1) == 'Y') tempnumber = tempnumber.replace(/Y/, "1");
            if (tempnumber.substring(0, 1) == 'Z') tempnumber = tempnumber.replace(/Z/, "2");
            return tempnumber.charAt(8) == 'TRWAGMYFPDXBNJZSQVHLCKE'.charAt(Number(tempnumber.substring(0, 8)) % 23);
        }

        else if (esexp[3].test(vatnumber)) {
            return vatnumber.charAt(8) == 'TRWAGMYFPDXBNJZSQVHLCKE'.charAt(Number(vatnumber.substring(1, 8)) % 23);
        }

        else return false;
    }

    function EUVATCheckDigit(vatnumber) {

        return true;
    }

    function FIVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [7, 9, 10, 5, 8, 4, 2];

        for (var i = 0; i < 7; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 11 - total % 11;
        if (total > 9) {
            total = 0;
        }

        if (total == vatnumber.slice(7, 8))
            return true;
        else
            return false;
    }

    function FRVATCheckDigit(vatnumber) {


        if (!(/^\d{11}$/).test(vatnumber)) return true;

        var total = vatnumber.substring(2);

        total = (total * 100 + 12) % 97;

        if (total == vatnumber.slice(0, 2))
            return true;
        else
            return false;
    }

    function GBVATCheckDigit(vatnumber) {


        var multipliers = [8, 7, 6, 5, 4, 3, 2];

        if (vatnumber.substr(0, 2) == 'GD') {
            if (vatnumber.substr(2, 3) < 500)
                return true;
            else
                return false;
        }

        if (vatnumber.substr(0, 2) == 'HA') {
            if (vatnumber.substr(2, 3) > 499)
                return true;
            else
                return false;
        }

        var total = 0;

        if (Number(vatnumber.slice(0)) == 0) return false;

        var no = Number(vatnumber.slice(0, 7));

        for (var i = 0; i < 7; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];


        var cd = total;
        while (cd > 0) {
            cd = cd - 97;
        }

        cd = Math.abs(cd);
        if (cd == vatnumber.slice(7, 9) && no < 9990001 && (no < 100000 || no > 999999) && (no < 9490001 || no > 9700000)) return true;

        if (cd >= 55)
            cd = cd - 55;
        else
            cd = cd + 42;
        if (cd == vatnumber.slice(7, 9) && no > 1000000)
            return true;
        else
            return false;
    }

    function HRVATCheckDigit(vatnumber) {


        var product = 10;
        var sum = 0;
        var checkdigit = 0;

        for (var i = 0; i < 10; i++) {

            sum = (Number(vatnumber.charAt(i)) + product) % 10;
            if (sum == 0) {
                sum = 10;
            }
            product = (2 * sum) % 11;
        }

        if ((product + vatnumber.slice(10, 11) * 1) % 10 == 1)
            return true;
        else
            return false;
    }

    function HUVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [9, 7, 3, 1, 9, 7, 3];

        for (var i = 0; i < 7; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 10 - total % 10;
        if (total == 10) total = 0;

        if (total == vatnumber.slice(7, 8))
            return true;
        else
            return false;
    }

    function IEVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [8, 7, 6, 5, 4, 3, 2];

        if (/^\d[A-Z\*\+]/.test(vatnumber)) vatnumber = "0" + vatnumber.substring(2, 7) + vatnumber.substring(0, 1) + vatnumber.substring(7, 8);

        for (var i = 0; i < 7; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        if (/^\d{7}[A-Z][AH]$/.test(vatnumber)) {

            if (vatnumber.charAt(8) == 'H')
                total += 72;
            else
                total += 9;
        }

        total = total % 23;
        if (total == 0)
            total = "W";
        else
            total = String.fromCharCode(total + 64);

        if (total == vatnumber.slice(7, 8))
            return true;
        else
            return false;
    }

    function ITVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2];
        var temp;

        if (Number(vatnumber.slice(0, 7)) == 0) return false;
        temp = Number(vatnumber.slice(7, 10));
        if ((temp < 1) || (temp > 201) && temp != 999 && temp != 888) return false;

        for (var i = 0; i < 10; i++) {
            temp = Number(vatnumber.charAt(i)) * multipliers[i];
            if (temp > 9)
                total += Math.floor(temp / 10) + temp % 10;
            else
                total += temp;
        }

        total = 10 - total % 10;
        if (total > 9) {
            total = 0;
        }

        if (total == vatnumber.slice(10, 11))
            return true;
        else
            return false;
    }

    function LTVATCheckDigit(vatnumber) {

        var total, multipliers, i;

        if (vatnumber.length == 9) {

            if (!(/^\d{7}1/).test(vatnumber)) return false;

            total = 0;
            for (i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * (i + 1);

            if (total % 11 == 10) {
                multipliers = [3, 4, 5, 6, 7, 8, 9, 1];
                total = 0;
                for (i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];
            }

            total = total % 11;
            if (total == 10) {
                total = 0;
            }

            if (total == vatnumber.slice(8, 9))
                return true;
            else
                return false;
        }

        else {

            if (!(/^\d{10}1/).test(vatnumber)) return false;

            total = 0;
            multipliers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1, 2];
            for (i = 0; i < 11; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

            if (total % 11 == 10) {
                multipliers = [3, 4, 5, 6, 7, 8, 9, 1, 2, 3, 4];
                total = 0;
                for (i = 0; i < 11; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];
            }

            total = total % 11;
            if (total == 10) {
                total = 0;
            }

            if (total == vatnumber.slice(11, 12))
                return true;
            else
                return false;
        }
    }

    function LUVATCheckDigit(vatnumber) {


        if (vatnumber.slice(0, 6) % 89 == vatnumber.slice(6, 8))
            return true;
        else
            return false;
    }

    function LVVATCheckDigit(vatnumber) {


        if ((/^[0-3]/).test(vatnumber)) {
            if ((/^[0-3][0-9][0-1][0-9]/).test(vatnumber))
                return true;
            else
                return false;
        }

        else {

            var total = 0;
            var multipliers = [9, 1, 4, 8, 3, 10, 2, 5, 7, 6];

            for (var i = 0; i < 10; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

            if (total % 11 == 4 && vatnumber[0] == 9) total = total - 45;
            if (total % 11 == 4)
                total = 4 - total % 11;
            else if (total % 11 > 4)
                total = 14 - total % 11;
            else if (total % 11 < 4)
                total = 3 - total % 11;

            if (total == vatnumber.slice(10, 11))
                return true;
            else
                return false;
        }
    }

    function MTVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [3, 4, 6, 7, 8, 9];

        for (var i = 0; i < 6; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 37 - total % 37;

        if (total == vatnumber.slice(6, 8) * 1)
            return true;
        else
            return false;
    }

    function NLVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [9, 8, 7, 6, 5, 4, 3, 2];

        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = total % 11;
        if (total > 9) {
            total = 0;
        }

        if (total == vatnumber.slice(8, 9))
            return true;
        else
            return false;
    }

    function NOVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [3, 2, 7, 6, 5, 4, 3, 2];

        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 11 - total % 11;
        if (total == 11) {
            total = 0;
        }
        if (total < 10) {

            if (total == vatnumber.slice(8, 9))
                return true;
            else
                return false;
        }
    }

    function PLVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [6, 5, 7, 2, 3, 4, 5, 6, 7];

        for (var i = 0; i < 9; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = total % 11;
        if (total > 9) {
            total = 0;
        }

        if (total == vatnumber.slice(9, 10))
            return true;
        else
            return false;
    }

    function PTVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [9, 8, 7, 6, 5, 4, 3, 2];

        for (var i = 0; i < 8; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 11 - total % 11;
        if (total > 9) {
            total = 0;
        }

        if (total == vatnumber.slice(8, 9))
            return true;
        else
            return false;
    }

    function ROVATCheckDigit(vatnumber) {


        var multipliers = [7, 5, 3, 2, 1, 7, 5, 3, 2];

        var VATlen = vatnumber.length;
        multipliers = multipliers.slice(10 - VATlen);
        var total = 0;
        for (var i = 0; i < vatnumber.length - 1; i++) {
            total += Number(vatnumber.charAt(i)) * multipliers[i];
        }

        total = (10 * total) % 11;
        if (total == 10) total = 0;

        if (total == vatnumber.slice(vatnumber.length - 1, vatnumber.length))
            return true;
        else
            return false;
    }

    function RSVATCheckDigit(vatnumber) {


        var product = 10;
        var sum = 0;
        var checkdigit = 0;

        for (var i = 0; i < 8; i++) {

            sum = (Number(vatnumber.charAt(i)) + product) % 10;
            if (sum == 0) {
                sum = 10;
            }
            product = (2 * sum) % 11;
        }

        if ((product + vatnumber.slice(8, 9) * 1) % 10 == 1)
            return true;
        else
            return false;
    }

    function RUVATCheckDigit(vatnumber) {


        var i;

        if (vatnumber.length == 10) {
            var total = 0;
            var multipliers = [2, 4, 10, 3, 5, 9, 4, 6, 8, 0];
            for (i = 0; i < 10; i++) {
                total += Number(vatnumber.charAt(i)) * multipliers[i];
            }
            total = total % 11;
            if (total > 9) {
                total = total % 10;
            }

            if (total == vatnumber.slice(9, 10))
                return true;
            else
                return false;

        } else if (vatnumber.length == 12) {
            var total1 = 0;
            var multipliers1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0];
            var total2 = 0;
            var multipliers2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0];

            for (i = 0; i < 11; i++) total1 += Number(vatnumber.charAt(i)) * multipliers1[i];
            total1 = total1 % 11;
            if (total1 > 9) {
                total1 = total1 % 10;
            }

            for (i = 0; i < 11; i++) total2 += Number(vatnumber.charAt(i)) * multipliers2[i];
            total2 = total2 % 11;
            if (total2 > 9) {
                total2 = total2 % 10;
            }

            if ((total1 == vatnumber.slice(10, 11)) && (total2 == vatnumber.slice(11, 12)))
                return true;
            else
                return false;
        }
    }

    function SEVATCheckDigit(vatnumber) {
        var i;

        var R = 0;
        var digit;
        for (i = 0; i < 9; i = i + 2) {
            digit = Number(vatnumber.charAt(i));
            R += Math.floor(digit / 5) + ((digit * 2) % 10);
        }

        var S = 0;
        for (i = 1; i < 9; i = i + 2) S += Number(vatnumber.charAt(i));

        var cd = (10 - (R + S) % 10) % 10;

        if (cd == vatnumber.slice(9, 10))
            return true;
        else
            return false;
    }

    function SIVATCheckDigit(vatnumber) {


        var total = 0;
        var multipliers = [8, 7, 6, 5, 4, 3, 2];

        for (var i = 0; i < 7; i++) total += Number(vatnumber.charAt(i)) * multipliers[i];

        total = 11 - total % 11;
        if (total == 10) {
            total = 0;
        }

        if (total != 11 && total == vatnumber.slice(7, 8))
            return true;
        else
            return false;
    }

    function SKVATCheckDigit(vatnumber) {


        if (Number(vatnumber % 11) == 0)
            return true;
        else
            return false;
    }

    const CHECK_DIGIT = {
        AT: ATVATCheckDigit,
        BE: BEVATCheckDigit,
        BG: BGVATCheckDigit,
        CHE: CHEVATCheckDigit,
        CY: CYVATCheckDigit,
        CZ: CZVATCheckDigit,
        DE: DEVATCheckDigit,
        DK: DKVATCheckDigit,
        EE: EEVATCheckDigit,
        EL: ELVATCheckDigit,
        ES: ESVATCheckDigit,
        EU: EUVATCheckDigit,
        FI: FIVATCheckDigit,
        FR: FRVATCheckDigit,
        GB: GBVATCheckDigit,
        HR: HRVATCheckDigit,
        HU: HUVATCheckDigit,
        IE: IEVATCheckDigit,
        IT: ITVATCheckDigit,
        LT: LTVATCheckDigit,
        LU: LUVATCheckDigit,
        LV: LVVATCheckDigit,
        MT: MTVATCheckDigit,
        NL: NLVATCheckDigit,
        NO: NOVATCheckDigit,
        PL: PLVATCheckDigit,
        PT: PTVATCheckDigit,
        RO: ROVATCheckDigit,
        RS: RSVATCheckDigit,
        RU: RUVATCheckDigit,
        SE: SEVATCheckDigit,
        SI: SIVATCheckDigit,
        SK: SKVATCheckDigit,
        XI: GBVATCheckDigit,
    };
