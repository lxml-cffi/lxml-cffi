# XPath evaluation

import threading
import re

from .xmlerror import _ErrorLog
from . import config
from .includes import tree, xmlerror
from .etree import _LIBXML_VERSION_INT, LxmlSyntaxError
from .extensions import _BaseContext, _xpath_function_call
from .extensions import XPathError, XPathEvalError
from .extensions import _wrapXPathObject, _unwrapXPathObject, _freeXPathObject
from .apihelpers import _utf8, _documentOrRaise, _rootNodeOrRaise
from .apihelpers import _assertValidNode, _assertValidDoc
from .xslt import LIBXSLT_VERSION
from .includes import xslt
from .includes import ffi, xpath
from .proxy import _fakeRootDoc, _destroyFakeDoc
from . import python

class XPathSyntaxError(LxmlSyntaxError, XPathError):
    pass

################################################################################
# XPath

_XPATH_SYNTAX_ERRORS = (
    xmlerror.XML_XPATH_NUMBER_ERROR,
    xmlerror.XML_XPATH_UNFINISHED_LITERAL_ERROR,
    xmlerror.XML_XPATH_VARIABLE_REF_ERROR,
    xmlerror.XML_XPATH_INVALID_PREDICATE_ERROR,
    xmlerror.XML_XPATH_UNCLOSED_ERROR,
    xmlerror.XML_XPATH_INVALID_CHAR_ERROR
)

_XPATH_EVAL_ERRORS = (
    xmlerror.XML_XPATH_UNDEF_VARIABLE_ERROR,
    xmlerror.XML_XPATH_UNDEF_PREFIX_ERROR,
    xmlerror.XML_XPATH_UNKNOWN_FUNC_ERROR,
    xmlerror.XML_XPATH_INVALID_OPERAND,
    xmlerror.XML_XPATH_INVALID_TYPE,
    xmlerror.XML_XPATH_INVALID_ARITY,
    xmlerror.XML_XPATH_INVALID_CTXT_SIZE,
    xmlerror.XML_XPATH_INVALID_CTXT_POSITION
)

def _register_xpath_function(ctxt, name_utf, ns_utf):
    if ns_utf is None:
        return xpath.xmlXPathRegisterFunc(
            ctxt, name_utf, _xpath_function_call)
    else:
        return xpath.xmlXPathRegisterFuncNS(
            ctxt, name_utf, ns_utf,_xpath_function_call)

def _unregister_xpath_function(ctxt, name_utf, ns_utf):
    if ns_utf is None:
        return xpath.xmlXPathRegisterFunc(
            ctxt, name_utf, ffi.NULL)
    else:
        return xpath.xmlXPathRegisterFuncNS(
            ctxt, name_utf, ns_utf, ffi.NULL)

@tree.ffi.callback("xmlHashScanner")
def _registerExsltFunctionsForNamespaces(_c_href, _ctxt, c_prefix):
    c_href = ffi.string(ffi.cast("const xmlChar*", _c_href))
    ctxt = ffi.cast("xmlXPathContextPtr", _ctxt)

    if tree.xmlStrcmp(c_href, xslt.EXSLT_DATE_NAMESPACE) == 0:
        xslt.exsltDateXpathCtxtRegister(ctxt, c_prefix)
    elif tree.xmlStrcmp(c_href, xslt.EXSLT_SETS_NAMESPACE) == 0:
        xslt.exsltSetsXpathCtxtRegister(ctxt, c_prefix)
    elif tree.xmlStrcmp(c_href, xslt.EXSLT_MATH_NAMESPACE) == 0:
        xslt.exsltMathXpathCtxtRegister(ctxt, c_prefix)
    elif tree.xmlStrcmp(c_href, xslt.EXSLT_STRINGS_NAMESPACE) == 0:
        xslt.exsltStrXpathCtxtRegister(ctxt, c_prefix)

if _LIBXML_VERSION_INT == 20627:
    _XPATH_VERSION_WARNING_REQUIRED = 1
else:
    _XPATH_VERSION_WARNING_REQUIRED = 0

