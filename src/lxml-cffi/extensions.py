import re

from .etree import _ExceptionContext, LxmlError
from .includes.etree_defs import _isElement
from . import python
from .apihelpers import funicode, funicodeOrNone, _isString, _namespacedName
from .apihelpers import _previousElement, _makeElement, _utf8
from ._libxml2 import ffi, lib
xpath = tree = xmlerror = lib

# support for extension functions in XPath and XSLT

class XPathError(LxmlError):
    u"""Base class of all XPath errors.
    """
    pass

class XPathEvalError(XPathError):
    u"""Error during XPath evaluation.
    """
    pass

class XPathFunctionError(XPathEvalError):
    u"""Internal error looking up an XPath extension function.
    """
    pass

class XPathResultError(XPathEvalError):
    u"""Error handling an XPath result.
    """
    pass

################################################################################
# Base class for XSLT and XPath evaluation contexts: functions, namespaces, ...

class _BaseContext(object):
    def __init__(self, namespaces, extensions, error_log, enable_regexp,
                 build_smart_strings):
        self._xpathCtxt = ffi.NULL
        self._utf_refs = {}
        self._global_namespaces = []
        self._function_cache = {}
        self._eval_context_dict = None
        self._error_log = error_log

        if extensions is not None:
            # convert extensions to UTF-8
            if isinstance(extensions, dict):
                extensions = (extensions,)
            # format: [ {(ns, name):function} ] -> {(ns_utf, name_utf):function}
            new_extensions = {}
            for extension in extensions:
                for (ns_uri, name), function in extension.items():
                    if name is None:
                        raise ValueError, u"extensions must have non empty names"
                    ns_utf   = self._to_utf(ns_uri)
                    name_utf = self._to_utf(name)
                    new_extensions[(ns_utf, name_utf)] = function
            extensions = new_extensions or None

        if namespaces is not None:
            if isinstance(namespaces, dict):
                namespaces = namespaces.items()
            if namespaces:
                ns = []
                for prefix, ns_uri in namespaces:
                    if prefix is None or not prefix:
                        raise TypeError, \
                            u"empty namespace prefix is not supported in XPath"
                    if ns_uri is None or not ns_uri:
                        raise TypeError, \
                            u"setting default namespace is not supported in XPath"
                    prefix_utf = self._to_utf(prefix)
                    ns_uri_utf = self._to_utf(ns_uri)
                    ns.append( (prefix_utf, ns_uri_utf) )
                namespaces = ns
            else:
                namespaces = None

        self._doc        = None
        self._exc        = _ExceptionContext()
        self._extensions = extensions
        self._namespaces = namespaces
        self._temp_documents  = set()
        self._build_smart_strings = build_smart_strings

        if enable_regexp:
            _regexp = _ExsltRegExp()
            _regexp._register_in_context(self)

    def _copy(self):
        if self._namespaces is not None:
            namespaces = self._namespaces[:]
        else:
            namespaces = None
        context = self.__class__(namespaces, None, self._error_log, False,
                                 self._build_smart_strings)
        if self._extensions is not None:
            context._extensions = self._extensions.copy()
        return context

    def _to_utf(self, s):
        u"Convert to UTF-8 and keep a reference to the encoded string"
        if s is None:
            return None
        return s.encode('utf-8')

    def _set_xpath_context(self, xpathCtxt):
        from . import xpath
        self._xpathCtxt = xpathCtxt
        handle = ffi.new_handle(self)
        self._keepalive = handle
        xpathCtxt.userData = handle
        xpathCtxt.error = _receiveXPathError

    def _register_context(self, doc):
        self._doc = doc
        self._exc.clear()

    def _cleanup_context(self):
        #xpath.xmlXPathRegisteredNsCleanup(self._xpathCtxt)
        #self.unregisterGlobalNamespaces()
        self._utf_refs.clear()
        self._eval_context_dict = None
        self._doc = None

    def _release_context(self):
        if self._xpathCtxt:
            self._xpathCtxt.userData = ffi.NULL
            self._xpathCtxt = ffi.NULL

    # namespaces (internal UTF-8 methods with leading '_')

    def addNamespace(self, prefix, ns_uri):
        if prefix is None:
            raise TypeError, u"empty prefix is not supported in XPath"
        prefix_utf = self._to_utf(prefix)
        ns_uri_utf = self._to_utf(ns_uri)
        new_item = (prefix_utf, ns_uri_utf)
        if self._namespaces is None:
            self._namespaces = [new_item]
        else:
            namespaces = []
            for item in self._namespaces:
                if item[0] == prefix_utf:
                    item = new_item
                    new_item = None
                namespaces.append(item)
            if new_item is not None:
                namespaces.append(new_item)
            self._namespaces = namespaces
        if self._xpathCtxt:
            xpath.xmlXPathRegisterNs(
                self._xpathCtxt, prefix_utf, ns_uri_utf)

    def registerLocalNamespaces(self):
        if self._namespaces is None:
            return
        for prefix_utf, ns_uri_utf in self._namespaces:
            xpath.xmlXPathRegisterNs(
                self._xpathCtxt, prefix_utf, ns_uri_utf)

    def registerGlobalNamespaces(self):
        from .nsclasses import _find_all_extension_prefixes
        ns_prefixes = _find_all_extension_prefixes()
        for prefix_utf, ns_uri_utf in ns_prefixes:
            self._global_namespaces.append(prefix_utf)
            xpath.xmlXPathRegisterNs(
                self._xpathCtxt, prefix_utf, ns_uri_utf)

    def unregisterGlobalNamespaces(self):
        if self._global_namespaces:
            for prefix_utf in self._global_namespaces:
                xpath.xmlXPathRegisterNs(self._xpathCtxt,
                                         prefix_utf, ffi.NULL)
            del self._global_namespaces[:]

    # extension functions

    def _addLocalExtensionFunction(self, ns_utf, name_utf, function):
        if self._extensions is None:
            self._extensions = {}
        self._extensions[(ns_utf, name_utf)] = function

    def registerGlobalFunctions(self, ctxt, reg_func):
        from .nsclasses import _FUNCTION_NAMESPACE_REGISTRIES
        for ns_utf, ns_functions in _FUNCTION_NAMESPACE_REGISTRIES.iteritems():
            if ns_utf in self._function_cache:
                d = self._function_cache[ns_utf]
            else:
                d = {}
                self._function_cache[ns_utf] = d
            for name_utf, function in ns_functions.iteritems():
                d[name_utf] = function
                reg_func(ctxt, name_utf, ns_utf)

    def registerLocalFunctions(self, ctxt, reg_func):
        if self._extensions is None:
            return # done
        last_ns = None
        d = None
        for (ns_utf, name_utf), function in self._extensions.iteritems():
            if ns_utf is not last_ns or d is None:
                last_ns = ns_utf
                try:
                    dict_result = python.PyDict_GetItem(
                        self._function_cache, ns_utf)
                except KeyError:
                    d = {}
                    self._function_cache[ns_utf] = d
                else:
                    d = dict_result
            d[name_utf] = function
            reg_func(ctxt, name_utf, ns_utf)

    def unregisterGlobalFunctions(self, ctxt, unreg_func):
        for ns_utf, functions in self._function_cache.items():
            for name_utf in functions:
                if self._extensions is None or \
                       (ns_utf, name_utf) not in self._extensions:
                    unreg_func(ctxt, name_utf, ns_utf)

    def _find_cached_function(self, c_ns_uri, c_name):
        u"""Lookup an extension function in the cache and return it.

        Parameters: c_ns_uri may be NULL, c_name must not be NULL
        """
        c_dict = self._function_cache.get(c_ns_uri)
        if c_dict:
            return c_dict.get(c_name, None)
        return None

    # Python access to the XPath context for extension functions

    @property
    def context_node(self):
        from .etree import _elementFactory
        if not self._xpathCtxt:
            raise XPathError, \
                u"XPath context is only usable during the evaluation"
        c_node = self._xpathCtxt.node
        if not c_node:
            raise XPathError, u"no context node"
        if c_node.doc != self._xpathCtxt.doc:
            raise XPathError, \
                u"document-external context nodes are not supported"
        if self._doc is None:
            raise XPathError, u"document context is missing"
        return _elementFactory(self._doc, c_node)

    @property
    def eval_context(self):
        if self._eval_context_dict is None:
            self._eval_context_dict = {}
        return self._eval_context_dict

    # Python reference keeping during XPath function evaluation

    def _release_temp_refs(self):
        u"Free temporarily referenced objects from this context."
        self._temp_documents.clear()

    def _hold(self, obj):
        u"""A way to temporarily hold references to nodes in the evaluator.

        This is needed because otherwise nodes created in XPath extension
        functions would be reference counted too soon, during the XPath
        evaluation.  This is most important in the case of exceptions.
        """
        from .etree import _Element
        if isinstance(obj, _Element):
            self._temp_documents.add(obj._doc)
            return
        elif _isString(obj) or not python.PySequence_Check(obj):
            return
        for o in obj:
            if isinstance(o, _Element):
                #print "Holding document:", <int>element._doc._c_doc
                self._temp_documents.add(o._doc)

    def _findDocumentForNode(self, c_node):
        u"""If an XPath expression returns an element from a different
        document than the current context document, we call this to
        see if it was possibly created by an extension and is a known
        document instance.
        """
        for doc in self._temp_documents:
            if doc is not None and doc._c_doc == c_node.doc:
                return doc
        return None


