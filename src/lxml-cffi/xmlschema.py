#  support for XMLSchema validation
from .etree import LxmlError, _Validator, _LIBXML_VERSION_INT
from .apihelpers import _documentOrRaise, _rootNodeOrRaise, _isString
from .apihelpers import _encodeFilename
from .xmlerror import _receiveError
from .proxy import _fakeRootDoc, _destroyFakeDoc
from .parser import _GLOBAL_PARSER_CONTEXT, _parseDocument
from .xpath import XPath
from ._libxml2 import ffi, lib
xmlschema = tree = xmlerror = xmlparser = lib

class XMLSchemaError(LxmlError):
    u"""Base class of all XML Schema errors
    """
    pass

class XMLSchemaParseError(XMLSchemaError):
    u"""Error while parsing an XML document as XML Schema.
    """
    pass

class XMLSchemaValidateError(XMLSchemaError):
    u"""Error while validating an XML document with an XML Schema.
    """
    pass

################################################################################
# XMLSchema

_check_for_default_attributes = XPath(
    u"boolean(//xs:attribute[@default or @fixed][1])",
    namespaces={u'xs': u'http://www.w3.org/2001/XMLSchema'})

class XMLSchema(_Validator):
    u"""XMLSchema(self, etree=None, file=None)
    Turn a document into an XML Schema validator.

    Either pass a schema as Element or ElementTree, or pass a file or
    filename through the ``file`` keyword argument.

    Passing the ``attribute_defaults`` boolean option will make the
    schema insert default/fixed attributes into validated documents.
    """
    _c_schema = ffi.NULL
    _has_default_attributes = True # play safe
    _add_attribute_defaults = False

    def __init__(self, etree=None, file=None, attribute_defaults=False):
        self._add_attribute_defaults = attribute_defaults
        _Validator.__init__(self)
        fake_c_doc = ffi.NULL
        if etree is not None:
            doc = _documentOrRaise(etree)
            root_node = _rootNodeOrRaise(etree)

            # work around for libxml2 bug if document is not XML schema at all
            if _LIBXML_VERSION_INT < 20624:
                c_node = root_node._c_node
                c_href = _getNs(c_node)
                if c_href is NULL or \
                       tree.xmlStrcmp(
                           c_href, 'http://www.w3.org/2001/XMLSchema') != 0:
                    raise XMLSchemaParseError, u"Document is not XML Schema"

            fake_c_doc = _fakeRootDoc(doc._c_doc, root_node._c_node)
            parser_ctxt = xmlschema.xmlSchemaNewDocParserCtxt(fake_c_doc)
        elif file is not None:
            if _isString(file):
                doc = None
                filename = _encodeFilename(file)
                parser_ctxt = xmlschema.xmlSchemaNewParserCtxt(filename)
            else:
                doc = _parseDocument(file, None, None)
                parser_ctxt = xmlschema.xmlSchemaNewDocParserCtxt(doc._c_doc)
        else:
            raise XMLSchemaParseError, u"No tree or file given"

        if parser_ctxt:
            xmlschema.xmlSchemaSetParserStructuredErrors(
                parser_ctxt, _receiveError, self._error_log.get_handle())
            if doc is None:
                if 1:
                    self._c_schema = xmlschema.xmlSchemaParse(parser_ctxt)
            else:
                # calling xmlSchemaParse on a schema with imports or
                # includes will cause libxml2 to create an internal
                # context for parsing, so push an implied context to route
                # resolve requests to the document's parser
                _GLOBAL_PARSER_CONTEXT.pushImpliedContextFromParser(doc._parser)
                self._c_schema = xmlschema.xmlSchemaParse(parser_ctxt)
                _GLOBAL_PARSER_CONTEXT.popImpliedContext()

            if _LIBXML_VERSION_INT >= 20624:
                xmlschema.xmlSchemaFreeParserCtxt(parser_ctxt)

        if fake_c_doc:
            _destroyFakeDoc(doc._c_doc, fake_c_doc)

        if not self._c_schema:
            raise XMLSchemaParseError(
                self._error_log._buildExceptionMessage(
                    u"Document is not valid XML Schema"),
                self._error_log)

        if doc is not None:
            self._has_default_attributes = _check_for_default_attributes(doc)
        self._add_attribute_defaults = attribute_defaults and \
                                       self._has_default_attributes

    def __del__(self):
        xmlschema.xmlSchemaFree(self._c_schema)

    def __call__(self, etree):
        u"""__call__(self, etree)

        Validate doc using XML Schema.

        Returns true if document is valid, false if not.
        """
        assert self._c_schema, "Schema instance not initialised"
        doc = _documentOrRaise(etree)
        root_node = _rootNodeOrRaise(etree)

        valid_ctxt = xmlschema.xmlSchemaNewValidCtxt(self._c_schema)
        if not valid_ctxt:
            raise MemoryError()

        try:
            if self._add_attribute_defaults:
                xmlschema.xmlSchemaSetValidOptions(
                    valid_ctxt, xmlschema.XML_SCHEMA_VAL_VC_I_CREATE)

            self._error_log.clear()
            xmlschema.xmlSchemaSetValidStructuredErrors(
                valid_ctxt, _receiveError, self._error_log.get_handle())

            c_doc = _fakeRootDoc(doc._c_doc, root_node._c_node)
            if 1:
                ret = xmlschema.xmlSchemaValidateDoc(valid_ctxt, c_doc)
            _destroyFakeDoc(doc._c_doc, c_doc)
        finally:
            xmlschema.xmlSchemaFreeValidCtxt(valid_ctxt)

        if ret == -1:
            raise XMLSchemaValidateError(
                u"Internal error in XML Schema validation.",
                self._error_log)
        if ret == 0:
            return True
        else:
            return False

    def _newSaxValidator(self, add_default_attributes):
        context = _ParserSchemaValidationContext.__new__(_ParserSchemaValidationContext)
        context._schema = self
        context._add_default_attributes = (self._has_default_attributes and (
            add_default_attributes or self._add_attribute_defaults))
        return context

