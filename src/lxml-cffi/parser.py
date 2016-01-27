import threading

from .includes.etree_defs import _isString, FOR_EACH_ELEMENT_FROM
from .apihelpers import (
    _getFilenameForFile, _encodeFilenameUTF8, _copyTail, _utf8, funicode,
    _encodeFilename, _decodeFilename, _decodeFilenameWithLength)
from .apihelpers import _makeElement, _hasEncodingDeclaration
from . import python, limits, config
from ._libxml2 import ffi, lib
from .docloader import (
    _ResolverRegistry, _ResolverContext, _initResolverContext,
    PARSER_DATA_STRING, PARSER_DATA_FILENAME, PARSER_DATA_FILE)
from .xmlerror import _ErrorLog, ErrorTypes
from .etree import LxmlSyntaxError, LxmlError, _documentFactory
from .etree import _LIBXML_VERSION_INT
import io

xmlparser = htmlparser = xmlerror = tree = lib


HTMLParser = None # XXX HACK

class ParseError(LxmlSyntaxError):
    u"""Syntax error while parsing an XML document.

    For compatibility with ElementTree 1.3 and later.
    """
    def __init__(self, message, code, line, column):
        super(_ParseError, self).__init__(message)
        self.position = (line, column)
        self.code = code

_ParseError = ParseError


class XMLSyntaxError(ParseError):
    u"""Syntax error while parsing an XML document.
    """


class ParserError(LxmlError):
    u"""Internal lxml parser error.
    """


class _ParserDictionaryContext(object):
    # Global parser context to share the string dictionary.
    #
    # This class is a delegate singleton!
    #
    # It creates _ParserDictionaryContext objects for each thread to
    # keep thread state, but those must never be used directly.
    # Always stick to using the static _GLOBAL_PARSER_CONTEXT as
    # defined below the class.
    #

    _default_parser = None

    def __init__(self):
        self._c_dict = None
        self._implied_parser_contexts = []
        self.threadlocal = threading.local()

    def __del__(self):
        if self._c_dict:
            xmlparser.xmlDictFree(self._c_dict)

    def initMainParserContext(self):
        u"""Put the global context into the thread dictionary of the main
        thread.  To be called once and only in the main thread."""
        self.threadlocal.context = self

    def _findThreadParserContext(self):
        u"Find (or create) the _ParserDictionaryContext object for the current thread"
        if hasattr(self.threadlocal, 'context'):
            return self.threadlocal.context
        context = _ParserDictionaryContext()
        self.threadlocal.context = context
        return context

    def setDefaultParser(self, parser):
        u"Set the default parser for the current thread"
        context = self._findThreadParserContext()
        context._default_parser = parser

    def getDefaultParser(self):
        u"Return (or create) the default parser of the current thread"
        context = self._findThreadParserContext()
        if context._default_parser is None:
            if self._default_parser is None:
                self._default_parser = _DEFAULT_XML_PARSER._copy()
            if context is not self:
                context._default_parser = self._default_parser._copy()
        return context._default_parser

    def _getThreadDict(self, default):
        u"Return the thread-local dict or create a new one if necessary."
        context = self._findThreadParserContext()
        if not context._c_dict:
            # thread dict not yet set up => use default or create a new one
            if default:
                context._c_dict = default
                xmlparser.xmlDictReference(default)
                return default
            if not self._c_dict:
                self._c_dict = xmlparser.xmlDictCreate()
            if context is not self:
                context._c_dict = xmlparser.xmlDictCreateSub(self._c_dict)
        return context._c_dict

    def initThreadDictRef(self, c_dict):
        c_thread_dict = self._getThreadDict(c_dict)
        if c_dict == c_thread_dict:
            return c_dict
        if c_dict:
            xmlparser.xmlDictFree(c_dict)
        xmlparser.xmlDictReference(c_thread_dict)
        return c_thread_dict

    def initParserDict(self, pctxt):
        u"Assure we always use the same string dictionary."
        pctxt.dict = self.initThreadDictRef(pctxt.dict)
        pctxt.dictNames = True

    def initXPathParserDict(self, pctxt):
        u"Assure we always use the same string dictionary."
        pctxt.dict = self.initThreadDictRef(pctxt.dict)

    def initDocDict(self, result):
        u"Store dict of last object parsed if no shared dict yet"
        # XXX We also free the result dict here if there already was one.
        # This case should only occur for new documents with empty dicts,
        # otherwise we'd free data that's in use => segfault
        result.dict = self.initThreadDictRef(result.dict)

    def findImpliedContext(self):
        u"""Return any current implied xml parser context for the current
        thread.  This is used when the resolver functions are called
        with an xmlParserCtxt that was generated from within libxml2
        (i.e. without a _ParserContext) - which happens when parsing
        schema and xinclude external references."""

        # see if we have a current implied parser
        context = self._findThreadParserContext()
        if context._implied_parser_contexts:
            implied_context = context._implied_parser_contexts[-1]
            return implied_context
        return None

    def pushImpliedContextFromParser(self, parser):
        u"Push a new implied context object taken from the parser."
        if parser is not None:
            self.pushImpliedContext(parser._getParserContext())
        else:
            self.pushImpliedContext(None)

    def pushImpliedContext(self, parser_context):
        u"Push a new implied context object."
        context = self._findThreadParserContext()
        context._implied_parser_contexts.append(parser_context)

    def popImpliedContext(self):
        u"Pop the current implied context object."
        context = self._findThreadParserContext()
        context._implied_parser_contexts.pop()

_GLOBAL_PARSER_CONTEXT = _ParserDictionaryContext()
_GLOBAL_PARSER_CONTEXT.initMainParserContext()

############################################################
## support for Python unicode I/O
############################################################

# name of Python unicode encoding as known to libxml2
_UNICODE_ENCODING = None

def _setupPythonUnicode():
    u"""Sets _UNICODE_ENCODING to the internal encoding name of Python unicode
    strings if libxml2 supports reading native Python unicode.  This depends
    on iconv and the local Python installation, so we simply check if we find
    a matching encoding handler.
    """
    buf = ffi.new("wchar_t[]", u"<test/>")
    buf4 = ffi.buffer(buf, 4)[0:4]
    # apparently, libxml2 can't detect UTF-16 on some systems
    if buf4 == b'<\0t\0':
        enc = "UTF-16LE"
    elif buf4 == b'\0<\0t':
        enc = "UTF-16BE"
    else:
        # let libxml2 give it a try
        enc = _findEncodingName(ffi.cast("const xmlChar*", buf),
                                ffi.sizeof(buf))
        if not enc:
            # not my fault, it's YOUR broken system :)
            return
    enchandler = tree.xmlFindCharEncodingHandler(enc)
    if enchandler:
        global _UNICODE_ENCODING
        tree.xmlCharEncCloseFunc(enchandler)
        _UNICODE_ENCODING = enc