# libxml2 keeps these error messages in a static array in its code
# and doesn't give us access to them ...

LIBXML2_XPATH_ERROR_MESSAGES = [
    b"Ok",
    b"Number encoding",
    b"Unfinished literal",
    b"Start of literal",
    b"Expected $ for variable reference",
    b"Undefined variable",
    b"Invalid predicate",
    b"Invalid expression",
    b"Missing closing curly brace",
    b"Unregistered function",
    b"Invalid operand",
    b"Invalid type",
    b"Invalid number of arguments",
    b"Invalid context size",
    b"Invalid context position",
    b"Memory allocation error",
    b"Syntax error",
    b"Resource error",
    b"Sub resource error",
    b"Undefined namespace prefix",
    b"Encoding error",
    b"Char out of XML range",
    b"Invalid or incomplete context",
    b"Stack usage error",
    ]

def _forwardXPathError(c_ctxt, c_error):
    error = ffi.new("xmlError*")
    if c_error.message:
        error.message = c_error.message
    else:
        xpath_code = c_error.code - xmlerror.XML_XPATH_EXPRESSION_OK
        if 0 <= xpath_code < len(LIBXML2_XPATH_ERROR_MESSAGES):
            message = LIBXML2_XPATH_ERROR_MESSAGES[xpath_code]
        else:
            message = b"unknown error"
        # This message should be kept alive until after the call to _receive().
        message = ffi.new("char[]", message)
        error.message = message
    error.domain = c_error.domain
    error.code = c_error.code
    error.level = c_error.level
    error.line = c_error.line
    error.int2 = c_error.int1 # column
    error.file = c_error.file

    ctxt = ffi.from_handle(c_ctxt)
    ctxt._error_log._receive(error)