class _XPathContext(_BaseContext):
    def __init__(self, namespaces, extensions, error_log, enable_regexp, variables,
                 build_smart_strings):
        self._variables = variables
        _BaseContext.__init__(self, namespaces, extensions, error_log, enable_regexp,
                              build_smart_strings)

    def set_context(self, xpathCtxt):
        self._set_xpath_context(xpathCtxt)
        # This would be a good place to set up the XPath parser dict, but
        # we cannot use the current thread dict as we do not know which
        # thread will execute the XPath evaluator - so, no dict for now.
        self.registerLocalNamespaces()
        self.registerLocalFunctions(xpathCtxt, _register_xpath_function)

    def register_context(self, doc):
        self._register_context(doc)
        self.registerGlobalNamespaces()
        self.registerGlobalFunctions(self._xpathCtxt, _register_xpath_function)
        self.registerExsltFunctions()
        if self._variables is not None:
            self.registerVariables(self._variables)

    def unregister_context(self):
        self.unregisterGlobalFunctions(
            self._xpathCtxt, _unregister_xpath_function)
        self.unregisterGlobalNamespaces()
        xpath.xmlXPathRegisteredVariablesCleanup(self._xpathCtxt)
        self._cleanup_context()

    def registerExsltFunctions(self):
        if LIBXSLT_VERSION < 10125:
            # we'd only execute dummy functions anyway
            return
        tree.xmlHashScan(
            self._xpathCtxt.nsHash,
            _registerExsltFunctionsForNamespaces,
            self._xpathCtxt)

    def registerVariables(self, variable_dict):
        for name, value in variable_dict.items():
            name_utf = self._to_utf(name)
            xpath.xmlXPathRegisterVariable(
                self._xpathCtxt, name_utf, _wrapXPathObject(value, None, None))


class _XPathEvaluatorBase(object):
    _xpathCtxt = ffi.NULL

    def __init__(self, namespaces, extensions, enable_regexp,
                 smart_strings):
        if config.ENABLE_THREADING:
            self._eval_lock = threading.Lock()
        self._error_log = _ErrorLog()

        global _XPATH_VERSION_WARNING_REQUIRED
        if _XPATH_VERSION_WARNING_REQUIRED:
            _XPATH_VERSION_WARNING_REQUIRED = 0
            import warnings
            warnings.warn(u"This version of libxml2 has a known XPath bug. "
                          u"Use it at your own risk.")
        self._context = _XPathContext(namespaces, extensions, self._error_log,
                                      enable_regexp, None,
                                      smart_strings)

    def __del__(self):
        if self._xpathCtxt:
            xpath.xmlXPathFreeContext(self._xpathCtxt)

    def set_context(self, xpathCtxt):
        self._xpathCtxt = xpathCtxt
        self._context.set_context(xpathCtxt)

    def _lock(self):
        if config.ENABLE_THREADING and self._eval_lock:
            self._eval_lock.acquire()
        return 0

    def _unlock(self):
        if config.ENABLE_THREADING and self._eval_lock:
            self._eval_lock.release()

    def _raise_parse_error(self):
        entries = self._error_log.filter_types(_XPATH_SYNTAX_ERRORS)
        if entries:
            message = entries._buildExceptionMessage(None)
            if message is not None:
                raise XPathSyntaxError(message, self._error_log)
        raise XPathSyntaxError(self._error_log._buildExceptionMessage(
                u"Error in xpath expression"),
                               self._error_log)

    def _raise_eval_error(self):
        entries = self._error_log.filter_types(_XPATH_EVAL_ERRORS)
        if not entries:
            entries = self._error_log.filter_types(_XPATH_SYNTAX_ERRORS)
        if entries:
            message = entries._buildExceptionMessage(None)
            if message is not None:
                raise XPathEvalError(message, self._error_log)
        raise XPathEvalError(self._error_log._buildExceptionMessage(
                u"Error in xpath expression"),
                             self._error_log)

    def _handle_result(self, xpathObj, doc):
        if self._context._exc._has_raised():
            if xpathObj:
                _freeXPathObject(xpathObj)
                xpathObj = NULL
            self._context._release_temp_refs()
            self._context._exc._raise_if_stored()

        if not xpathObj:
            self._context._release_temp_refs()
            self._raise_eval_error()

        try:
            result = _unwrapXPathObject(xpathObj, doc, self._context)
        finally:
            _freeXPathObject(xpathObj)
            self._context._release_temp_refs()

        return result

