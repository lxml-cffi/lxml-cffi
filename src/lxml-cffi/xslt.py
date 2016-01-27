# XSLT

import re

from .etree import __unpackIntVersion
from ._libxml2 import ffi, lib

LIBXSLT_VERSION = __unpackIntVersion(lib.xsltLibxsltVersion)
LIBXSLT_COMPILED_VERSION = __unpackIntVersion(lib.xsltLibxsltVersion)

from .apihelpers import _documentOrRaise, _rootNodeOrRaise
from .apihelpers import _assertValidNode, _assertValidDoc
from .apihelpers import _utf8, _decodeFilename, funicode, funicodeOrNone
from .apihelpers import _stripEncodingDeclaration
from .proxy import fixThreadDictNames
from .xmlerror import _ErrorLog
from .xmlerror import pyXsltGenericErrorFunc
from .docloader import _ResolverContext, _initResolverContext
from .docloader import (
    PARSER_DATA_STRING, PARSER_DATA_FILENAME, PARSER_DATA_FILE, PARSER_DATA_EMPTY)
from .extensions import _BaseContext, _xpath_function_call
from . import python
from .etree import LxmlError, _elementFactory, _elementTreeFactory, _documentFactory, _newElementTree, _ElementTree, ElementTree
from .xsltext import _registerXSLTExtensions, XSLTExtension
from .classlookup import PIBase
from .parser import _parseDocumentFromURL, _parseDoc, _GLOBAL_PARSER_CONTEXT, _copyDoc
xslt = tree = xmlparser = xmlerror = lib

class XSLTError(LxmlError):
    u"""Base class of all XSLT errors.
    """
    pass

class XSLTParseError(XSLTError):
    u"""Error parsing a stylesheet document.
    """
    pass

class XSLTApplyError(XSLTError):
    u"""Error running an XSL transformation.
    """
    pass

class XSLTSaveError(XSLTError):
    u"""Error serialising an XSLT result.
    """
    pass

class XSLTExtensionError(XSLTError):
    u"""Error registering an XSLT extension.
    """
    pass

################################################################################
# Where do we store what?
#
# xsltStylesheet->doc->_private
#    == _XSLTResolverContext for XSL stylesheet
#
# xsltTransformContext->_private
#    == _XSLTResolverContext for transformed document
#
################################################################################


################################################################################
# XSLT document loaders

class _XSLTResolverContext(_ResolverContext):
    def _copy(self):
        context = _XSLTResolverContext()
        _initXSLTResolverContext(context, self._parser)
        context._c_style_doc = self._c_style_doc
        return context

def _initXSLTResolverContext(context, parser):
    _initResolverContext(context, parser.resolvers)
    context._parser = parser
    context._c_style_doc = ffi.NULL

def _xslt_resolve_from_python(c_uri, c_context, parse_options):
    # call the Python document loaders
    context = ffi.from_handle(c_context)

    # shortcut if we resolve the stylesheet itself
    c_doc = context._c_style_doc
    if c_doc and c_doc.URL:
        if tree.xmlStrcmp(c_uri, c_doc.URL) == 0:
            return _copyDoc(c_doc, 1), 0

    # delegate to the Python resolvers
    try:
        resolvers = context._resolvers
        uri = _decodeFilename(ffi.string(c_uri))
        if uri.startswith(u'string://__STRING__XSLT__/'):
            uri = uri[26:]
        doc_ref = resolvers.resolve(uri, None, context)

        c_doc = ffi.NULL
        if doc_ref is not None:
            if doc_ref._type == PARSER_DATA_STRING:
                c_doc = _parseDoc(
                    doc_ref._data_bytes, doc_ref._filename, context._parser)
            elif doc_ref._type == PARSER_DATA_FILENAME:
                c_doc = _parseDocFromFile(doc_ref._filename, context._parser)
            elif doc_ref._type == PARSER_DATA_FILE:
                c_doc = _parseDocFromFilelike(
                    doc_ref._file, doc_ref._filename, context._parser)
            elif doc_ref._type == PARSER_DATA_EMPTY:
                c_doc = _newXMLDoc()
            if c_doc and not c_doc.URL:
                c_doc.URL = tree.xmlStrdup(c_uri)
        return c_doc, 0
    except:
        context._store_raised()
        return ffi.NULL, 1

