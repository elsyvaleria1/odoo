# Run by odoo.libs.pdf_raster as `python -I _child.py WIDTH HEIGHT CPU MEMORY`,
# the PDF on stdin, a PNG on stdout. Exit 2: no page to show; 3: no MuPDF.
import resource
import sys


def main() -> int:
    width, height, cpu_seconds, memory_bytes = map(int, sys.argv[1:5])
    try:
        import pymupdf
    except ImportError:
        return 3
    # capped once the library is in, before a byte of the file is read: a
    # limit then fails this PDF, never reads as a missing renderer
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    content = sys.stdin.buffer.read()
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        if pdf.needs_pass or not pdf.page_count:
            return 2
        page = pdf[0]
        zoom = min(width / page.rect.width, height / page.rect.height)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        sys.stdout.buffer.write(pixmap.tobytes("png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
