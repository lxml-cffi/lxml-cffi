# support for RelaxNG validation

from .etree import _Validator, _LIBXML_VERSION_INT, LxmlError
from .apihelpers import _documentOrRaise, _rootNodeOrRaise, _isString
from .proxy import _fakeRootDoc, _destroyFakeDoc
from .xmlerror import _receiveError
from .parser import _parseDocument
from ._libxml2 import ffi, lib as relaxng

class RelaxNGError(LxmlError):
    u"""Base class for RelaxNG errors.
    """
    pass

class RelaxNGParseError(RelaxNGError):
    u"""Error while parsing an XML document as RelaxNG.
    """
    pass

class RelaxNGValidateError(RelaxNGError):
    u"""Error while validating an XML document with a RelaxNG schema.
    """
    pass

################################################################################
# RelaxNG

class RelaxNG(_Validator):
    u"""RelaxNG(self, etree=None, file=None)
    Turn a document into a Relax NG validator.

    Either pass a schema as Element or ElementTree, or pass a file or
    filename through the ``file`` keyword argument.
    """
    def __init__(self, etree=None, file=None):
        self._c_schema = ffi.NULL
        _Validator.__init__(self)
        fake_c_doc = ffi.NULL
        if etree is not None:
            doc = _documentOrRaise(etree)
            root_node = _rootNodeOrRaise(etree)
            c_node = root_node._c_node
            fake_c_doc = _fakeRootDoc(doc._c_doc, root_node._c_node)
            parser_ctxt = relaxng.xmlRelaxNGNewDocParserCtxt(fake_c_doc)
        elif file is not None:
            if _isString(file):
                doc = None
                filename = _encodeFilename(file)
                with self._error_log:
                    parser_ctxt = relaxng.xmlRelaxNGNewParserCtxt(_cstr(filename))
            else:
                doc = _parseDocument(file, None, None)
                parser_ctxt = relaxng.xmlRelaxNGNewDocParserCtxt(doc._c_doc)
        else:
            raise RelaxNGParseError, u"No tree or file given"

        if not parser_ctxt:
            if fake_c_doc:
                _destroyFakeDoc(doc._c_doc, fake_c_doc)
            raise RelaxNGParseError(
                self._error_log._buildExceptionMessage(
                    u"Document is not parsable as Relax NG"),
                self._error_log)

        relaxng.xmlRelaxNGSetParserStructuredErrors(
            parser_ctxt, _receiveError, self._error_log.get_handle())
        self._c_schema = relaxng.xmlRelaxNGParse(parser_ctxt)

        relaxng.xmlRelaxNGFreeParserCtxt(parser_ctxt)
        if not self._c_schema:
            if fake_c_doc:
                _destroyFakeDoc(doc._c_doc, fake_c_doc)
            raise RelaxNGParseError(
                self._error_log._buildExceptionMessage(
                    u"Document is not valid Relax NG"),
                self._error_log)
        if fake_c_doc:
            _destroyFakeDoc(doc._c_doc, fake_c_doc)

    def __del__(self):
        relaxng.xmlRelaxNGFree(self._c_schema)

    def __call__(self, etree):
        u"""__call__(self, etree)

        Validate doc using Relax NG.

        Returns true if document is valid, false if not."""
        assert self._c_schema, "RelaxNG instance not initialised"
        doc = _documentOrRaise(etree)
        root_node = _rootNodeOrRaise(etree)

        valid_ctxt = relaxng.xmlRelaxNGNewValidCtxt(self._c_schema)
        if not valid_ctxt:
            raise MemoryError()

        try:
            self._error_log.clear()
            relaxng.xmlRelaxNGSetValidStructuredErrors(
                valid_ctxt, _receiveError, self._error_log.get_handle())
            c_doc = _fakeRootDoc(doc._c_doc, root_node._c_node)
            if 1:
                ret = relaxng.xmlRelaxNGValidateDoc(valid_ctxt, c_doc)
            _destroyFakeDoc(doc._c_doc, c_doc)
        finally:
            relaxng.xmlRelaxNGFreeValidCtxt(valid_ctxt)

        if ret == -1:
            raise RelaxNGValidateError(
                u"Internal error in Relax NG validation",
                self._error_log)
        if ret == 0:
            return True
        else:
            return False