def _xslt_store_resolver_exception(c_uri, context, c_type):
    context = ffi.from_handle(context)
    try:
        uri = ffi.string(c_uri)
        message = u"Cannot resolve URI %s" % _decodeFilename(uri)
        if c_type == xslt.XSLT_LOAD_DOCUMENT:
            exception = XSLTApplyError(message)
        else:
            exception = XSLTParseError(message)
        context._store_exception(exception)
    except Exception, e:
        context._store_exception(e)

@ffi.callback("xsltDocLoaderFunc")
def _xslt_doc_loader(c_uri, c_dict,
                     parse_options, c_ctxt,
                     c_type):
    # nogil => no Python objects here, may be called without thread context !
    # find resolver contexts of stylesheet and transformed doc
    if c_type == xslt.XSLT_LOAD_DOCUMENT:
        # transformation time
        c_pcontext = ffi.cast("xsltTransformContextPtr", c_ctxt)._private
    elif c_type == xslt.XSLT_LOAD_STYLESHEET:
        # include/import resolution while parsing
        c_pcontext = ffi.cast("xsltStylesheetPtr", c_ctxt).doc._private
    else:
        c_pcontext = ffi.NULL

    if not c_pcontext:
        # can't call Python without context, fall back to default loader
        return XSLT_DOC_DEFAULT_LOADER(
            c_uri, c_dict, parse_options, c_ctxt, c_type)

    c_doc, error = _xslt_resolve_from_python(c_uri, c_pcontext, parse_options)
    if not c_doc and not error:
        c_doc = XSLT_DOC_DEFAULT_LOADER(
            c_uri, c_dict, parse_options, c_ctxt, c_type)
        if not c_doc:
            _xslt_store_resolver_exception(c_uri, c_pcontext, c_type)

    if c_doc and c_type == xslt.XSLT_LOAD_STYLESHEET:
        c_doc._private = c_pcontext
    return c_doc

XSLT_DOC_DEFAULT_LOADER = xslt.xsltDocDefaultLoader
xslt.xsltSetLoaderFunc(_xslt_doc_loader)

################################################################################
# XSLT file/network access control

class XSLTAccessControl(object):
    u"""XSLTAccessControl(self, read_file=True, write_file=True, create_dir=True, read_network=True, write_network=True)

    Access control for XSLT: reading/writing files, directories and
    network I/O.  Access to a type of resource is granted or denied by
    passing any of the following boolean keyword arguments.  All of
    them default to True to allow access.

    - read_file
    - write_file
    - create_dir
    - read_network
    - write_network

    For convenience, there is also a class member `DENY_ALL` that
    provides an XSLTAccessControl instance that is readily configured
    to deny everything, and a `DENY_WRITE` member that denies all
    write access but allows read access.

    See `XSLT`.
    """

    def __init__(self, read_file=True, write_file=True, create_dir=True,
                 read_network=True, write_network=True):
        self._prefs = xslt.xsltNewSecurityPrefs()
        if not self._prefs:
            raise MemoryError()

        self._setAccess(xslt.XSLT_SECPREF_READ_FILE, read_file)
        self._setAccess(xslt.XSLT_SECPREF_WRITE_FILE, write_file)
        self._setAccess(xslt.XSLT_SECPREF_CREATE_DIRECTORY, create_dir)
        self._setAccess(xslt.XSLT_SECPREF_READ_NETWORK, read_network)
        self._setAccess(xslt.XSLT_SECPREF_WRITE_NETWORK, write_network)

    def __del__(self):
        if self._prefs:
            xslt.xsltFreeSecurityPrefs(self._prefs)

    def _setAccess(self, option, allow):
        if allow:
            function = ffi.addressof(lib, 'xsltSecurityAllow')
        else:
            function = ffi.addressof(lib, 'xsltSecurityForbid')
        xslt.xsltSetSecurityPrefs(self._prefs, option, function)

    def _register_in_context(self, ctxt):
        xslt.xsltSetCtxtSecurityPrefs(self._prefs, ctxt)

    @property
    def options(self):
        u"The access control configuration as a map of options."
        return {
            u'read_file': self._optval(xslt.XSLT_SECPREF_READ_FILE),
            u'write_file': self._optval(xslt.XSLT_SECPREF_WRITE_FILE),
            u'create_dir': self._optval(xslt.XSLT_SECPREF_CREATE_DIRECTORY),
            u'read_network': self._optval(xslt.XSLT_SECPREF_READ_NETWORK),
            u'write_network': self._optval(xslt.XSLT_SECPREF_WRITE_NETWORK),
            }

    def _optval(self, option):
        function = xslt.xsltGetSecurityPrefs(self._prefs, option)
        if function == ffi.addressof(lib, 'xsltSecurityAllow'):
            return True
        elif function == ffi.addressof(lib, 'xsltSecurityForbid'):
            return False
        else:
            return None

    def __repr__(self):
        items = sorted(self.options.items())
        return u"%s(%s)" % (
            python._fqtypename(self).decode('UTF-8').split(u'.')[-1],
            u', '.join([u"%s=%r" % item for item in items]))

