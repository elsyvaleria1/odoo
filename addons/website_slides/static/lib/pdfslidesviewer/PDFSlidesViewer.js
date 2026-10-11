globalThis.PDFSlidesViewer = (function(){
    function PDFSlidesViewer(pdf_url, $canvas) {
        this.pdf = null;
        this.pdf_url = pdf_url;
        this.pdf_page_total = 0;
        this.pdf_page_current = 1;
        this.pdf_zoom = 1;
        this.pageRendering = false;
        this.pageNumPending = null;
        this.canvas = $canvas;
        this.canvas_context = $canvas.getContext('2d');
    }

    /**
     * Load the PDF document
     * @param pdfjsLib : the namespace of the "pdfjs-dist" ES module, as import() returned it
     */
    PDFSlidesViewer.prototype.loadDocument = async function(pdfjsLib) {
        const file_content = await pdfjsLib.getDocument({ url: this.pdf_url }).promise;
        this.pdf = file_content;
        this.pdf_page_total = file_content.numPages;
        return file_content;
    };

    /**
     * Get page info from document, resize canvas accordingly, and render page.
     * @param page_number : Page number.
     */
    PDFSlidesViewer.prototype.renderPage = function(page_number) {
        var self = this;
        this.pageRendering = true;
        return this.pdf.getPage(page_number).then(function(page) {
            var scale = self.getScaleToFit(page) * self.pdf_zoom;
            var viewport = page.getViewport({ scale: scale });
            self.canvas.height = viewport.height;
            self.canvas.width = viewport.width;
            var renderContext = {
                canvasContext: self.canvas_context,
                viewport: viewport
            };
            var renderTask = page.render(renderContext);
            return renderTask.promise.then(function () {
                self.pageRendering = false;
                if (self.pdf_zoom === 1 && scale > self.getScaleToFit(page)) {
                    return self.renderPage(page_number);
                }
                if (self.pageNumPending !== null) {
                    self.renderPage(self.pageNumPending);
                    self.pageNumPending = null;
                }
                self.pdf_page_current = page_number;
                return page_number;
            });
        });
    };

    PDFSlidesViewer.prototype.queueRenderPage = function(num) {
        if(this.pageRendering) {
            this.pageNumPending = num;
            return Promise.resolve(num);
        } else {
            return this.renderPage(num);
        }
    }

    PDFSlidesViewer.prototype.previousPage = function() {
        if (this.pdf_page_current <= 1) {
          return Promise.resolve(false);
        }
        this.pdf_page_current--;
        return this.queueRenderPage(this.pdf_page_current);
    };

    PDFSlidesViewer.prototype.nextPage = function() {
        if (this.pdf_page_current >= this.pdf_page_total) {
            return Promise.resolve(false);
        }
        this.pdf_page_current++;
        return this.queueRenderPage(this.pdf_page_current);
    };

    PDFSlidesViewer.prototype.getScaleToFit = function(page) {
        var maxWidth = this.canvas.parentNode.clientWidth;
        var maxHeight = this.canvas.parentNode.clientHeight;
        var hScale = maxWidth / page.view[2];
        var vScale = maxHeight / page.view[3];
        return Math.min(hScale, vScale);
    };

    PDFSlidesViewer.prototype.changePage = function(num){
        if(num >= 1 && num <= this.pdf_page_total){
            this.pdf_page_current = num;
            return this.queueRenderPage(num);
        }
        return Promise.resolve(false);
    }

    PDFSlidesViewer.prototype.firstPage = function(){
        this.pdf_page_current = 1;
        return this.queueRenderPage(1);
    }

    PDFSlidesViewer.prototype.lastPage = function(){
        this.pdf_page_current = this.pdf_page_total;
        return this.queueRenderPage(this.pdf_page_total);
    }

    PDFSlidesViewer.prototype.toggleFullScreenFooter = function(){
        if(document.fullscreenElement || document.mozFullScreenElement || document.webkitFullscreenElement || document.msFullscreenElement) {
            var footer = document.querySelector('div#PDFViewer div.oe_slides_panel_footer');
            var navBarFooter = footer?.parentElement;
            if (navBarFooter) {
                navBarFooter.classList.toggle('oe_show_footer');
                navBarFooter.style.display = navBarFooter.style.display === 'none' ? '' : 'none';
            }
        }
    }

    PDFSlidesViewer.prototype.toggleFullScreen = function(){
        var el = this.canvas.parentNode.parentNode;

        var isFullscreenAvailable = document.fullscreenEnabled || document.mozFullScreenEnabled || document.webkitFullscreenEnabled || document.msFullscreenEnabled || false;
        if(isFullscreenAvailable){
            var fullscreenElement = document.fullscreenElement || document.mozFullScreenElement || document.webkitFullscreenElement || document.msFullscreenElement;

            if (fullscreenElement) {
                if (document.exitFullscreen) {
                    document.exitFullscreen();
                } else if (document.mozCancelFullScreen) {
                    document.mozCancelFullScreen();
                } else if (document.webkitExitFullscreen) {
                    document.webkitExitFullscreen();
                } else if (document.webkitCancelFullScreen) {
                    document.webkitCancelFullScreen();
                } else if (document.msExitFullscreen) {
                    document.msExitFullscreen();
                }
            }else {
                if (el.requestFullscreen) {
                    el.requestFullscreen();
                } else if (el.mozRequestFullScreen) {
                    el.mozRequestFullScreen();
                } else if (el.msRequestFullscreen) {
                    el.msRequestFullscreen();
                } else if (el.webkitRequestFullscreen) {
                    if (navigator.userAgent.indexOf('Safari') != -1 && navigator.userAgent.indexOf('Chrome') == -1) {
                        el.webkitRequestFullscreen();
                    } else {
                        el.webkitRequestFullscreen(Element.ALLOW_KEYBOARD_INPUT);
                    }
                } else if (el.webkitRequestFullScreen) {
                    if (navigator.userAgent.indexOf('Safari') != -1 && navigator.userAgent.indexOf('Chrome') == -1) {
                        el.webkitRequestFullScreen();
                    } else {
                        el.webkitRequestFullScreen(Element.ALLOW_KEYBOARD_INPUT);
                    }
                }
            }
        }else{
            console.error("ERROR : full screen not supported by web browser");
        }
    }
    return PDFSlidesViewer;
})();
