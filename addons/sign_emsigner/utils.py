import lzma


def compress_pdf_base64(pdf_data):
    return lzma.compress(pdf_data, format=lzma.FORMAT_ALONE)