XSLTAccessControl.DENY_ALL = XSLTAccessControl(
    read_file=False, write_file=False, create_dir=False,
    read_network=False, write_network=False)

XSLTAccessControl.DENY_WRITE = XSLTAccessControl(
    read_file=True, write_file=False, create_dir=False,
    read_network=True, write_network=False)


################################################################################
# XSLT

def _register_xslt_function(ctxt, name_utf, ns_utf):
    if ns_utf is None:
        return 0
    # libxml2 internalises the strings if ctxt has a dict
    return xslt.xsltRegisterExtFunction(
        ctxt, name_utf, ns_utf,
        _xpath_function_call)

EMPTY_DICT = {}

class _XSLTContext(_BaseContext):
    _xsltCtxt = ffi.NULL
    _extension_elements = EMPTY_DICT

    def __init__(self, namespaces, extensions, error_log, enable_regexp,
                 build_smart_strings):
        if extensions is not None and extensions:
            for ns_name_tuple, extension in extensions.items():
                if ns_name_tuple[0] is None:
                    raise XSLTExtensionError, \
                        u"extensions must not have empty namespaces"
                if isinstance(extension, XSLTExtension):
                    if self._extension_elements is EMPTY_DICT:
                        self._extension_elements = {}
                        extensions = extensions.copy()
                    ns_utf   = _utf8(ns_name_tuple[0])
                    name_utf = _utf8(ns_name_tuple[1])
                    self._extension_elements[(ns_utf, name_utf)] = extension
                    del extensions[ns_name_tuple]
        _BaseContext.__init__(self, namespaces, extensions, error_log, enable_regexp,
                              build_smart_strings)

    def _copy(self):
        context = _BaseContext._copy(self)
        context._extension_elements = self._extension_elements
        return context

    def register_context(self, xsltCtxt, doc):
        self._xsltCtxt = xsltCtxt
        self._set_xpath_context(xsltCtxt.xpathCtxt)
        self._register_context(doc)
        self.registerLocalFunctions(xsltCtxt, _register_xslt_function)
        self.registerGlobalFunctions(xsltCtxt, _register_xslt_function)
        _registerXSLTExtensions(xsltCtxt, self._extension_elements)

    def free_context(self):
        self._cleanup_context()
        self._release_context()
        if self._xsltCtxt:
            xslt.xsltFreeTransformContext(self._xsltCtxt)
            self._xsltCtxt = ffi.NULL
        self._release_temp_refs()


class _XSLTQuotedStringParam(object):
    u"""A wrapper class for literal XSLT string parameters that require
    quote escaping.
    """
    def __init__(self, strval):
        self.strval = strval