def _findEncodingName(buf, length):
    u"Work around bug in libxml2: find iconv name of encoding on our own."
    enc = tree.xmlDetectCharEncoding(buf, length)
    if enc == tree.XML_CHAR_ENCODING_UTF16LE:
        return "UTF-16LE"
    elif enc == tree.XML_CHAR_ENCODING_UTF16BE:
        return "UTF-16BE"
    elif enc == tree.XML_CHAR_ENCODING_UCS4LE:
        return "UCS-4LE"
    elif enc == tree.XML_CHAR_ENCODING_UCS4BE:
        return "UCS-4BE"
    elif enc == tree.XML_CHAR_ENCODING_NONE:
        return ffi.NULL
    else:
        # returns a constant char*, no need to free it
        return tree.xmlGetCharEncodingName(enc)

_setupPythonUnicode()

############################################################
## support for file-like objects
############################################################

class _FileReaderContext(object):
    def __init__(self, filelike, exc_context, url, encoding=None, close_file=False):
        self._exc_context = exc_context
        self._filelike = filelike
        self._close_file_after_read = close_file
        self._encoding = encoding
        if url is None:
            self._c_url = ffi.NULL
        else:
            url = _encodeFilename(url)
            self._c_url = url
        self._url = url
        self._bytes  = b''
        self._bytes_read = 0
        self._handle = ffi.new_handle(self)

    def _close_file(self):
        if self._filelike is None or not self._close_file_after_read:
            return
        try:
            close = self._filelike.close
        except AttributeError:
            close = None
        finally:
            self._filelike = None
        if close is not None:
            close()

    def _createParserInputBuffer(self):
        c_buffer = xmlparser.xmlAllocParserInputBuffer(0)
        c_buffer.readcallback  = _readFilelikeParser
        c_buffer.context = self._handle
        return c_buffer

    def _createParserInput(self, ctxt):
        c_buffer = self._createParserInputBuffer()
        return xmlparser.xmlNewIOInputStream(ctxt, c_buffer, 0)

    def _readDtd(self):
        c_buffer = self._createParserInputBuffer()
        if 1:
            return xmlparser.xmlIOParseDTD(ffi.NULL, c_buffer, 0)

    def _readDoc(self, ctxt, options):
        if self._encoding is None:
            c_encoding = ffi.NULL
        else:
            c_encoding = self._encoding

        c_read_callback  = _readFilelikeParser

        orig_options = ctxt.options
        if 1:
            if ctxt.html:
                result = htmlparser.htmlCtxtReadIO(
                        ctxt, c_read_callback, ffi.NULL, self._handle,
                        self._c_url, c_encoding, options)
                if result:
                    if _fixHtmlDictNames(ctxt.dict, result) < 0:
                        tree.xmlFreeDoc(result)
                        result = ffi.NULL
            else:
                result = xmlparser.xmlCtxtReadIO(
                    ctxt, c_read_callback, ffi.NULL, self._handle,
                    self._c_url, c_encoding, options)
        ctxt.options = orig_options # work around libxml2 problem
        try:
            self._close_file()
        except:
            self._exc_context._store_raised()
        finally:
            return result  # swallow any exception

    def copyToBuffer(self, c_buffer, c_requested):
        if self._bytes_read < 0:
            return 0
        try:
            c_byte_count = 0
            byte_count = python.PyBytes_GET_SIZE(self._bytes)
            remaining  = byte_count - self._bytes_read
            while c_requested > remaining:
                ffi.buffer(c_buffer, remaining)[:] = self._bytes[self._bytes_read:self._bytes_read + remaining]
                c_byte_count += remaining
                c_buffer += remaining
                c_requested -= remaining

                self._bytes = self._filelike.read(c_requested)
                if not isinstance(self._bytes, bytes):
                    if isinstance(self._bytes, unicode):
                        if self._encoding is None:
                            self._bytes = self._bytes.encode('utf8')
                        else:
                            self._bytes = python.PyUnicode_AsEncodedString(
                                self._bytes, _cstr(self._encoding), NULL)
                    else:
                        self._close_file()
                        raise TypeError, \
                            u"reading from file-like objects must return byte strings or unicode strings"

                remaining = python.PyBytes_GET_SIZE(self._bytes)
                if remaining == 0:
                    self._bytes_read = -1
                    self._close_file()
                    return c_byte_count
                self._bytes_read = 0

            if c_requested > 0:
                ffi.buffer(c_buffer, c_requested)[:] = self._bytes[self._bytes_read:self._bytes_read + c_requested]
                c_byte_count += c_requested
                self._bytes_read += c_requested
        except:
            c_byte_count = -1
            self._exc_context._store_raised()
            try:
                self._close_file()
            except:
                self._exc_context._store_raised()
        finally:
            return c_byte_count  # swallow any exceptions

@ffi.callback("xmlInputReadCallback")
def _readFilelikeParser(ctxt, c_buffer, c_size):
    context = ffi.from_handle(ctxt)
    return context.copyToBuffer(c_buffer, c_size)

############################################################
## support for custom document loaders
############################################################

@ffi.callback("xmlExternalEntityLoader")
def _local_resolver(c_url, c_pubid, c_context):
    # if there is no _ParserContext associated with the xmlParserCtxt
    # passed, check to see if the thread state object has an implied
    # context.
    if c_context._private:
        context = ffi.from_handle(c_context._private)
    else:
        context = _GLOBAL_PARSER_CONTEXT.findImpliedContext()

    if context is None:
        if not __DEFAULT_ENTITY_LOADER:
            return ffi.NULL
        return __DEFAULT_ENTITY_LOADER(c_url, c_pubid, c_context)

    try:
        if not c_url:
            url = None
        else:
            # parsing a related document (DTD etc.) => UTF-8 encoded URL?
            url = _decodeFilename(ffi.string(c_url))
        if not c_pubid:
            pubid = None
        else:
            pubid = funicode(c_pubid) # always UTF-8

        doc_ref = context._resolvers.resolve(url, pubid, context)
    except:
        context._store_raised()
        return ffi.NULL

    if doc_ref is not None:
        if doc_ref._type == PARSER_DATA_STRING:
            data = ffi.new("xmlChar[]", doc_ref._data_bytes)
            c_input = xmlparser.xmlNewInputStream(c_context)
            if c_input:
                c_input.base = data
                c_input.length = len(data)
                c_input.cur = c_input.base
                c_input.end = c_input.base + c_input.length
        elif doc_ref._type == PARSER_DATA_FILENAME:
            data = None
            c_input = xmlparser.xmlNewInputFromFile(
                c_context, doc_ref._filename)
        elif doc_ref._type == PARSER_DATA_FILE:
            file_context = _FileReaderContext(doc_ref._file, context, url,
                                              None, doc_ref._close_file)
            c_input = file_context._createParserInput(c_context)
            data = file_context
        else:
            data = None
            c_input = ffi.NULL

        if c_input:
            return c_input

    if not __DEFAULT_ENTITY_LOADER:
        return NULL
    return __DEFAULT_ENTITY_LOADER(c_url, c_pubid, c_context)

__DEFAULT_ENTITY_LOADER = xmlparser.xmlGetExternalEntityLoader()

