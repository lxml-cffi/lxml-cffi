# support for Schematron validation
from . import config
from .etree import _Validator, _LIBXML_VERSION_INT
from .apihelpers import _documentOrRaise, _rootNodeOrRaise
from .parser import _copyDocRoot
from .etree import LxmlError
from .xmlerror import _receiveError
from .proxy import _fakeRootDoc, _destroyFakeDoc
from ._libxml2 import ffi, lib
schematron = tree = lib

class SchematronError(LxmlError):
    u"""Base class of all Schematron errors.
    """
    pass

class SchematronParseError(SchematronError):
    u"""Error while parsing an XML document as Schematron schema.
    """
    pass

class SchematronValidateError(SchematronError):
    u"""Error while validating an XML document with a Schematron schema.
    """
    pass

################################################################################
# Schematron

class Schematron(_Validator):
    u"""Schematron(self, etree=None, file=None)
    A Schematron validator.

    Pass a root Element or an ElementTree to turn it into a validator.
    Alternatively, pass a filename as keyword argument 'file' to parse from
    the file system.

    Schematron is a less well known, but very powerful schema language.  The main
    idea is to use the capabilities of XPath to put restrictions on the structure
    and the content of XML documents.  Here is a simple example::

      >>> schematron = Schematron(XML('''
      ... <schema xmlns="http://www.ascc.net/xml/schematron" >
      ...   <pattern name="id is the only permited attribute name">
      ...     <rule context="*">
      ...       <report test="@*[not(name()='id')]">Attribute
      ...         <name path="@*[not(name()='id')]"/> is forbidden<name/>
      ...       </report>
      ...     </rule>
      ...   </pattern>
      ... </schema>
      ... '''))

      >>> xml = XML('''
      ... <AAA name="aaa">
      ...   <BBB id="bbb"/>
      ...   <CCC color="ccc"/>
      ... </AAA>
      ... ''')

      >>> schematron.validate(xml)
      0

      >>> xml = XML('''
      ... <AAA id="aaa">
      ...   <BBB id="bbb"/>
      ...   <CCC/>
      ... </AAA>
      ... ''')

      >>> schematron.validate(xml)
      1

    Schematron was added to libxml2 in version 2.6.21.  Before version 2.6.32,
    however, Schematron lacked support for error reporting other than to stderr.
    This version is therefore required to retrieve validation warnings and
    errors in lxml.
    """
    def __init__(self, etree=None, file=None):
        self._c_schema = ffi.NULL
        self._c_schema_doc = ffi.NULL
        _Validator.__init__(self)
        if not config.ENABLE_SCHEMATRON:
            raise SchematronError, \
                u"lxml.etree was compiled without Schematron support."
        if etree is not None:
            doc = _documentOrRaise(etree)
            root_node = _rootNodeOrRaise(etree)
            self._c_schema_doc = _copyDocRoot(doc._c_doc, root_node._c_node)
            parser_ctxt = schematron.xmlSchematronNewDocParserCtxt(self._c_schema_doc)
        elif file is not None:
            filename = _getFilenameForFile(file)
            if filename is None:
                # XXX assume a string object
                filename = file
            filename = _encodeFilename(filename)
            with self._error_log:
                parser_ctxt = schematron.xmlSchematronNewParserCtxt(_cstr(filename))
        else:
            raise SchematronParseError, u"No tree or file given"

        if not parser_ctxt:
            if self._c_schema_doc:
                tree.xmlFreeDoc(self._c_schema_doc)
                self._c_schema_doc = ffi.NULL
            raise MemoryError()

        try:
            with self._error_log:
                self._c_schema = schematron.xmlSchematronParse(parser_ctxt)
        finally:
            schematron.xmlSchematronFreeParserCtxt(parser_ctxt)

        if not self._c_schema:
            raise SchematronParseError(
                u"Document is not a valid Schematron schema",
                self._error_log)

    def __del__(self):
        schematron.xmlSchematronFree(self._c_schema)
        if self._c_schema_doc:
            tree.xmlFreeDoc(self._c_schema_doc)

    def __call__(self, etree):
        u"""__call__(self, etree)

        Validate doc using Schematron.

        Returns true if document is valid, false if not."""
        assert self._c_schema, "Schematron instance not initialised"
        doc = _documentOrRaise(etree)
        root_node = _rootNodeOrRaise(etree)

        valid_ctxt = schematron.xmlSchematronNewValidCtxt(
            self._c_schema, schematron.XML_SCHEMATRON_OUT_ERROR)
        if not valid_ctxt:
            raise MemoryError()

        try:
            self._error_log.clear()
            schematron.xmlSchematronSetValidStructuredErrors(
                valid_ctxt, _receiveError, self._error_log.get_handle())
            c_doc = _fakeRootDoc(doc._c_doc, root_node._c_node)
            if 1:
                ret = schematron.xmlSchematronValidateDoc(valid_ctxt, c_doc)
            _destroyFakeDoc(doc._c_doc, c_doc)
        finally:
            schematron.xmlSchematronFreeValidCtxt(valid_ctxt)

        if ret == -1:
            raise SchematronValidateError(
                u"Internal error in Schematron validation",
                self._error_log)
        if ret == 0:
            return True
        else:
            return False