class XSLT(object):
    u"""XSLT(self, xslt_input, extensions=None, regexp=True, access_control=None)

    Turn an XSL document into an XSLT object.

    Calling this object on a tree or Element will execute the XSLT::

      >>> transform = etree.XSLT(xsl_tree)
      >>> result = transform(xml_tree)

    Keyword arguments of the constructor:

    - extensions: a dict mapping ``(namespace, name)`` pairs to
      extension functions or extension elements
    - regexp: enable exslt regular expression support in XPath
      (default: True)
    - access_control: access restrictions for network or file
      system (see `XSLTAccessControl`)

    Keyword arguments of the XSLT call:

    - profile_run: enable XSLT profiling (default: False)

    Other keyword arguments of the call are passed to the stylesheet
    as parameters.
    """
    _c_style = ffi.NULL
    _xslt_resolver_context = None

    def __init__(self, xslt_input, extensions=None, regexp=True,
                 access_control=None):
        from .parser import _copyDocRoot, _copyDoc
        doc = _documentOrRaise(xslt_input)
        root_node = _rootNodeOrRaise(xslt_input)

        # set access control or raise TypeError
        self._access_control = access_control

        # make a copy of the document as stylesheet parsing modifies it
        c_doc = _copyDocRoot(doc._c_doc, root_node._c_node)

        # make sure we always have a stylesheet URL
        if not c_doc.URL:
            doc_url_utf = python.PyUnicode_AsASCIIString(
                u"string://__STRING__XSLT__/%d.xslt" % id(self))
            c_doc.URL = tree.xmlStrdup(doc_url_utf)

        self._error_log = _ErrorLog()
        self._xslt_resolver_context = _XSLTResolverContext()
        _initXSLTResolverContext(self._xslt_resolver_context, doc._parser)
        # keep a copy in case we need to access the stylesheet via 'document()'
        self._xslt_resolver_context._c_style_doc = _copyDoc(c_doc, 1)
        c_doc._private = self._keepalive = ffi.new_handle(self._xslt_resolver_context)

        with self._error_log:
            c_style = xslt.xsltParseStylesheetDoc(c_doc)

        if not c_style or c_style.errors:
            tree.xmlFreeDoc(c_doc)
            if c_style:
                xslt.xsltFreeStylesheet(c_style)
            self._xslt_resolver_context._raise_if_stored()
            # last error seems to be the most accurate here
            if self._error_log.last_error is not None and \
                    self._error_log.last_error.message:
                raise XSLTParseError(self._error_log.last_error.message,
                                     self._error_log)
            else:
                raise XSLTParseError(
                    self._error_log._buildExceptionMessage(
                        u"Cannot parse stylesheet"),
                    self._error_log)

        c_doc._private = ffi.NULL # no longer used!
        self._c_style = c_style
        self._context = _XSLTContext(None, extensions, self._error_log, regexp, True)

    def __del__(self):
        if self._xslt_resolver_context is not None and \
               self._xslt_resolver_context._c_style_doc:
            tree.xmlFreeDoc(self._xslt_resolver_context._c_style_doc)
        # this cleans up the doc copy as well
        if self._c_style:
            xslt.xsltFreeStylesheet(self._c_style)

    @property
    def error_log(self):
        u"The log of errors and warnings of an XSLT execution."
        return self._error_log.copy()

    @staticmethod
    def strparam(strval):
        u"""strparam(strval)

        Mark an XSLT string parameter that requires quote escaping
        before passing it into the transformation.  Use it like this::

            result = transform(doc, some_strval = XSLT.strparam(
                '''it's \"Monty Python's\" ...'''))

        Escaped string parameters can be reused without restriction.
        """
        return _XSLTQuotedStringParam(strval)

    def __deepcopy__(self, memo):
        return self.__copy__()

    def __copy__(self):
        return _copyXSLT(self)

    def __call__(self, _input, profile_run=False, **kw):
        u"""__call__(self, _input, profile_run=False, **kw)

        Execute the XSL transformation on a tree or Element.

        Pass the ``profile_run`` option to get profile information
        about the XSLT.  The result of the XSLT will have a property
        xslt_profile that holds an XML tree with profiling data.
        """
        from .proxy import _fakeRootDoc, _destroyFakeDoc
        context = None
        profile_doc = None
        c_result = ffi.NULL

        assert self._c_style, "XSLT stylesheet not initialised"
        input_doc = _documentOrRaise(_input)
        root_node = _rootNodeOrRaise(_input)

        c_doc = _fakeRootDoc(input_doc._c_doc, root_node._c_node)

        transform_ctxt = xslt.xsltNewTransformContext(self._c_style, c_doc)
        if not transform_ctxt:
            _destroyFakeDoc(input_doc._c_doc, c_doc)
            raise MemoryError()

        # using the stylesheet dict is safer than using a possibly
        # unrelated dict from the current thread.  Almost all
        # non-input tag/attr names will come from the stylesheet
        # anyway.
        if transform_ctxt.dict:
            xmlparser.xmlDictFree(transform_ctxt.dict)
        if kw:
            # parameter values are stored in the dict
            # => avoid unnecessarily cluttering the global dict
            transform_ctxt.dict = xmlparser.xmlDictCreateSub(self._c_style.doc.dict)
            if not transform_ctxt.dict:
                xslt.xsltFreeTransformContext(transform_ctxt)
                raise MemoryError()
        else:
            transform_ctxt.dict = self._c_style.doc.dict
            xmlparser.xmlDictReference(transform_ctxt.dict)

        xslt.xsltSetCtxtParseOptions(
            transform_ctxt, input_doc._parser._parse_options)

        if profile_run:
            transform_ctxt.profile = 1

        try:
            context = self._context._copy()
            context.register_context(transform_ctxt, input_doc)

            resolver_context = self._xslt_resolver_context._copy()
            transform_ctxt._private = resolver_context._keepalive = ffi.new_handle(resolver_context)

            params = _convert_xslt_parameters(transform_ctxt, kw)
            c_result = self._run_transform(
                c_doc, params, context, transform_ctxt)

            if transform_ctxt.state != xslt.XSLT_STATE_OK:
                if c_result:
                    tree.xmlFreeDoc(c_result)
                    c_result = ffi.NULL

            if transform_ctxt.profile:
                c_profile_doc = xslt.xsltGetProfileInformation(transform_ctxt)
                if c_profile_doc:
                    profile_doc = _documentFactory(
                        c_profile_doc, input_doc._parser)
        finally:
            if context is not None:
                context.free_context()
            _destroyFakeDoc(input_doc._c_doc, c_doc)

        try:
            if resolver_context and resolver_context._has_raised():
                if c_result:
                    tree.xmlFreeDoc(c_result)
                    c_result = ffi.NULL
                resolver_context._raise_if_stored()

            if context._exc._has_raised():
                if c_result:
                    tree.xmlFreeDoc(c_result)
                    c_result = ffi.NULL
                context._exc._raise_if_stored()

            if not c_result:
                # last error seems to be the most accurate here
                error = self._error_log.last_error
                if error is not None and error.message:
                    if error.line > 0:
                        message = u"%s, line %d" % (error.message, error.line)
                    else:
                        message = error.message
                elif error is not None and error.line > 0:
                    message = u"Error applying stylesheet, line %d" % error.line
                else:
                    message = u"Error applying stylesheet"
                raise XSLTApplyError(message, self._error_log)
        finally:
            if resolver_context is not None:
                resolver_context.clear()

        result_doc = _documentFactory(c_result, input_doc._parser)

        c_dict = c_result.dict
        xmlparser.xmlDictReference(c_dict)
        c_result.dict = _GLOBAL_PARSER_CONTEXT.initThreadDictRef(c_result.dict)
        if c_dict is not c_result.dict or \
                self._c_style.doc.dict is not c_result.dict or \
                input_doc._c_doc.dict is not c_result.dict:
            if 1:
                if c_dict is not c_result.dict:
                    fixThreadDictNames(ffi.cast("xmlNodePtr", c_result),
                                       c_dict, c_result.dict)
                if self._c_style.doc.dict is not c_result.dict:
                    fixThreadDictNames(ffi.cast("xmlNodePtr", c_result),
                                       self._c_style.doc.dict, c_result.dict)
                if input_doc._c_doc.dict is not c_result.dict:
                    fixThreadDictNames(ffi.cast("xmlNodePtr", c_result),
                                       input_doc._c_doc.dict, c_result.dict)
        xmlparser.xmlDictFree(c_dict)

        return _xsltResultTreeFactory(result_doc, self, profile_doc)

    def _run_transform(self, c_input_doc, params, _context, transform_ctxt):
        xslt.xsltSetTransformErrorFunc(
            transform_ctxt, self._error_log.get_handle(), pyXsltGenericErrorFunc)
        if self._access_control is not None:
            self._access_control._register_in_context(transform_ctxt)
        if 1:
            c_params = [ffi.new("char[]", param) for param in params]
            c_params.append(ffi.NULL)
            c_result = xslt.xsltApplyStylesheetUser(
                self._c_style, c_input_doc, c_params,
                ffi.NULL, ffi.NULL, transform_ctxt)
        return c_result