xmlparser.xmlSetExternalEntityLoader(_local_resolver)

############################################################
## Parsers
############################################################

class _ParserContext(_ResolverContext):
    _validator = None
    _doc = None

    def __init__(self):
        self._c_ctxt = None
        self._collect_ids = True
        if not config.ENABLE_THREADING:
            self._lock = None
        else:
            self._lock = threading.Lock()
        self._error_log = _ErrorLog()

    def __del__(self):
        if self._c_ctxt is not None:
            xmlparser.xmlFreeParserCtxt(self._c_ctxt)

    def _initParserContext(self, c_ctxt):
        self._c_ctxt = c_ctxt
        handle = ffi.new_handle(self)
        c_ctxt._private = handle
        self._keepalive = handle

    def _resetParserContext(self):
        if self._c_ctxt:
            if self._c_ctxt.html:
                htmlparser.htmlCtxtReset(self._c_ctxt)
                self._c_ctxt.disableSAX = 0 # work around bug in libxml2
            else:
                xmlparser.xmlClearParserCtxt(self._c_ctxt)

    def prepare(self):
        if config.ENABLE_THREADING and self._lock:
            self._lock.acquire()
        self._error_log.clear()
        self._c_ctxt.sax.serror = _receiveParserError
        if self._validator is not None:
            self._validator.connect(self._c_ctxt, self._error_log)

    def cleanup(self):
        if self._validator is not None:
            self._validator.disconnect()
        self._resetParserContext()
        self.clear()
        self._c_ctxt.sax.serror = ffi.NULL
        if config.ENABLE_THREADING and self._lock:
            self._lock.release()

    def _handleParseResult(self, parser, result, filename):
        c_doc = self._handleParseResultDoc(parser, result, filename)
        if self._doc and self._doc._c_doc == c_doc:
            return self._doc
        else:
            return _documentFactory(c_doc, parser)

    def _handleParseResultDoc(self, parser, result, filename):
        recover = parser._parse_options & xmlparser.XML_PARSE_RECOVER
        return _handleParseResult(self, self._c_ctxt, result,
                                  filename, recover,
                                  free_doc=self._doc is None)

def _initParserContext(context, resolvers, c_ctxt):
    _initResolverContext(context, resolvers)
    if c_ctxt:
        context._initParserContext(c_ctxt)

def _forwardParserError(_parser_context, error):
    ffi.from_handle(_parser_context._private)._error_log._receive(error)

@ffi.callback("xmlStructuredErrorFunc")
def _receiveParserError(c_context, error):
    context = ffi.cast("xmlParserCtxtPtr", c_context)
    if not context or not context._private:
        _forwardError(NULL, error)
    else:
        _forwardParserError(context, error)

def _raiseParseError(ctxt, filename, error_log):
    if filename is not None and \
           ctxt.lastError.domain == xmlerror.XML_FROM_IO:
        if isinstance(filename, bytes):
            filename = _decodeFilenameWithLength(filename, len(filename))
        if ctxt.lastError.message:
            message = ffi.string(ctxt.lastError.message)
            try:
                message = message.decode('utf-8')
            except UnicodeDecodeError:
                # the filename may be in there => play it safe
                message = message.decode('iso8859-1')
            message = u"Error reading file '%s': %s" % (
                filename, message.strip())
        else:
            message = u"Error reading '%s'" % filename
        raise IOError, message
    elif error_log:
        raise error_log._buildParseException(
            XMLSyntaxError, u"Document is not well formed")
    elif ctxt.lastError.message:
        message = ffi.string(ctxt.lastError.message).strip()
        code = ctxt.lastError.code
        line = ctxt.lastError.line
        column = ctxt.lastError.int2
        if ctxt.lastError.line > 0:
            message = u"line %d: %s" % (line, message)
        raise XMLSyntaxError(message, code, line, column)
    else:
        raise XMLSyntaxError(None, xmlerror.XML_ERR_INTERNAL_ERROR, 0, 0)

def _handleParseResult(context, c_ctxt, result, filename, recover, free_doc):
    if result:
        _GLOBAL_PARSER_CONTEXT.initDocDict(result)

    if c_ctxt.myDoc:
        if c_ctxt.myDoc != result:
            _GLOBAL_PARSER_CONTEXT.initDocDict(c_ctxt.myDoc)
            tree.xmlFreeDoc(c_ctxt.myDoc)
        c_ctxt.myDoc = ffi.NULL

    if result:
        if (context._validator is not None and
                not context._validator.isvalid()):
            well_formed = 0  # actually not 'valid', but anyway ...
        elif (not c_ctxt.wellFormed and not c_ctxt.html and
                c_ctxt.charset == tree.XML_CHAR_ENCODING_8859_1 and
                [1 for error in context._error_log
                 if error.type == ErrorTypes.ERR_INVALID_CHAR]):
            # An encoding error occurred and libxml2 switched from UTF-8
            # input to (undecoded) Latin-1, at some arbitrary point in the
            # document.  Better raise an error than allowing for a broken
            # tree with mixed encodings.
            well_formed = 0
        elif recover or (c_ctxt.wellFormed and
                         c_ctxt.lastError.level < xmlerror.XML_ERR_ERROR):
            well_formed = 1
        elif not c_ctxt.replaceEntities and not c_ctxt.validate \
                 and context is not None:
            # in this mode, we ignore errors about undefined entities
            for error in context._error_log.filter_from_errors():
                if error.type != ErrorTypes.WAR_UNDECLARED_ENTITY and \
                       error.type != ErrorTypes.ERR_UNDECLARED_ENTITY:
                    well_formed = 0
                    break
            else:
                well_formed = 1
        else:
            well_formed = 0

        if not well_formed:
            if free_doc:
                tree.xmlFreeDoc(result)
            result = ffi.NULL

    if context is not None and context._has_raised():
        if result:
            if free_doc:
                tree.xmlFreeDoc(result)
            result = ffi.NULL
        context._raise_if_stored()

    if not result:
        if context:
            _raiseParseError(c_ctxt, filename, context._error_log)
        else:
            _raiseParseError(c_ctxt, filename, None)
    else:
        if not result.URL and filename is not None:
            result.URL = tree.xmlStrdup(filename)
        if not result.encoding:
            result.encoding = tree.xmlStrdup("UTF-8")

    if context._validator is not None and \
           context._validator._add_default_attributes:
        # we currently need to do this here as libxml2 does not
        # support inserting default attributes during parse-time
        # validation
        context._validator.inject_default_attributes(result)

    return result

def _fixHtmlDictNames(c_dict, c_doc):
    if not c_doc:
        return 0
    c_node = c_doc.children
    for c_node in FOR_EACH_ELEMENT_FROM(c_doc, c_node, 1):
        if c_node.type == tree.XML_ELEMENT_NODE:
            if _fixHtmlDictNodeNames(c_dict, c_node) < 0:
                return -1
    return 0