class XPathElementEvaluator(_XPathEvaluatorBase):
    u"""XPathElementEvaluator(self, element, namespaces=None, extensions=None, regexp=True, smart_strings=True)
    Create an XPath evaluator for an element.

    Absolute XPath expressions (starting with '/') will be evaluated against
    the ElementTree as returned by getroottree().

    Additional namespace declarations can be passed with the
    'namespace' keyword argument.  EXSLT regular expression support
    can be disabled with the 'regexp' boolean keyword (defaults to
    True).  Smart strings will be returned for string results unless
    you pass ``smart_strings=False``.
    """
    def __init__(self, element, namespaces=None,
                 extensions=None, regexp=True, smart_strings=True):
        _assertValidNode(element)
        _assertValidDoc(element._doc)
        self._element = element
        doc = element._doc
        _XPathEvaluatorBase.__init__(self, namespaces, extensions,
                                     regexp, smart_strings)
        xpathCtxt = xpath.xmlXPathNewContext(doc._c_doc)
        if not xpathCtxt:
            raise MemoryError()
        self.set_context(xpathCtxt)

    def __call__(self, _path, **_variables):
        u"""__call__(self, _path, **_variables)

        Evaluate an XPath expression on the document.

        Variables may be provided as keyword arguments.  Note that namespaces
        are currently not supported for variables.

        Absolute XPath expressions (starting with '/') will be evaluated
        against the ElementTree as returned by getroottree().
        """
        assert self._xpathCtxt, "XPath context not initialised"
        path = _utf8(_path)
        doc = self._element._doc

        self._lock()
        self._xpathCtxt.node = self._element._c_node
        try:
            self._context.register_context(doc)
            self._context.registerVariables(_variables)
            c_path = path
            if 1:
                xpathObj = xpath.xmlXPathEvalExpression(
                    c_path, self._xpathCtxt)
            result = self._handle_result(xpathObj, doc)
        finally:
            self._context.unregister_context()
            self._unlock()

        return result


class XPathDocumentEvaluator(XPathElementEvaluator):
    u"""XPathDocumentEvaluator(self, etree, namespaces=None, extensions=None, regexp=True, smart_strings=True)
    Create an XPath evaluator for an ElementTree.

    Additional namespace declarations can be passed with the
    'namespace' keyword argument.  EXSLT regular expression support
    can be disabled with the 'regexp' boolean keyword (defaults to
    True).  Smart strings will be returned for string results unless
    you pass ``smart_strings=False``.
    """
    def __init__(self, etree, namespaces=None,
                 extensions=None, regexp=True, smart_strings=True):
        XPathElementEvaluator.__init__(
            self, etree._context_node, namespaces=namespaces,
            extensions=extensions, regexp=regexp,
            smart_strings=smart_strings)

    def register_namespace(self, prefix, uri):
        u"""Register a namespace with the XPath context.
        """
        assert self._xpathCtxt, "XPath context not initialised"
        self._context.addNamespace(prefix, uri)

    def register_namespaces(self, namespaces):
        u"""Register a prefix -> uri dict.
        """
        assert self._xpathCtxt, "XPath context not initialised"
        for prefix, uri in namespaces.items():
            self._context.addNamespace(prefix, uri)

    def __call__(self, _path, **_variables):
        u"""__call__(self, _path, **_variables)

        Evaluate an XPath expression on the document.

        Variables may be provided as keyword arguments.  Note that namespaces
        are currently not supported for variables.
        """
        assert self._xpathCtxt, "XPath context not initialised"
        path = _utf8(_path)
        doc = self._element._doc

        self._lock()
        try:
            self._context.register_context(doc)
            c_doc = _fakeRootDoc(doc._c_doc, self._element._c_node)
            try:
                self._context.registerVariables(_variables)
                c_path = path
                if 1:
                    self._xpathCtxt.doc  = c_doc
                    self._xpathCtxt.node = tree.xmlDocGetRootElement(c_doc)
                    xpathObj = xpath.xmlXPathEvalExpression(
                        c_path, self._xpathCtxt)
                result = self._handle_result(xpathObj, doc)
            finally:
                _destroyFakeDoc(doc._c_doc, c_doc)
                self._context.unregister_context()
        finally:
            self._unlock()

        return result