def _convert_xslt_parameters(transform_ctxt, parameters):
    from .xpath import XPath
    c_dict = transform_ctxt.dict
    params = []
    for key, value in parameters.iteritems():
        k = _utf8(key)
        if isinstance(value, _XSLTQuotedStringParam):
            v = value.strval
            xslt.xsltQuoteOneUserParam(
                transform_ctxt, k, v)
        else:
            if isinstance(value, XPath):
                v = value._path
            else:
                v = _utf8(value)
            params.append(ffi.string(
                tree.xmlDictLookup(c_dict, k, len(k))))
            params.append(ffi.string(
                tree.xmlDictLookup(c_dict, v, len(v))))
    return params

def _copyXSLT(stylesheet):
    assert stylesheet._c_style, "XSLT stylesheet not initialised"
    new_xslt = XSLT.__new__(XSLT)
    new_xslt._access_control = stylesheet._access_control
    new_xslt._error_log = _ErrorLog()
    new_xslt._context = stylesheet._context._copy()

    new_xslt._xslt_resolver_context = stylesheet._xslt_resolver_context._copy()
    new_xslt._xslt_resolver_context._c_style_doc = _copyDoc(
        stylesheet._xslt_resolver_context._c_style_doc, 1)

    c_doc = _copyDoc(stylesheet._c_style.doc, 1)
    new_xslt._c_style = xslt.xsltParseStylesheetDoc(c_doc)
    if not new_xslt._c_style:
        tree.xmlFreeDoc(c_doc)
        raise MemoryError()

    return new_xslt