def _fixHtmlDictSubtreeNames(c_dict, c_doc, c_start_node):
    """
    Move names to the dict, iterating in document order, starting at
    c_start_node. This is used in incremental parsing after each chunk.
    """
    if not c_doc:
        return 0
    if not c_start_node:
        return _fixHtmlDictNames(c_dict, c_doc)
    c_node = c_start_node
    for c_node in FOR_EACH_ELEMENT_FROM(c_doc, c_node, 1):
        if c_node.type == tree.XML_ELEMENT_NODE:
            if _fixHtmlDictNodeNames(c_dict, c_node) < 0:
                return -1
    return 0

def _fixHtmlDictNodeNames(c_dict, c_node):
    c_name = tree.xmlDictLookup(c_dict, c_node.name, -1)
    if not c_name:
        return -1
    if c_name != c_node.name:
        tree.xmlFree(c_node.name)
        c_node.name = c_name
    c_attr = c_node.properties
    while c_attr:
        c_name = tree.xmlDictLookup(c_dict, c_attr.name, -1)
        if not c_name:
            return -1
        if c_name != c_attr.name:
            tree.xmlFree(c_attr.name)
            c_attr.name = c_name
        c_attr = c_attr.next
    return 0

class _BaseParser(object):
    _class_lookup = None
    _parser_context = None
    _push_parser_context = None
    _filename = None
    _events_to_collect = None

    def __init__(self, parse_options, for_html, schema,
                 remove_comments, remove_pis, strip_cdata, collect_ids,
                 target, encoding):
        if not isinstance(self, (XMLParser, HTMLParser)):
            raise TypeError, u"This class cannot be instantiated"

        self._parse_options = parse_options
        self.target = target
        self._for_html = for_html
        self._remove_comments = remove_comments
        self._remove_pis = remove_pis
        self._strip_cdata = strip_cdata
        self._collect_ids = collect_ids
        self._schema = schema

        self._resolvers = _ResolverRegistry()

        if encoding is None:
            self._default_encoding = None
        else:
            encoding = _utf8(encoding)
            enchandler = tree.xmlFindCharEncodingHandler(encoding)
            if not enchandler:
                raise LookupError, u"unknown encoding: '%s'" % encoding
            tree.xmlCharEncCloseFunc(enchandler)
            self._default_encoding = encoding

    def _setBaseURL(self, base_url):
        self._filename = _encodeFilename(base_url)

    def _collectEvents(self, event_types, tag):
        if event_types is None:
            event_types = ()
        else:
            event_types = tuple(set(event_types))
            from .saxparser import _buildParseEventFilter
            _buildParseEventFilter(event_types)  # purely for validation
        self._events_to_collect = (event_types, tag)

    def _getParserContext(self):
        if self._parser_context is None:
            self._parser_context = self._createContext(self.target, None)
            self._parser_context._collect_ids = self._collect_ids
            if self._schema is not None:
                self._parser_context._validator = \
                    self._schema._newSaxValidator(
                        self._parse_options & xmlparser.XML_PARSE_DTDATTR)
            pctxt = self._newParserCtxt()
            _initParserContext(self._parser_context, self._resolvers, pctxt)
            self._configureSaxContext(pctxt)
        return self._parser_context

    def _getPushParserContext(self):
        if self._push_parser_context is None:
            self._push_parser_context = self._createContext(
                self.target, self._events_to_collect)
            if self._schema is not None:
                self._push_parser_context._validator = \
                    self._schema._newSaxValidator(
                        self._parse_options & xmlparser.XML_PARSE_DTDATTR)
            pctxt = self._newPushParserCtxt()
            _initParserContext(
                self._push_parser_context, self._resolvers, pctxt)
            self._configureSaxContext(pctxt)
        return self._push_parser_context

    def _createContext(self, target, events_to_collect):
        from .parsertarget import _TargetParserContext
        if target is not None:
            sax_context = _TargetParserContext(self)
            sax_context._setTarget(target)
        elif events_to_collect:
            from .saxparser import _SaxParserContext
            sax_context = _SaxParserContext(self)
        else:
            # nothing special to configure
            return _ParserContext()
        if events_to_collect:
            events, tag = events_to_collect
            sax_context._setEventFilter(events, tag)
        return sax_context

    def _configureSaxContext(self, pctxt):
        if self._remove_comments:
            pctxt.sax.comment = ffi.NULL
        if self._remove_pis:
            pctxt.sax.processingInstruction = ffi.NULL
        if self._strip_cdata:
            # hard switch-off for CDATA nodes => makes them plain text
            pctxt.sax.cdataBlock = ffi.NULL

    def _registerHtmlErrorHandler(self, c_ctxt):
        sax = c_ctxt.sax
        if sax and sax.initialized and sax.initialized != xmlparser.XML_SAX2_MAGIC:
            # need to extend SAX1 context to SAX2 to get proper error reports
            if sax == ffi.addressof(htmlparser.htmlDefaultSAXHandler):
                sax = ffi.new("xmlSAXHandler*")
                ffi.memcpy(
                    sax, htmlparser.htmlDefaultSAXHandler,
                    ffi.sizeof(htmlparser.htmlDefaultSAXHandler))
                c_ctxt.sax = sax
            sax.initialized = xmlparser.XML_SAX2_MAGIC
            sax.serror = _receiveParserError
            sax.startElementNs = ffi.NULL
            sax.endElementNs = ffi.NULL
            sax._private = ffi.NULL

    def _newParserCtxt(self):
        if self._for_html:
            c_ctxt = htmlparser.htmlCreateMemoryParserCtxt('dummy', 5)
            if c_ctxt:
                self._registerHtmlErrorHandler(c_ctxt)
        else:
            c_ctxt = xmlparser.xmlNewParserCtxt()
        if not c_ctxt:
            raise MemoryError
        c_ctxt.sax.startDocument = _initSaxDocument
        return c_ctxt

    def _newPushParserCtxt(self):
        if self._filename is not None:
            c_filename = self._filename
        else:
            c_filename = ffi.NULL
        if self._for_html:
            c_ctxt = htmlparser.htmlCreatePushParserCtxt(
                ffi.NULL, ffi.NULL, ffi.NULL,
                0, c_filename, tree.XML_CHAR_ENCODING_NONE)
            if c_ctxt:
                self._registerHtmlErrorHandler(c_ctxt)
                htmlparser.htmlCtxtUseOptions(c_ctxt, self._parse_options)
        else:
            c_ctxt = xmlparser.xmlCreatePushParserCtxt(
                ffi.NULL, ffi.NULL, ffi.NULL,
                0, c_filename)
            if c_ctxt:
                xmlparser.xmlCtxtUseOptions(c_ctxt, self._parse_options)
        if not c_ctxt:
            raise MemoryError
        c_ctxt.sax.startDocument = _initSaxDocument
        return c_ctxt

    @property
    def error_log(self):
        u"""The error log of the last parser run.
        """
        context = self._getParserContext()
        return context._error_log.copy()

    @property
    def resolvers(self):
        u"The custom resolver registry of this parser."
        return self._resolvers

    def set_element_class_lookup(self, lookup = None):
        u"""set_element_class_lookup(self, lookup = None)

        Set a lookup scheme for element classes generated from this parser.

        Reset it by passing None or nothing.
        """
        self._class_lookup = lookup

    def _copy(self):
        u"Create a new parser with the same configuration."
        parser = self.__class__()
        parser._parse_options = self._parse_options
        parser._for_html = self._for_html
        parser._remove_comments = self._remove_comments
        parser._remove_pis = self._remove_pis
        parser._strip_cdata = self._strip_cdata
        parser._filename = self._filename
        parser._resolvers = self._resolvers
        parser.target = self.target
        parser._class_lookup  = self._class_lookup
        parser._default_encoding = self._default_encoding
        parser._schema = self._schema
        parser._events_to_collect = self._events_to_collect
        return parser

    def copy(self):
        u"""copy(self)

        Create a new parser with the same configuration.
        """
        return self._copy()

    def makeelement(self, _tag, attrib=None, nsmap=None, **_extra):
        u"""makeelement(self, _tag, attrib=None, nsmap=None, **_extra)

        Creates a new element associated with this parser.
        """
        return _makeElement(_tag, ffi.NULL, None, self, None, None,
                            attrib, nsmap, _extra)

    # internal parser methods

    def _parseUnicodeDoc(self, utext, c_filename):
        u"""Parse unicode document, share dictionary if possible.
        """
        buf = ffi.new("wchar_t[]", utext)
        buffer_len = ffi.sizeof(buf) - ffi.sizeof("wchar_t")
        c_encoding = _UNICODE_ENCODING

        context = self._getParserContext()
        context.prepare()
        try:
            pctxt = context._c_ctxt
            _GLOBAL_PARSER_CONTEXT.initParserDict(pctxt)

            orig_options = pctxt.options
            if 1:
                if self._for_html:
                    result = htmlparser.htmlCtxtReadMemory(
                        pctxt, buf, buffer_len, c_filename, c_encoding,
                        self._parse_options)
                    if result:
                        if _fixHtmlDictNames(pctxt.dict, result) < 0:
                            tree.xmlFreeDoc(result)
                            result = ffi.NULL
                else:
                    result = xmlparser.xmlCtxtReadMemory(
                        pctxt, buf, buffer_len, c_filename, c_encoding,
                        self._parse_options)
            pctxt.options = orig_options # work around libxml2 problem

            return context._handleParseResultDoc(self, result, None)
        finally:
            context.cleanup()

    def _parseDoc(self, text, c_filename):
        u"""Parse document, share dictionary if possible.
        """
        if len(text) > limits.INT_MAX:
            raise ParserError, u"string is too long to parse it with libxml2"

        context = self._getParserContext()
        context.prepare()
        try:
            pctxt = context._c_ctxt
            _GLOBAL_PARSER_CONTEXT.initParserDict(pctxt)

            if self._default_encoding is None:
                c_encoding = ffi.NULL
            else:
                c_encoding = self._default_encoding

            orig_options = pctxt.options
            if 1:
                if self._for_html:
                    result = htmlparser.htmlCtxtReadMemory(
                        pctxt, text, len(text), c_filename,
                        c_encoding, self._parse_options)
                    if result:
                        if _fixHtmlDictNames(pctxt.dict, result) < 0:
                            tree.xmlFreeDoc(result)
                            result = ffi.NULL
                else:
                    result = xmlparser.xmlCtxtReadMemory(
                        pctxt, text, len(text), c_filename,
                        c_encoding, self._parse_options)
            pctxt.options = orig_options # work around libxml2 problem

            return context._handleParseResultDoc(self, result, None)
        finally:
            context.cleanup()

    def _parseDocFromFile(self, c_filename):
        context = self._getParserContext()
        context.prepare()
        try:
            pctxt = context._c_ctxt
            _GLOBAL_PARSER_CONTEXT.initParserDict(pctxt)

            if self._default_encoding is None:
                c_encoding = ffi.NULL
            else:
                c_encoding = self._default_encoding

            orig_options = pctxt.options
            if 1:
                if self._for_html:
                    result = htmlparser.htmlCtxtReadFile(
                        pctxt, c_filename, c_encoding, self._parse_options)
                    if result:
                        if _fixHtmlDictNames(pctxt.dict, result) < 0:
                            tree.xmlFreeDoc(result)
                            result = ffi.NULL
                else:
                    result = xmlparser.xmlCtxtReadFile(
                        pctxt, c_filename, c_encoding, self._parse_options)
            pctxt.options = orig_options # work around libxml2 problem

            return context._handleParseResultDoc(self, result, c_filename)
        finally:
            context.cleanup()

    def _parseDocFromFilelike(self, filelike, filename, encoding):
        if not filename:
            filename = None

        context = self._getParserContext()
        context.prepare()
        try:
            pctxt = context._c_ctxt
            _GLOBAL_PARSER_CONTEXT.initParserDict(pctxt)
            file_context = _FileReaderContext(
                filelike, context, filename,
                encoding or self._default_encoding)
            result = file_context._readDoc(pctxt, self._parse_options)

            return context._handleParseResultDoc(
                self, result, filename)
        finally:
            context.cleanup()


