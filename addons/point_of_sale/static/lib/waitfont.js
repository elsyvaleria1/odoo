(function(){
    function waitForWebfonts(fonts, callback) {
        var loadedFonts = 0;
        for(var i = 0, l = fonts.length; i < l; ++i) {
            (function(font) {
                var node = document.createElement('span');
                node.innerHTML = 'giItT1WQy@!-/#';
                node.style.position      = 'absolute';
                node.style.left          = '-10000px';
                node.style.top           = '-10000px';
                node.style.fontSize      = '300px';
                node.style.fontFamily    = 'sans-serif';
                node.style.fontVariant   = 'normal';
                node.style.fontStyle     = 'normal';
                node.style.fontWeight    = 'normal';
                node.style.letterSpacing = '0';
                document.body.appendChild(node);

                var width = node.offsetWidth;

                node.style.fontFamily = font;

                var interval;
                function checkFont() {
                    if(node && node.offsetWidth != width) {
                        ++loadedFonts;
                        node.parentNode.removeChild(node);
                        node = null;
                    }

                    if(loadedFonts >= fonts.length) {
                        if(interval) {
                            clearInterval(interval);
                        }
                        if(loadedFonts == fonts.length) {
                            callback();
                            return true;
                        }
                    }
                };

                if(!checkFont()) {
                    interval = setInterval(checkFont, 50);
                }
            })(fonts[i]);
        }
    }
    window.waitForWebfonts = waitForWebfonts;
})();