class _XSLTResultTree(_ElementTree):
    def _saveToStringAndSize(self):
        if self._context_node is not None:
            doc = self._context_node._doc
        else:
            doc = None
        if doc is None:
            doc = self._doc
            if doc is None:
                return None
        s_ptr = ffi.new("xmlChar**")
        l_ptr = ffi.new("int*")
        if 1:
            r = xslt.xsltSaveResultToString(s_ptr, l_ptr, doc._c_doc,
                                            self._xslt._c_style)
        if r == -1:
            raise MemoryError()
        try:
            return ffi.buffer(s_ptr[0], l_ptr[0])[:]
        finally:
            tree.xmlFree(s_ptr[0])

    def __str__(self):
        if python.IS_PYTHON3:
            return self.__unicode__()
        s = self._saveToStringAndSize()
        if not s:
            return ''
        return s

    def __unicode__(self):
        s = self._saveToStringAndSize()
        encoding = funicodeOrNone(self._xslt._c_style.encoding)
        if not encoding:
            result = s.decode('UTF-8')
        else:
            result = s.decode(encoding)
        return _stripEncodingDeclaration(result)

    @property
    def xslt_profile(self):
        u"""Return an ElementTree with profiling data for the stylesheet run.
        """
        if self._profile is None:
            return None
        root = self._profile.getroot()
        if root is None:
            return None
        return ElementTree(root)
    @xslt_profile.deleter
    def xslt_profile(self):
        self._profile = None