@ffi.callback("startDocumentSAXFunc")
def _initSaxDocument(ctxt):
    xmlparser.xmlSAX2StartDocument(ctxt)
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    c_doc = c_ctxt.myDoc

    # set up document dict
    if c_doc and c_ctxt.dict and not c_doc.dict:
        # I have no idea why libxml2 disables this - we need it
        c_ctxt.dictNames = 1
        c_doc.dict = c_ctxt.dict
        xmlparser.xmlDictReference(c_ctxt.dict)

    # set up XML ID hash table
    if c_ctxt._private and not c_ctxt.html:
        context = ffi.from_handle(c_ctxt._private)
        if context._collect_ids:
            # keep the global parser dict from filling up with XML IDs
            if c_doc and not c_doc.ids:
                # memory errors are not fatal here
                c_dict = xmlparser.xmlDictCreate()
                if c_dict:
                    c_doc.ids = tree.xmlHashCreateDict(0, c_dict)
                    xmlparser.xmlDictFree(c_dict)
                else:
                    c_doc.ids = tree.xmlHashCreate(0)
        else:
            c_ctxt.loadsubset |= xmlparser.XML_SKIP_IDS
            if c_doc and c_doc.ids and not tree.xmlHashSize(c_doc.ids):
                # already initialised but empty => clear
                tree.xmlHashFree(c_doc.ids, NULL)
                c_doc.ids = NULL


############################################################
## ET feed parser
############################################################