@ffi.callback("xmlStructuredErrorFunc")
def _receiveXPathError(c_context, error):
    if not c_context:
        _forwardError(ffi.NULL, error)
    else:
        _forwardXPathError(c_context, error)

def Extension(module, function_mapping=None, ns=None):
    u"""Extension(module, function_mapping=None, ns=None)

    Build a dictionary of extension functions from the functions
    defined in a module or the methods of an object.

    As second argument, you can pass an additional mapping of
    attribute names to XPath function names, or a list of function
    names that should be taken.

    The ``ns`` keyword argument accepts a namespace URI for the XPath
    functions.
    """
    functions = {}
    if isinstance(function_mapping, dict):
        for function_name, xpath_name in function_mapping.items():
            functions[(ns, xpath_name)] = getattr(module, function_name)
    else:
        if function_mapping is None:
            function_mapping = [ name for name in dir(module)
                                 if not name.startswith(u'_') ]
        for function_name in function_mapping:
            functions[(ns, function_name)] = getattr(module, function_name)
    return functions

################################################################################
# EXSLT regexp implementation

class _ExsltRegExp(object):
    def __init__(self):
        self._compile_map = {}

    def _make_string(self, value):
        from .etree import _Element
        if _isString(value):
            return value
        elif isinstance(value, list):
            # node set: take recursive text concatenation of first element
            if not value:
                return u''
            firstnode = value[0]
            if _isString(firstnode):
                return firstnode
            elif isinstance(firstnode, _Element):
                c_text = tree.xmlNodeGetContent(firstnode._c_node)
                if not c_text:
                    raise MemoryError()
                try:
                    return funicode(c_text)
                finally:
                    tree.xmlFree(c_text)
            else:
                return unicode(firstnode)
        else:
            return unicode(value)

    def _compile(self, rexp, ignore_case):
        rexp = self._make_string(rexp)
        key = (rexp, ignore_case)
        try:
            return self._compile_map[key]
        except KeyError:
            pass
        py_flags = re.UNICODE
        if ignore_case:
            py_flags = py_flags | re.IGNORECASE
        rexp_compiled = re.compile(rexp, py_flags)
        self._compile_map[key] = rexp_compiled
        return rexp_compiled

    def test(self, ctxt, s, rexp, flags=u''):
        flags = self._make_string(flags)
        s = self._make_string(s)
        rexpc = self._compile(rexp, u'i' in flags)
        if rexpc.search(s) is None:
            return False
        else:
            return True

    def match(self, ctxt, s, rexp, flags=u''):
        from .etree import Element, SubElement
        flags = self._make_string(flags)
        s = self._make_string(s)
        rexpc = self._compile(rexp, u'i' in flags)
        if u'g' in flags:
            results = rexpc.findall(s)
            if not results:
                return ()
        else:
            result = rexpc.search(s)
            if not result:
                return ()
            results = [ result.group() ]
            results.extend( result.groups(u'') )
        result_list = []
        root = Element(u'matches')
        join_groups = u''.join
        for s_match in results:
            if isinstance(s_match, tuple):
                s_match = join_groups(s_match)
            elem = SubElement(root, u'match')
            elem.text = s_match
            result_list.append(elem)
        return result_list

    def replace(self, ctxt, s, rexp, flags, replacement):
        replacement = self._make_string(replacement)
        flags = self._make_string(flags)
        s = self._make_string(s)
        rexpc = self._compile(rexp, u'i' in flags)
        if u'g' in flags:
            count = 0
        else:
            count = 1
        return rexpc.sub(replacement, s, count)

    def _register_in_context(self, context):
        ns = b"http://exslt.org/regular-expressions"
        context._addLocalExtensionFunction(ns, b"test",    self.test)
        context._addLocalExtensionFunction(ns, b"match",   self.match)
        context._addLocalExtensionFunction(ns, b"replace", self.replace)


