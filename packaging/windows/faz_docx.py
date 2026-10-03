# SPDX-License-Identifier: GPL-3.0-or-later
"""Um .docx mínimo para o aceite do pacote (F3): `python faz_docx.py saida.docx texto`."""
import sys, zipfile

TIPOS = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Override PartName="/word/document.xml" ContentType="application/'
         'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
DOC = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
       '<w:body><w:p><w:r><w:t>{}</w:t></w:r></w:p></w:body></w:document>')

with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("[Content_Types].xml", TIPOS)
    z.writestr("word/document.xml", DOC.format(sys.argv[2]))