class _FeedParser(_BaseParser):
    _feed_parser_running = 0

    def feed(self, data):
        u"""feed(self, data)

        Feeds data to the parser.  The argument should be an 8-bit string
        buffer containing encoded data, although Unicode is supported as long
        as both string types are not mixed.

        This is the main entry point to the consumer interface of a
        parser.  The parser will parse as much of the XML stream as it
        can on each call.  To finish parsing or to reset the parser,
        call the ``close()`` method.  Both methods may raise
        ParseError if errors occur in the input data.  If an error is
        raised, there is no longer a need to call ``close()``.

        The feed parser interface is independent of the normal parser
        usage.  You can use the same parser as a feed parser and in
        the ``parse()`` function concurrently.
        """
        recover = self._parse_options & xmlparser.XML_PARSE_RECOVER
        if isinstance(data, bytes):
            if self._default_encoding is None:
                c_encoding = ffi.NULL
            else:
                c_encoding = self._default_encoding
            c_data = data
            py_buffer_len = python.PyBytes_GET_SIZE(data)
        elif isinstance(data, unicode):
            c_encoding = "utf8"
            c_data = data.encode('utf8')
            py_buffer_len = python.PyBytes_GET_SIZE(data)
        else:
            raise TypeError, u"Parsing requires string data"

        context = self._getPushParserContext()
        pctxt = context._c_ctxt
        error = 0
        if not self._feed_parser_running:
            context.prepare()
            self._feed_parser_running = 1

            if py_buffer_len > limits.INT_MAX:
                buffer_len = limits.INT_MAX
            else:
                buffer_len = py_buffer_len
            c_filename = self._filename or ffi.NULL

            if not c_encoding and py_buffer_len >= 2:
                # libxml2 can't handle BOMs here, so let's try ourselves
                if c_data[0] in b'\xfe\xef\xff':
                    # likely a BOM, let's take a closer look
                    c_encoding = _findEncodingName(
                        c_data,
                        4 if py_buffer_len > 4 else py_buffer_len)
                    if c_encoding:
                        # found it => skip over BOM (if there is one)
                        if (c_data[0] == b'\xef' and
                                c_data[1] == b'\xbb' and
                                c_data[2] == b'\xbf'):
                            c_data = c_data[3:]  # UTF-8 BOM
                            py_buffer_len -= 3
                        elif (c_data[0] == b'\xfe' and c_data[1] == b'\xff' or
                                c_data[0] == b'\xff' and c_data[1] == b'\xfe'):
                            # UTF-16 BE/LE
                            c_data = c_data[2:]
                            py_buffer_len -= 2

            if self._for_html:
                error = _htmlCtxtResetPush(
                    pctxt, ffi.NULL, 0,
                    c_filename, c_encoding,
                    self._parse_options)
            else:
                xmlparser.xmlCtxtUseOptions(pctxt, self._parse_options)
                error = xmlparser.xmlCtxtResetPush(
                    pctxt, ffi.NULL, 0, c_filename, c_encoding)
            if error:
                raise MemoryError
            _GLOBAL_PARSER_CONTEXT.initParserDict(pctxt)

        #print pctxt.charset, 'NONE' if c_encoding is NULL else c_encoding

        fixup_error = False
        while py_buffer_len > 0 and (error == 0 or recover):
            if 1:
                if py_buffer_len > limits.INT_MAX:
                    buffer_len = limits.INT_MAX
                else:
                    buffer_len = py_buffer_len
                if self._for_html:
                    c_node = pctxt.node  # last node where the parser stopped
                    error = htmlparser.htmlParseChunk(pctxt, c_data, buffer_len, 0)
                    # and now for the fun part: move node names to the dict
                    if pctxt.myDoc:
                        fixup_error = _fixHtmlDictSubtreeNames(
                            pctxt.dict, pctxt.myDoc, c_node)
                        if pctxt.myDoc.dict and pctxt.myDoc.dict != pctxt.dict:
                            xmlparser.xmlDictFree(pctxt.myDoc.dict)
                            pctxt.myDoc.dict = pctxt.dict
                            xmlparser.xmlDictReference(pctxt.dict)
                else:
                    error = xmlparser.xmlParseChunk(pctxt, c_data, buffer_len, 0)
                py_buffer_len -= buffer_len
                c_data = c_data[buffer_len:]

            if fixup_error and not context.has_raised():
                context.store_exception(MemoryError())

            if error and not pctxt.replaceEntities and not pctxt.validate:
                # in this mode, we ignore errors about undefined entities
                for entry in context._error_log.filter_from_errors():
                    if entry.type != ErrorTypes.WAR_UNDECLARED_ENTITY and \
                           entry.type != ErrorTypes.ERR_UNDECLARED_ENTITY:
                        break
                else:
                    error = 0

        if fixup_error or not recover and (error or not pctxt.wellFormed):
            self._feed_parser_running = 0
            try:
                context._handleParseResult(self, pctxt.myDoc, None)
            finally:
                context.cleanup()

    def close(self):
        u"""close(self)

        Terminates feeding data to this parser.  This tells the parser to
        process any remaining data in the feed buffer, and then returns the
        root Element of the tree that was parsed.

        This method must be called after passing the last chunk of data into
        the ``feed()`` method.  It should only be called when using the feed
        parser interface, all other usage is undefined.
        """
        from .etree import _Document
        if not self._feed_parser_running:
            raise XMLSyntaxError(u"no element found",
                                 xmlerror.XML_ERR_INTERNAL_ERROR, 0, 0)

        context = self._getPushParserContext()
        pctxt = context._c_ctxt

        self._feed_parser_running = 0
        if self._for_html:
            htmlparser.htmlParseChunk(pctxt, ffi.NULL, 0, 1)
        else:
            xmlparser.xmlParseChunk(pctxt, ffi.NULL, 0, 1)

        from .saxparser import _SaxParserContext
        if (pctxt.recovery and not pctxt.disableSAX and
            isinstance(context, _SaxParserContext)):
            # apply any left-over 'end' events
            context.flushEvents()

        try:
            result = context._handleParseResult(self, pctxt.myDoc, None)
        finally:
            context.cleanup()

        if isinstance(result, _Document):
            return result.getroot()
        else:
            return result

def _htmlCtxtResetPush(c_ctxt, c_data, buffer_len,
                       c_filename, c_encoding, parse_options):
    # libxml2 lacks an HTML push parser setup function
    error = xmlparser.xmlCtxtResetPush(
        c_ctxt, ffi.NULL, 0, c_filename, c_encoding)
    if error:
        return error

    # fix libxml2 setup for HTML
    c_ctxt.progressive = 1
    c_ctxt.html = 1
    htmlparser.htmlCtxtUseOptions(c_ctxt, parse_options)

    if c_data and buffer_len > 0:
        return htmlparser.htmlParseChunk(c_ctxt, c_data, buffer_len, 0)
    return 0

############################################################
## XML parser
############################################################

_XML_DEFAULT_PARSE_OPTIONS = (
    xmlparser.XML_PARSE_NOENT   |
    xmlparser.XML_PARSE_NOCDATA |
    xmlparser.XML_PARSE_NONET   |
    xmlparser.XML_PARSE_COMPACT |
    xmlparser.XML_PARSE_BIG_LINES
    )