################################################################################
# helper functions

def _wrapXPathObject(obj, doc, context):
    from .etree import _Element
    fake_node = None

    if isinstance(obj, unicode):
        obj = _utf8(obj)
    if isinstance(obj, bytes):
        # libxml2 copies the string value
        return xpath.xmlXPathNewCString(obj)
    if isinstance(obj, bool):
        return xpath.xmlXPathNewBoolean(obj)
    if python.PyNumber_Check(obj):
        return xpath.xmlXPathNewFloat(obj)
    if obj is None:
        resultSet = xpath.xmlXPathNodeSetCreate(ffi.NULL)
    elif isinstance(obj, _Element):
        resultSet = xpath.xmlXPathNodeSetCreate(obj._c_node)
    elif python.PySequence_Check(obj):
        resultSet = xpath.xmlXPathNodeSetCreate(ffi.NULL)
        try:
            for value in obj:
                if isinstance(value, _Element):
                    if context is not None:
                        context._hold(value)
                    xpath.xmlXPathNodeSetAdd(resultSet, value._c_node)
                else:
                    if context is None or doc is None:
                        raise XPathResultError, \
                              u"Non-Element values not supported at this point - got %r" % value
                    # support strings by appending text nodes to an Element
                    if isinstance(value, unicode):
                        value = _utf8(value)
                    if isinstance(value, bytes):
                        if fake_node is None:
                            fake_node = _makeElement("text-root", ffi.NULL, doc, None,
                                                     None, None, None, None, None)
                            context._hold(fake_node)
                        else:
                            # append a comment node to keep the text nodes separate
                            c_node = tree.xmlNewDocComment(doc._c_doc, "")
                            if not c_node:
                                raise MemoryError()
                            tree.xmlAddChild(fake_node._c_node, c_node)
                        context._hold(value)
                        c_node = tree.xmlNewDocText(doc._c_doc, value)
                        if not c_node:
                            raise MemoryError()
                        tree.xmlAddChild(fake_node._c_node, c_node)
                        xpath.xmlXPathNodeSetAdd(resultSet, c_node)
                    else:
                        raise XPathResultError, \
                              u"This is not a supported node-set result: %r" % value
        except:
            xpath.xmlXPathFreeNodeSet(resultSet)
            raise
    else:
        raise XPathResultError, u"Unknown return type: %s" % \
            python._fqtypename(obj)
    return xpath.xmlXPathWrapNodeSet(resultSet)

