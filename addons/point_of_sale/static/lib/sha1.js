/*  SHA-1 implementation in JavaScript                  (c) Chris Veness 2002-2014 / MIT Licence  */
(function (_window) {
/* global define, escape, unescape */
'use strict';


/** @namespace */
var Sha1 = {};
_window.Sha1 = Sha1;

/**
 * @param {string} msg
 * @returns {string}
 */
Sha1.hash = function(msg) {
    msg = msg.utf8Encode();

    var K = [ 0x5a827999, 0x6ed9eba1, 0x8f1bbcdc, 0xca62c1d6 ];


    msg += String.fromCharCode(0x80);

    var l = msg.length/4 + 2;
    var N = Math.ceil(l/16);
    var M = new Array(N);

    for (var i=0; i<N; i++) {
        M[i] = new Array(16);
        for (var j=0; j<16; j++) {
            M[i][j] = (msg.charCodeAt(i*64+j*4)<<24) | (msg.charCodeAt(i*64+j*4+1)<<16) |
                (msg.charCodeAt(i*64+j*4+2)<<8) | (msg.charCodeAt(i*64+j*4+3));
        }
    }
    M[N-1][14] = ((msg.length-1)*8) / Math.pow(2, 32); M[N-1][14] = Math.floor(M[N-1][14]);
    M[N-1][15] = ((msg.length-1)*8) & 0xffffffff;

    var H0 = 0x67452301;
    var H1 = 0xefcdab89;
    var H2 = 0x98badcfe;
    var H3 = 0x10325476;
    var H4 = 0xc3d2e1f0;


    var W = new Array(80); var a, b, c, d, e;
    for (var i=0; i<N; i++) {

        for (var t=0;  t<16; t++) W[t] = M[i][t];
        for (var t=16; t<80; t++) W[t] = Sha1.ROTL(W[t-3] ^ W[t-8] ^ W[t-14] ^ W[t-16], 1);

        a = H0; b = H1; c = H2; d = H3; e = H4;

        for (var t=0; t<80; t++) {
            var s = Math.floor(t/20);
            var T = (Sha1.ROTL(a,5) + Sha1.f(s,b,c,d) + e + K[s] + W[t]) & 0xffffffff;
            e = d;
            d = c;
            c = Sha1.ROTL(b, 30);
            b = a;
            a = T;
        }

        H0 = (H0+a) & 0xffffffff;
        H1 = (H1+b) & 0xffffffff;
        H2 = (H2+c) & 0xffffffff;
        H3 = (H3+d) & 0xffffffff;
        H4 = (H4+e) & 0xffffffff;
    }

    return Sha1.toHexStr(H0) + Sha1.toHexStr(H1) + Sha1.toHexStr(H2) +
           Sha1.toHexStr(H3) + Sha1.toHexStr(H4);
};


/** @private */
Sha1.f = function(s, x, y, z)  {
    switch (s) {
        case 0: return (x & y) ^ (~x & z);
        case 1: return  x ^ y  ^  z;
        case 2: return (x & y) ^ (x & z) ^ (y & z);
        case 3: return  x ^ y  ^  z;
    }
};

/** @private */
Sha1.ROTL = function(x, n) {
    return (x<<n) | (x>>>(32-n));
};


/** @private */
Sha1.toHexStr = function(n) {
    var s="", v;
    for (var i=7; i>=0; i--) { v = (n>>>(i*4)) & 0xf; s += v.toString(16); }
    return s;
};




if (typeof String.prototype.utf8Encode == 'undefined') {
    String.prototype.utf8Encode = function() {
        return unescape( encodeURIComponent( this ) );
    };
}

if (typeof String.prototype.utf8Decode == 'undefined') {
    String.prototype.utf8Decode = function() {
        try {
            return decodeURIComponent( escape( this ) );
        } catch (e) {
            return this;
        }
    };
}


if (typeof module != 'undefined' && module.exports) module.exports = Sha1;
if (typeof define == 'function' && define.amd) define([], function() { return Sha1; });
})(window)
