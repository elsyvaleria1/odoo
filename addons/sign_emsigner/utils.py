import lzma


def compress_pdf_base64(pdf_data):
    """Compress the PDF data using LZMA and encode it to base64

    :param pdf_data: PDF file data to compress
    :return: Compressed bytes data
    """
    # Compress using LZMA
    return lzma.compress(pdf_data, format=lzma.FORMAT_ALONE)