def _unwrapXPathObject(xpathObj, doc, context):
    if xpathObj.type == xpath.XPATH_UNDEFINED:
        raise XPathResultError, u"Undefined xpath result"
    elif xpathObj.type == xpath.XPATH_NODESET:
        return _createNodeSetResult(xpathObj, doc, context)
    elif xpathObj.type == xpath.XPATH_BOOLEAN:
        return bool(xpathObj.boolval)
    elif xpathObj.type == xpath.XPATH_NUMBER:
        return xpathObj.floatval
    elif xpathObj.type == xpath.XPATH_STRING:
        stringval = funicode(xpathObj.stringval)
        if context._build_smart_strings:
            stringval = _elementStringResultFactory(
                stringval, None, None, 0)
        return stringval
    elif xpathObj.type == xpath.XPATH_POINT:
        raise NotImplementedError, u"XPATH_POINT"
    elif xpathObj.type == xpath.XPATH_RANGE:
        raise NotImplementedError, u"XPATH_RANGE"
    elif xpathObj.type == xpath.XPATH_LOCATIONSET:
        raise NotImplementedError, u"XPATH_LOCATIONSET"
    elif xpathObj.type == xpath.XPATH_USERS:
        raise NotImplementedError, u"XPATH_USERS"
    elif xpathObj.type == xpath.XPATH_XSLT_TREE:
        return _createNodeSetResult(xpathObj, doc, context)
    else:
        raise XPathResultError, u"Unknown xpath result %s" % unicode(xpathObj.type)

def _createNodeSetResult(xpathObj, doc, context):
    result = []
    if not xpathObj.nodesetval:
        return result
    for i in range(xpathObj.nodesetval.nodeNr):
        c_node = xpathObj.nodesetval.nodeTab[i]
        _unpackNodeSetEntry(result, c_node, doc, context,
                            xpathObj.type == xpath.XPATH_XSLT_TREE)
    return result

def _unpackNodeSetEntry(results, c_node, doc,
                        context, is_fragment):
    from .proxy import _fakeDocElementFactory
    if _isElement(c_node):
        if c_node.doc != doc._c_doc and not c_node.doc._private:
            # XXX: works, but maybe not always the right thing to do?
            # XPath: only runs when extensions create or copy trees
            #        -> we store Python refs to these, so that is OK
            # XSLT: can it leak when merging trees from multiple sources?
            c_node = tree.xmlDocCopyNode(c_node, doc._c_doc, 1)
            # FIXME: call _instantiateElementFromXPath() instead?
        results.append(
            _fakeDocElementFactory(doc, c_node))
    elif c_node.type == tree.XML_TEXT_NODE or \
             c_node.type == tree.XML_CDATA_SECTION_NODE or \
             c_node.type == tree.XML_ATTRIBUTE_NODE:
        results.append(
            _buildElementStringResult(doc, c_node, context))
    elif c_node.type == tree.XML_NAMESPACE_DECL:
        c_ns = ffi.cast("xmlNsPtr", c_node)
        results.append( (funicodeOrNone(c_ns.prefix),
                         funicodeOrNone(c_ns.href)) )
    elif c_node.type == tree.XML_DOCUMENT_NODE or \
            c_node.type == tree.XML_HTML_DOCUMENT_NODE:
        # ignored for everything but result tree fragments
        if is_fragment:
            c_child = c_node.children
            while c_child:
                _unpackNodeSetEntry(results, c_child, doc, context, 0)
                c_child = c_child.next
    elif c_node.type == tree.XML_XINCLUDE_START or \
            c_node.type == tree.XML_XINCLUDE_END:
        pass
    else:
        raise NotImplementedError, \
            u"Not yet implemented result node type: %d" % c_node.type

def _freeXPathObject(xpathObj):
    u"""Free the XPath object, but *never* free the *content* of node sets.
    Python dealloc will do that for us.
    """
    if xpathObj.nodesetval:
        xpath.xmlXPathFreeNodeSet(xpathObj.nodesetval)
        xpathObj.nodesetval = ffi.NULL
    xpath.xmlXPathFreeObject(xpathObj)