class XMLParser(_FeedParser):
    u"""XMLParser(self, encoding=None, attribute_defaults=False, dtd_validation=False, load_dtd=False, no_network=True, ns_clean=False, recover=False, XMLSchema schema=None, remove_blank_text=False, resolve_entities=True, remove_comments=False, remove_pis=False, strip_cdata=True, collect_ids=True, target=None, compact=True)

    The XML parser.

    Parsers can be supplied as additional argument to various parse
    functions of the lxml API.  A default parser is always available
    and can be replaced by a call to the global function
    'set_default_parser'.  New parsers can be created at any time
    without a major run-time overhead.

    The keyword arguments in the constructor are mainly based on the
    libxml2 parser configuration.  A DTD will also be loaded if DTD
    validation or attribute default values are requested (unless you
    additionally provide an XMLSchema from which the default
    attributes can be read).

    Available boolean keyword arguments:

    - attribute_defaults - inject default attributes from DTD or XMLSchema
    - dtd_validation     - validate against a DTD referenced by the document
    - load_dtd           - use DTD for parsing
    - no_network         - prevent network access for related files (default: True)
    - ns_clean           - clean up redundant namespace declarations
    - recover            - try hard to parse through broken XML
    - remove_blank_text  - discard blank text nodes that appear ignorable
    - remove_comments    - discard comments
    - remove_pis         - discard processing instructions
    - strip_cdata        - replace CDATA sections by normal text content (default: True)
    - compact            - save memory for short text content (default: True)
    - collect_ids        - create a hash table of XML IDs (default: True, always True with DTD validation)
    - resolve_entities   - replace entities by their text value (default: True)
    - huge_tree          - disable security restrictions and support very deep trees
                           and very long text content (only affects libxml2 2.7+)

    Other keyword arguments:

    - encoding - override the document encoding
    - target   - a parser target object that will receive the parse events
    - schema   - an XMLSchema to validate against

    Note that you should avoid sharing parsers between threads.  While this is
    not harmful, it is more efficient to use separate parsers.  This does not
    apply to the default parser.
    """
    def __init__(self, encoding=None, attribute_defaults=False,
                 dtd_validation=False, load_dtd=False, no_network=True,
                 ns_clean=False, recover=False, schema=None,
                 huge_tree=False, remove_blank_text=False, resolve_entities=True,
                 remove_comments=False, remove_pis=False, strip_cdata=True,
                 collect_ids=True, target=None, compact=True):
        parse_options = _XML_DEFAULT_PARSE_OPTIONS
        if load_dtd:
            parse_options = parse_options | xmlparser.XML_PARSE_DTDLOAD
        if dtd_validation:
            parse_options = parse_options | xmlparser.XML_PARSE_DTDVALID | \
                            xmlparser.XML_PARSE_DTDLOAD
        if attribute_defaults:
            parse_options = parse_options | xmlparser.XML_PARSE_DTDATTR
            if schema is None:
                parse_options = parse_options | xmlparser.XML_PARSE_DTDLOAD
        if ns_clean:
            parse_options = parse_options | xmlparser.XML_PARSE_NSCLEAN
        if recover:
            parse_options = parse_options | xmlparser.XML_PARSE_RECOVER
        if remove_blank_text:
            parse_options = parse_options | xmlparser.XML_PARSE_NOBLANKS
        if huge_tree:
            parse_options = parse_options | xmlparser.XML_PARSE_HUGE
        if not no_network:
            parse_options = parse_options ^ xmlparser.XML_PARSE_NONET
        if not compact:
            parse_options = parse_options ^ xmlparser.XML_PARSE_COMPACT
        if not resolve_entities:
            parse_options = parse_options ^ xmlparser.XML_PARSE_NOENT
        if not strip_cdata:
            parse_options = parse_options ^ xmlparser.XML_PARSE_NOCDATA

        _BaseParser.__init__(self, parse_options, 0, schema,
                             remove_comments, remove_pis, strip_cdata,
                             collect_ids, target, encoding)


class XMLPullParser(XMLParser):
    """XMLPullParser(self, events=None, *, tag=None, **kwargs)

    XML parser that collects parse events in an iterator.

    The collected events are the same as for iterparse(), but the
    parser itself is non-blocking in the sense that it receives
    data chunks incrementally through its .feed() method, instead
    of reading them directly from a file(-like) object all by itself.

    By default, it collects Element end events.  To change that,
    pass any subset of the available events into the ``events``
    argument: ``'start'``, ``'end'``, ``'start-ns'``,
    ``'end-ns'``, ``'comment'``, ``'pi'``.

    To support loading external dependencies relative to the input
    source, you can pass the ``base_url``.
    """
    def __init__(self, events=None, tag=None, base_url=None, **kwargs):
        XMLParser.__init__(self, **kwargs)
        if events is None:
            events = ('end',)
        self._setBaseURL(base_url)
        self._collectEvents(events, tag)

    def read_events(self):
        return self._getPushParserContext().events_iterator


_DEFAULT_XML_PARSER = XMLParser()

def set_default_parser(parser=None):
    u"""set_default_parser(parser=None)

    Set a default parser for the current thread.  This parser is used
    globally whenever no parser is supplied to the various parse functions of
    the lxml API.  If this function is called without a parser (or if it is
    None), the default parser is reset to the original configuration.

    Note that the pre-installed default parser is not thread-safe.  Avoid the
    default parser in multi-threaded environments.  You can create a separate
    parser for each thread explicitly or use a parser pool.
    """
    if parser is None:
        parser = _DEFAULT_XML_PARSER
    _GLOBAL_PARSER_CONTEXT.setDefaultParser(parser)

def get_default_parser():
    u"get_default_parser()"
    return _GLOBAL_PARSER_CONTEXT.getDefaultParser()

############################################################
## HTML parser
############################################################

_HTML_DEFAULT_PARSE_OPTIONS = (
    htmlparser.HTML_PARSE_RECOVER |
    htmlparser.HTML_PARSE_NONET   |
    htmlparser.HTML_PARSE_COMPACT
    )

class HTMLParser(_FeedParser):
    u"""HTMLParser(self, encoding=None, remove_blank_text=False, \
                   remove_comments=False, remove_pis=False, strip_cdata=True, \
                   no_network=True, target=None, XMLSchema schema=None, \
                   recover=True, compact=True)

    The HTML parser.

    This parser allows reading HTML into a normal XML tree.  By
    default, it can read broken (non well-formed) HTML, depending on
    the capabilities of libxml2.  Use the 'recover' option to switch
    this off.

    Available boolean keyword arguments:

    - recover            - try hard to parse through broken HTML (default: True)
    - no_network         - prevent network access for related files (default: True)
    - remove_blank_text  - discard empty text nodes that are ignorable (i.e. not actual text content)
    - remove_comments    - discard comments
    - remove_pis         - discard processing instructions
    - strip_cdata        - replace CDATA sections by normal text content (default: True)
    - compact            - save memory for short text content (default: True)

    Other keyword arguments:

    - encoding - override the document encoding
    - target   - a parser target object that will receive the parse events
    - schema   - an XMLSchema to validate against

    Note that you should avoid sharing parsers between threads for performance
    reasons.
    """
    def __init__(self, encoding=None, remove_blank_text=False,
                 remove_comments=False, remove_pis=False, strip_cdata=True,
                 no_network=True, target=None, schema=None,
                 recover=True, compact=True):
        parse_options = _HTML_DEFAULT_PARSE_OPTIONS
        if remove_blank_text:
            parse_options = parse_options | htmlparser.HTML_PARSE_NOBLANKS
        if not recover:
            parse_options = parse_options ^ htmlparser.HTML_PARSE_RECOVER
        if not no_network:
            parse_options = parse_options ^ htmlparser.HTML_PARSE_NONET
        if not compact:
            parse_options = parse_options ^ htmlparser.HTML_PARSE_COMPACT

        _BaseParser.__init__(self, parse_options, 1, schema,
                             remove_comments, remove_pis, strip_cdata, True,
                             target, encoding)