class _ParserSchemaValidationContext(object):
    _valid_ctxt = ffi.NULL
    _sax_plug = ffi.NULL
    _add_default_attributes = False

    def __del__(self):
        self.disconnect()
        if self._valid_ctxt:
            xmlschema.xmlSchemaFreeValidCtxt(self._valid_ctxt)

    def copy(self):
        assert self._schema is not None, "_ParserSchemaValidationContext not initialised"
        return self._schema._newSaxValidator(
            self._add_default_attributes)

    def inject_default_attributes(self, c_doc):
        # we currently need to insert default attributes manually
        # after parsing, as libxml2 does not support this at parse
        # time
        if self._add_default_attributes:
            if 1:
                xmlschema.xmlSchemaValidateDoc(self._valid_ctxt, c_doc)

    def connect(self, c_ctxt, error_log):
        if not self._valid_ctxt:
            self._valid_ctxt = xmlschema.xmlSchemaNewValidCtxt(
                self._schema._c_schema)
            if not self._valid_ctxt:
                raise MemoryError()
            if self._add_default_attributes:
                xmlschema.xmlSchemaSetValidOptions(
                    self._valid_ctxt, xmlschema.XML_SCHEMA_VAL_VC_I_CREATE)
        if error_log is not None:
            xmlschema.xmlSchemaSetValidStructuredErrors(
                self._valid_ctxt, _receiveError, error_log.get_handle())
        sax_ptr = ffi.addressof(c_ctxt, "sax")
        usr_ptr = ffi.addressof(c_ctxt, "userData")
        self._sax_plug = xmlschema.xmlSchemaSAXPlug(
            self._valid_ctxt, sax_ptr, usr_ptr)

    def disconnect(self):
        if self._sax_plug:
            xmlschema.xmlSchemaSAXUnplug(self._sax_plug)
            self._sax_plug = ffi.NULL
        if self._valid_ctxt:
            xmlschema.xmlSchemaSetValidStructuredErrors(
                self._valid_ctxt, ffi.NULL, ffi.NULL)

    def isvalid(self):
        if not self._valid_ctxt:
            return True
        return xmlschema.xmlSchemaIsValid(self._valid_ctxt)