def _instantiateElementFromXPath(c_node, doc, context):
    from .proxy import _fakeDocElementFactory
    # NOTE: this may copy the element - only call this when it can't leak
    if c_node.doc != doc._c_doc and not c_node.doc._private:
        # not from the context document and not from a fake document
        # either => may still be from a known document, e.g. one
        # created by an extension function
        node_doc = context._findDocumentForNode(c_node)
        if node_doc is None:
            # not from a known document at all! => can only make a
            # safety copy here
            c_node = tree.xmlDocCopyNode(c_node, doc._c_doc, 1)
        else:
            doc = node_doc
    return _fakeDocElementFactory(doc, c_node)

################################################################################
# special str/unicode subclasses

class _ElementUnicodeResult(unicode):
    def getparent(self):
        return self._parent

class _ElementStringResult(bytes):
    def getparent(self):
        return self._parent

def _elementStringResultFactory(string_value, parent,
                                attrname, is_tail):
    is_attribute = attrname is not None
    if parent is None:
        is_text = 0
    else:
        is_text = not (is_tail or is_attribute)

    if type(string_value) is bytes:
        result = _ElementStringResult(string_value)
        result._parent = parent
        result.is_attribute = is_attribute
        result.is_tail = is_tail
        result.is_text = is_text
        result.attrname = attrname
        return result
    else:
        uresult = _ElementUnicodeResult(string_value)
        uresult._parent = parent
        uresult.is_attribute = is_attribute
        uresult.is_tail = is_tail
        uresult.is_text = is_text
        uresult.attrname = attrname
        return uresult

def _buildElementStringResult(doc, c_node, context):
    parent = None
    attrname = None

    if c_node.type == tree.XML_ATTRIBUTE_NODE:
        attrname = _namespacedName(c_node)
        is_tail = 0
        s = tree.xmlNodeGetContent(c_node)
        try:
            value = funicode(s)
        finally:
            tree.xmlFree(s)
        c_element = ffi.NULL
    else:
        #assert c_node.type == tree.XML_TEXT_NODE or c_node.type == tree.XML_CDATA_SECTION_NODE, "invalid node type"
        # may be tail text or normal text
        value = funicode(c_node.content)
        c_element = _previousElement(c_node)
        is_tail = bool(c_element)

    if not context._build_smart_strings:
        return value

    if not c_element:
        # non-tail text or attribute text
        c_element = c_node.parent
        while c_element and not _isElement(c_element):
            c_element = c_element.parent

    if c_element:
        parent = _instantiateElementFromXPath(c_element, doc, context)

    return _elementStringResultFactory(
        value, parent, attrname, is_tail)

################################################################################
# callbacks for XPath/XSLT extension functions

def _extension_function_call(context, function, ctxt, nargs):
    doc = context._doc
    try:
        args = []
        for i in range(nargs):
            obj = xpath.valuePop(ctxt)
            o = _unwrapXPathObject(obj, doc, context)
            _freeXPathObject(obj)
            args.append(o)
        args.reverse()

        res = function(context, *args)
        # wrap result for XPath consumption
        obj = _wrapXPathObject(res, doc, context)
        # prevent Python from deallocating elements handed to libxml2
        context._hold(res)
        xpath.valuePush(ctxt, obj)
    except:
        xpath.xmlXPathErr(ctxt, xpath.XPATH_EXPR_ERROR)
        context._exc._store_raised()

# lookup the function by name and call it

@ffi.callback("xmlXPathFunction")
def _xpath_function_call(ctxt, nargs):
    rctxt = ctxt.context
    context = ffi.from_handle(rctxt.userData)
    if rctxt.functionURI:
        functionURI = ffi.string(rctxt.functionURI)
    else:
        functionURI = None
    functionName = ffi.string(rctxt.function)
    function = context._find_cached_function(functionURI, functionName)
    if function is not None:
        _extension_function_call(context, function, ctxt, nargs)
    else:
        if rctxt.functionURI:
            fref = u"{%s}%s" % (functionURI, functionName)
        else:
            fref = functionName
        xpath.xmlXPathErr(ctxt, xpath.XPATH_UNKNOWN_FUNC_ERROR)
        context._exc._store_exception(
            XPathFunctionError(u"XPath function '%s' not found" % fref))