class HTMLPullParser(HTMLParser):
    """HTMLPullParser(self, events=None, *, tag=None, base_url=None, **kwargs)

    HTML parser that collects parse events in an iterator.

    The collected events are the same as for iterparse(), but the
    parser itself is non-blocking in the sense that it receives
    data chunks incrementally through its .feed() method, instead
    of reading them directly from a file(-like) object all by itself.

    By default, it collects Element end events.  To change that,
    pass any subset of the available events into the ``events``
    argument: ``'start'``, ``'end'``, ``'start-ns'``,
    ``'end-ns'``, ``'comment'``, ``'pi'``.

    To support loading external dependencies relative to the input
    source, you can pass the ``base_url``.
    """
    def __init__(self, events=None, tag=None, base_url=None, **kwargs):
        HTMLParser.__init__(self, **kwargs)
        if events is None:
            events = ('end',)
        self._setBaseURL(base_url)
        self._collectEvents(events, tag)

    def read_events(self):
        return self._getPushParserContext().events_iterator


_DEFAULT_HTML_PARSER = HTMLParser()

############################################################
## helper functions for document creation
############################################################

def _parseDoc(text, filename, parser):
    if parser is None:
        parser = _GLOBAL_PARSER_CONTEXT.getDefaultParser()
    if not filename:
        c_filename = ffi.NULL
    else:
        filename_utf = _encodeFilenameUTF8(filename)
        c_filename = filename_utf
    if isinstance(text, unicode):
        if len(text) * ffi.sizeof("wchar_t") > limits.INT_MAX:
            return parser._parseDocFromFilelike(
                io.StringIO(text), filename, None)
        if not _UNICODE_ENCODING:
            text = text.encode('utf8')
            return parser._parseDocFromFilelike(
                BytesIO(text), filename, "UTF-8")
        return parser._parseUnicodeDoc(text, c_filename)
    else:
        c_len = python.PyBytes_GET_SIZE(text)
        if c_len > limits.INT_MAX:
            return parser._parseDocFromFilelike(
                BytesIO(text), filename, None)
        return parser._parseDoc(text, c_filename)

def _parseDocFromFile(filename8, parser):
    if parser is None:
        parser = _GLOBAL_PARSER_CONTEXT.getDefaultParser()
    return parser._parseDocFromFile(filename8)

def _parseDocFromFilelike(source, filename, parser):
    if parser is None:
        parser = _GLOBAL_PARSER_CONTEXT.getDefaultParser()
    return parser._parseDocFromFilelike(source, filename, None)

def _newXMLDoc():
    result = tree.xmlNewDoc(ffi.NULL)
    if not result:
        python.PyErr_NoMemory()
    if not result.encoding:
        result.encoding = tree.xmlStrdup("UTF-8")
    _GLOBAL_PARSER_CONTEXT.initDocDict(result)
    return result

def _newHTMLDoc():
    result = htmlparser.htmlNewDoc(ffi.NULL, ffi.NULL)
    if not result:
        raise MemoryError()
    _GLOBAL_PARSER_CONTEXT.initDocDict(result)
    return result

def _copyDoc(c_doc, recursive):
    if recursive:
        result = tree.xmlCopyDoc(c_doc, recursive)
    else:
        result = tree.xmlCopyDoc(c_doc, 0)
    if not result:
        raise MemoryError()
    _GLOBAL_PARSER_CONTEXT.initDocDict(result)
    return result

def _copyDocRoot(c_doc, c_new_root):
    u"Recursively copy the document and make c_new_root the new root node."
    result = tree.xmlCopyDoc(c_doc, 0) # non recursive
    _GLOBAL_PARSER_CONTEXT.initDocDict(result)
    c_node = tree.xmlDocCopyNode(c_new_root, result, 1) # recursive
    if not c_node:
        python.PyErr_NoMemory()
    tree.xmlDocSetRootElement(result, c_node)
    _copyTail(c_new_root.next, c_node)
    return result

def _copyNodeToDoc(c_node, c_doc):
    u"Recursively copy the element into the document. c_doc is not modified."
    c_root = tree.xmlDocCopyNode(c_node, c_doc, 1) # recursive
    if not c_root:
        raise MemoryError()
    _copyTail(c_node.next, c_root)
    return c_root


############################################################
## API level helper functions for _Document creation
############################################################

def _parseDocument(source, parser, base_url):
    if not isinstance(parser, _BaseParser) and parser is not None:
        raise TypeError("Expected a Parser object, got %s" %
                        parser.__class__.__name__)
    if _isString(source):
        # parse the file directly from the filesystem
        doc = _parseDocumentFromURL(_encodeFilename(source), parser)
        # fix base URL if requested
        if base_url is not None:
            base_url = _encodeFilenameUTF8(base_url)
            if doc._c_doc.URL:
                tree.xmlFree(doc._c_doc.URL)
            doc._c_doc.URL = tree.xmlStrdup(base_url)
        return doc

    if base_url is not None:
        url = base_url
    else:
        url = _getFilenameForFile(source)

    if hasattr(source, u'getvalue') and hasattr(source, u'tell'):
        # StringIO - reading from start?
        if source.tell() == 0:
            return _parseMemoryDocument(source.getvalue(), url, parser)

    # Support for file-like objects (urlgrabber.urlopen, ...)
    if hasattr(source, u'read'):
        return _parseFilelikeDocument(
            source, url, parser)

    raise TypeError, u"cannot parse from '%s'" % python._fqtypename(source).decode('UTF-8')

def _parseDocumentFromURL(url, parser):
    c_doc = _parseDocFromFile(url, parser)
    return _documentFactory(c_doc, parser)

def _parseMemoryDocument(text, url, parser):
    if isinstance(text, unicode):
        if _hasEncodingDeclaration(text):
            raise ValueError(
                u"Unicode strings with encoding declaration are not supported. "
                u"Please use bytes input or XML fragments without declaration.")
    elif not isinstance(text, bytes):
        raise ValueError, u"can only parse strings"
    c_doc = _parseDoc(text, url, parser)
    return _documentFactory(c_doc, parser)

def _parseFilelikeDocument(source, url, parser):
    c_doc = _parseDocFromFilelike(source, url, parser)
    return _documentFactory(c_doc, parser)