def _xsltResultTreeFactory(doc, xslt, profile):
    result = _newElementTree(doc, None, _XSLTResultTree)
    result._xslt = xslt
    result._profile = profile
    return result

# functions like "output" and "write" are a potential security risk, but we
# rely on the user to configure XSLTAccessControl as needed
xslt.xsltRegisterAllExtras()

# enable EXSLT support for XSLT
xslt.exsltRegisterAll()


################################################################################
# XSLT PI support

_RE_PI_HREF = re.compile(ur'\s+href\s*=\s*(?:\'([^\']*)\'|"([^"]*)")')
_FIND_PI_HREF = _RE_PI_HREF.findall
_REPLACE_PI_HREF = _RE_PI_HREF.sub
__findStylesheetByID = None

def _findStylesheetByID(doc, id):
    from .xpath import XPath
    global __findStylesheetByID
    if __findStylesheetByID is None:
        __findStylesheetByID = XPath(
            u"//xsl:stylesheet[@xml:id = $id]",
            namespaces={u"xsl" : u"http://www.w3.org/1999/XSL/Transform"})
    return __findStylesheetByID(doc, id=id)

class _XSLTProcessingInstruction(PIBase):
    def parseXSL(self, parser=None):
        u"""parseXSL(self, parser=None)

        Try to parse the stylesheet referenced by this PI and return
        an ElementTree for it.  If the stylesheet is embedded in the
        same document (referenced via xml:id), find and return an
        ElementTree for the stylesheet Element.

        The optional ``parser`` keyword argument can be passed to specify the
        parser used to read from external stylesheet URLs.
        """
        _assertValidNode(self)
        if not self._c_node.content:
            raise ValueError, u"PI lacks content"
        hrefs = _FIND_PI_HREF(u' ' + ffi.string(self._c_node.content).decode('UTF-8'))
        if len(hrefs) != 1:
            raise ValueError, u"malformed PI attributes"
        hrefs = hrefs[0]
        href_utf = _utf8(hrefs[0] or hrefs[1])
        c_href = href_utf

        if c_href[0] != '#':
            # normal URL, try to parse from it
            c_href = tree.xmlBuildURI(
                c_href,
                tree.xmlNodeGetBase(self._c_node.doc, self._c_node))
            if c_href:
                try:
                    result_doc = _parseDocumentFromURL(c_href, parser)
                finally:
                    tree.xmlFree(c_href)
            else:
                result_doc = _parseDocumentFromURL(href_utf, parser)
            return _elementTreeFactory(result_doc, None)

        # ID reference to embedded stylesheet
        # try XML:ID lookup
        _assertValidDoc(self._doc)
        c_href = c_href[1:]  # skip leading '#'
        c_attr = tree.xmlGetID(self._c_node.doc, c_href)
        if c_attr and c_attr.doc == self._c_node.doc:
            result_node = _elementFactory(self._doc, c_attr.parent)
            return _elementTreeFactory(result_node._doc, result_node)

        # try XPath search
        root = _findStylesheetByID(self._doc, c_href.decode('utf8'))
        if not root:
            raise ValueError, u"reference to non-existing embedded stylesheet"
        elif len(root) > 1:
            raise ValueError, u"ambiguous reference to embedded stylesheet"
        result_node = root[0]
        return _elementTreeFactory(result_node._doc, result_node)

    def set(self, key, value):
        u"""set(self, key, value)

        Supports setting the 'href' pseudo-attribute in the text of
        the processing instruction.
        """
        if key != u"href":
            raise AttributeError, \
                u"only setting the 'href' attribute is supported on XSLT-PIs"
        if value is None:
            attrib = u""
        elif u'"' in value or u'>' in value:
            raise ValueError, u"Invalid URL, must not contain '\"' or '>'"
        else:
            attrib = u' href="%s"' % value
        text = u' ' + self.text
        if _FIND_PI_HREF(text):
            self.text = _REPLACE_PI_HREF(attrib, text)
        else:
            self.text = text + attrib