def XPathEvaluator(etree_or_element, namespaces=None, extensions=None,
                   regexp=True, smart_strings=True):
    u"""XPathEvaluator(etree_or_element, namespaces=None, extensions=None, regexp=True, smart_strings=True)

    Creates an XPath evaluator for an ElementTree or an Element.

    The resulting object can be called with an XPath expression as argument
    and XPath variables provided as keyword arguments.

    Additional namespace declarations can be passed with the
    'namespace' keyword argument.  EXSLT regular expression support
    can be disabled with the 'regexp' boolean keyword (defaults to
    True).  Smart strings will be returned for string results unless
    you pass ``smart_strings=False``.
    """
    from .etree import _ElementTree
    if isinstance(etree_or_element, _ElementTree):
        return XPathDocumentEvaluator(
            etree_or_element, namespaces=namespaces,
            extensions=extensions, regexp=regexp, smart_strings=smart_strings)
    else:
        return XPathElementEvaluator(
            etree_or_element, namespaces=namespaces,
            extensions=extensions, regexp=regexp, smart_strings=smart_strings)


class XPath(_XPathEvaluatorBase):
    u"""XPath(self, path, namespaces=None, extensions=None, regexp=True, smart_strings=True)
    A compiled XPath expression that can be called on Elements and ElementTrees.

    Besides the XPath expression, you can pass prefix-namespace
    mappings and extension functions to the constructor through the
    keyword arguments ``namespaces`` and ``extensions``.  EXSLT
    regular expression support can be disabled with the 'regexp'
    boolean keyword (defaults to True).  Smart strings will be
    returned for string results unless you pass
    ``smart_strings=False``.
    """

    _xpath = ffi.NULL

    def __init__(self, path, namespaces=None, extensions=None,
                 regexp=True, smart_strings=True):
        _XPathEvaluatorBase.__init__(self, namespaces, extensions,
                                     regexp, smart_strings)
        self._path = _utf8(path)
        xpathCtxt = xpath.xmlXPathNewContext(ffi.NULL)
        if not xpathCtxt:
            python.PyErr_NoMemory()
        self.set_context(xpathCtxt)
        self._xpath = xpath.xmlXPathCtxtCompile(xpathCtxt, self._path)
        if not self._xpath:
            self._raise_parse_error()

    def __call__(self, _etree_or_element, **_variables):
        u"__call__(self, _etree_or_element, **_variables)"
        assert self._xpathCtxt, "XPath context not initialised"
        document = _documentOrRaise(_etree_or_element)
        element  = _rootNodeOrRaise(_etree_or_element)

        self._lock()
        self._xpathCtxt.doc  = document._c_doc
        self._xpathCtxt.node = element._c_node

        try:
            self._context.register_context(document)
            self._context.registerVariables(_variables)
            xpathObj = xpath.xmlXPathCompiledEval(
                self._xpath, self._xpathCtxt)
            result = self._handle_result(xpathObj, document)
        finally:
            self._context.unregister_context()
            self._unlock()
        return result

    @property
    def path(self):
        u"""The literal XPath expression.
        """
        return self._path.decode(u'UTF-8')

    def __del__(self):
        if self._xpath:
            xpath.xmlXPathFreeCompExpr(self._xpath)

    def __repr__(self):
        return self.path

_replace_strings = re.compile(b'("[^"]*")|(\'[^\']*\')').sub
_find_namespaces = re.compile(b'({[^}]+})').findall

class ETXPath(XPath):
    u"""ETXPath(self, path, extensions=None, regexp=True, smart_strings=True)
    Special XPath class that supports the ElementTree {uri} notation for namespaces.

    Note that this class does not accept the ``namespace`` keyword
    argument. All namespaces must be passed as part of the path
    string.  Smart strings will be returned for string results unless
    you pass ``smart_strings=False``.
    """
    def __init__(self, path, extensions=None, regexp=True,
                 smart_strings=True):
        path, namespaces = self._nsextract_path(path)
        XPath.__init__(self, path, namespaces=namespaces,
                       extensions=extensions, regexp=regexp,
                       smart_strings=smart_strings)

    def _nsextract_path(self, path):
        # replace {namespaces} by new prefixes
        namespaces = {}
        namespace_defs = []
        path_utf = _utf8(path)
        stripped_path = _replace_strings(b'', path_utf) # remove string literals
        i = 1
        for namespace_def in _find_namespaces(stripped_path):
            if namespace_def not in namespace_defs:
                prefix = python.PyBytes_FromFormat("__xpp%02d", i)
                i += 1
                namespace_defs.append(namespace_def)
                namespace = namespace_def[1:-1] # remove '{}'
                namespace = namespace.decode('utf8')
                namespaces[prefix.decode('utf8')] = namespace
                prefix_str = prefix + b':'
                # FIXME: this also replaces {namespaces} within strings!
                path_utf = path_utf.replace(namespace_def, prefix_str)
        path = path_utf.decode('utf8')
        return path, namespaces

