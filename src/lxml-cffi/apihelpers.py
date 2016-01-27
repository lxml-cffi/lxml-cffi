# Private/public helper functions for API functions

from .includes.etree_defs import _isString, _getNs, _isElement
from .includes.etree_defs import FOR_EACH_ELEMENT_FROM
from ._libxml2 import ffi, lib
from . import python
from collections import OrderedDict
import sys
import re
import os
uri = tree = lib


def displayNode(c_node, indent):
     # to help with debugging
    try:
        print indent * u' ', c_node
        c_child = c_node.children
        while c_child:
            displayNode(c_child, indent + 1)
            c_child = c_child.next
    finally:
        return  # swallow any exceptions

def _assertValidNode(element):
    from . import etree
    if not isinstance(element, etree._Element):
        raise TypeError("Expected a valid Element proxy")
    assert element._c_node, u"invalid Element proxy at %s" % id(element)

def _assertValidDoc(doc):
    from . import etree
    if not isinstance(doc, etree._Document):
        raise TypeError("Expected a valid Document proxy")
    assert doc._c_doc, u"invalid Document proxy at %s" % id(doc)

def _documentOrRaise(input):
    u"""Call this to get the document of a _Document, _ElementTree or _Element
    object, or to raise an exception if it can't be determined.

    Should be used in all API functions for consistency.
    """
    from .etree import _ElementTree, _Element, _Document
    if isinstance(input, _ElementTree):
        if input._context_node is not None:
            doc = input._context_node._doc
        else:
            doc = None
    elif isinstance(input, _Element):
        doc = input._doc
    elif isinstance(input, _Document):
        doc = input
    else:
        raise TypeError, u"Invalid input object: %s" % \
            python._fqtypename(input).decode('utf8')
    if doc is None:
        raise ValueError, u"Input object has no document: %s" % \
            python._fqtypename(input).decode('utf8')
    _assertValidDoc(doc)
    return doc

def _rootNodeOrRaise(input):
    u"""Call this to get the root node of a _Document, _ElementTree or
     _Element object, or to raise an exception if it can't be determined.

    Should be used in all API functions for consistency.
     """
    from .etree import _ElementTree, _Element, _Document
    if isinstance(input, _ElementTree):
        node = input._context_node
    elif isinstance(input, _Element):
        node = input
    elif isinstance(input, _Document):
        node = input.getroot()
    else:
        raise TypeError, u"Invalid input object: %s" % \
            python._fqtypename(input).decode('utf8')
    if (node is None or not node._c_node or
        node._c_node.type != tree.XML_ELEMENT_NODE):
        raise ValueError, u"Input object has no element: %s" % \
            python._fqtypename(input).decode('utf8')
    _assertValidNode(node)
    return node

def _isAncestorOrSame(c_ancestor, c_node):
    while c_node:
        if c_node == c_ancestor:
            return True
        c_node = c_node.parent
    return False

def _makeElement(tag, c_doc, doc,
                 parser, text, tail, attrib, nsmap,
                 extra_attrs):
    u"""Create a new element and initialize text content, namespaces and
    attributes.

    This helper function will reuse as much of the existing document as
    possible:

    If 'parser' is None, the parser will be inherited from 'doc' or the
    default parser will be used.

    If 'doc' is None, 'c_doc' is used to create a new _Document and the new
    element is made its root node.

    If 'c_doc' is also NULL, a new xmlDoc will be created.
    """
    from .parser import _newXMLDoc, _newHTMLDoc
    from .etree import _createElement, _documentFactory, _elementFactory
    if doc is not None:
        c_doc = doc._c_doc
    ns_utf, name_utf = _getNsTag(tag)
    if parser is not None and parser._for_html:
        _htmlTagValidOrRaise(name_utf)
        if not c_doc:
            c_doc = _newHTMLDoc()
    else:
        _tagValidOrRaise(name_utf)
        if not c_doc:
            c_doc = _newXMLDoc()
    c_node = _createElement(c_doc, name_utf)
    if not c_node:
        if doc is None and c_doc:
            tree.xmlFreeDoc(c_doc)
        return python.PyErr_NoMemory()
    try:
        if doc is None:
            tree.xmlDocSetRootElement(c_doc, c_node)
            doc = _documentFactory(c_doc, parser)
        if text is not None:
            _setNodeText(c_node, text)
        if tail is not None:
            _setTailText(c_node, tail)
        # add namespaces to node if necessary
        _initNodeNamespaces(c_node, doc, ns_utf, nsmap)
        _initNodeAttributes(c_node, doc, attrib, extra_attrs)
        return _elementFactory(doc, c_node)
    except:
        # free allocated c_node/c_doc unless Python does it for us
        if c_node.doc != c_doc:
            # node not yet in document => will not be freed by document
            if tail is not None:
                _removeText(c_node.next) # tail
            tree.xmlFreeNode(c_node)
        if doc is None:
            # c_doc will not be freed by doc
            tree.xmlFreeDoc(c_doc)
        raise

def _initNewElement(element, is_html, name_utf, ns_utf,
                    parser, attrib, nsmap, extra_attrs):
    u"""Initialise a new Element object.

    This is used when users instantiate a Python Element subclass
    directly, without it being mapped to an existing XML node.
    """
    from .parser import _newXMLDoc, _newHTMLDoc
    from .etree import _createElement, _documentFactory
    from .proxy import _registerProxy
    if is_html:
        _htmlTagValidOrRaise(name_utf)
        c_doc = _newHTMLDoc()
    else:
        _tagValidOrRaise(name_utf)
        c_doc = _newXMLDoc()
    c_node = _createElement(c_doc, name_utf)
    if not c_node:
        if c_doc:
            tree.xmlFreeDoc(c_doc)
        raise MemoryError()
    tree.xmlDocSetRootElement(c_doc, c_node)
    doc = _documentFactory(c_doc, parser)
    # add namespaces to node if necessary
    _initNodeNamespaces(c_node, doc, ns_utf, nsmap)
    _initNodeAttributes(c_node, doc, attrib, extra_attrs)
    _registerProxy(element, doc, c_node)
    element._init()
    return 0

def _makeSubElement(parent, tag, text, tail,
                    attrib, nsmap, extra_attrs):
    u"""Create a new child element and initialize text content, namespaces and
    attributes.
    """
    from .etree import _createElement, _elementFactory
    if parent is None or parent._doc is None:
        return None
    _assertValidNode(parent)
    ns_utf, name_utf = _getNsTag(tag)
    c_doc = parent._doc._c_doc

    if parent._doc._parser is not None and parent._doc._parser._for_html:
        _htmlTagValidOrRaise(name_utf)
    else:
        _tagValidOrRaise(name_utf)

    c_node = _createElement(c_doc, name_utf)
    if not c_node:
        return python.PyErr_NoMemory()
    tree.xmlAddChild(parent._c_node, c_node)

    try:
        if text is not None:
            _setNodeText(c_node, text)
        if tail is not None:
            _setTailText(c_node, tail)

        # add namespaces to node if necessary
        _initNodeNamespaces(c_node, parent._doc, ns_utf, nsmap)
        _initNodeAttributes(c_node, parent._doc, attrib, extra_attrs)
        return _elementFactory(parent._doc, c_node)
    except:
        # make sure we clean up in case of an error
        _removeNode(parent._doc, c_node)
        raise

def _initNodeNamespaces(c_node, doc,
                        node_ns_utf, nsmap):
    u"""Lookup current namespace prefixes, then set namespace structure for
    node and register new ns-prefix mappings.

    This only works for a newly created node!
    """
    if not nsmap:
        if node_ns_utf is not None:
            _uriValidOrRaise(node_ns_utf)
            doc._setNodeNs(c_node, node_ns_utf)
        return 0

    nsdefs = list(nsmap.items())
    if None in nsmap and len(nsdefs) > 1:
        # Move the default namespace to the end.  This makes sure libxml2
        # prefers a prefix if the ns is defined redundantly on the same
        # element.  That way, users can work around a problem themselves
        # where default namespace attributes on non-default namespaced
        # elements serialise without prefix (i.e. into the non-default
        # namespace).
        item = (None, nsmap[None])
        nsdefs.remove(item)
        nsdefs.append(item)

    for prefix, href in nsdefs:
        href_utf = _utf8(href)
        _uriValidOrRaise(href_utf)
        c_href = href_utf
        if prefix is not None:
            prefix_utf = _utf8(prefix)
            _prefixValidOrRaise(prefix_utf)
            c_prefix = prefix_utf
        else:
            c_prefix = ffi.NULL
        # add namespace with prefix if it is not already known
        c_ns = tree.xmlSearchNs(doc._c_doc, c_node, c_prefix)
        if not c_ns or not c_ns.href or \
                ffi.string(c_ns.href) != c_href:
            c_ns = tree.xmlNewNs(c_node, c_href, c_prefix)
        if href_utf == node_ns_utf:
            tree.xmlSetNs(c_node, c_ns)
            node_ns_utf = None

    if node_ns_utf is not None:
        doc._setNodeNs(c_node, node_ns_utf)
    return 0

def _initNodeAttributes(c_node, doc, attrib, extra):
    u"""Initialise the attributes of an element node.
    """
    if attrib is not None and not hasattr(attrib, u'items'):
        raise TypeError, u"Invalid attribute dictionary: %s" % \
            python._fqtypename(attrib).decode('utf8')
    if not attrib and not extra:
        return  # nothing to do
    is_html = doc._parser._for_html
    seen = set()
    if extra:
        for name, value in sorted(extra.items()):
            _addAttributeToNode(c_node, doc, is_html, name, value, seen)
    if attrib:
        from .etree import _Attrib
        # attrib will usually be a plain unordered dict
        if type(attrib) is dict:
            attrib = sorted(attrib.items())
        elif isinstance(attrib, (_Attrib, OrderedDict)):
            attrib = attrib.items()
        else:
            # assume it's an unordered mapping of some kind
            attrib = sorted(attrib.items())
        for name, value in attrib:
            _addAttributeToNode(c_node, doc, is_html, name, value, seen)

def _addAttributeToNode(c_node, doc, is_html,
                        name, value, seen_tags):
    ns_utf, name_utf = _getNsTag(name)
    if not is_html:
        _attributeValidOrRaise(name_utf)
    value_utf = _utf8(value)
    if ns_utf is None:
        tree.xmlNewProp(c_node, name_utf, value_utf)
    else:
        _uriValidOrRaise(ns_utf)
        c_ns = doc._findOrBuildNodeNs(c_node, ns_utf, ffi.NULL, 1)
        tree.xmlNewNsProp(c_node, c_ns,
                          name_utf, value_utf)

def _removeUnusedNamespaceDeclarations(c_element):
    u"""Remove any namespace declarations from a subtree that are not used by
    any of its elements (or attributes).
    """
    c_ns_list = {}

    if c_element.parent and c_element.parent.type == tree.XML_DOCUMENT_NODE:
        # include the document node
        c_nsdef = c_element.parent.nsDef
        while c_nsdef:
            c_ns_list[c_nsdef] = c_element.parent
            c_nsdef = c_nsdef.next

    for c_element in FOR_EACH_ELEMENT_FROM(c_element, c_element, 1):
        # collect all new namespace declarations into the ns list
        c_nsdef = c_element.nsDef
        while c_nsdef:
            c_ns_list[c_nsdef] = c_element
            c_nsdef = c_nsdef.next

        # remove all namespace declarations from the list that are referenced
        if c_element.type == tree.XML_ELEMENT_NODE:
            c_node = c_element
            while c_node:
                if c_node.ns:
                    try:
                        del c_ns_list[c_node.ns]
                    except KeyError:
                        pass
                if c_node == c_element:
                    # continue with attributes
                    c_node = c_element.properties
                else:
                    c_node = c_node.next

    # free all namespace declarations that remained in the list
    for ns, c_node in c_ns_list.items():
        c_nsdef = c_node.nsDef
        if c_nsdef == ns:
            c_node.nsDef = c_node.nsDef.next
        else:
            while c_nsdef.next != ns:
                c_nsdef = c_nsdef.next
            c_nsdef.next = c_nsdef.next.next
        tree.xmlFreeNs(ns)

    return 0

def _searchNsByHref(c_node, c_href, is_attribute):
    u"""Search a namespace declaration that covers a node (element or
    attribute).

    For attributes, try to find a prefixed namespace declaration
    instead of the default namespaces.  This helps in supporting
    round-trips for attributes on elements with a different namespace.
    """
    c_default_ns = ffi.NULL
    if not c_href or not c_node or c_node.type == tree.XML_ENTITY_REF_NODE:
        return ffi.NULL
    if c_href == ffi.string(tree.XML_XML_NAMESPACE):
        # no special cases here, let libxml2 handle this
        return tree.xmlSearchNsByHref(c_node.doc, c_node, c_href)
    if c_node.type == tree.XML_ATTRIBUTE_NODE:
        is_attribute = 1
    while c_node and c_node.type != tree.XML_ELEMENT_NODE:
        c_node = c_node.parent
    c_element = c_node
    while c_node:
        if c_node.type == tree.XML_ELEMENT_NODE:
            c_ns = c_node.nsDef
            while c_ns:
                if c_ns.href and c_href == ffi.string(c_ns.href):
                    if not c_ns.prefix and is_attribute:
                        # for attributes, continue searching a named
                        # prefix, but keep the first default namespace
                        # declaration that we found
                        if not c_default_ns:
                            c_default_ns = c_ns
                    elif tree.xmlSearchNs(
                        c_element.doc, c_element, c_ns.prefix) == c_ns:
                        # start node is in namespace scope => found!
                        return c_ns
                c_ns = c_ns.next
            if c_node != c_element and c_node.ns:
                # optimise: the node may have the namespace itself
                c_ns = c_node.ns
                if c_ns.href and c_href == c_ns.href:
                    if not c_ns.prefix and is_attribute:
                        # for attributes, continue searching a named
                        # prefix, but keep the first default namespace
                        # declaration that we found
                        if not c_default_ns:
                            c_default_ns = c_ns
                    elif tree.xmlSearchNs(
                        c_element.doc, c_element, c_ns.prefix) == c_ns:
                        # start node is in namespace scope => found!
                        return c_ns
        c_node = c_node.parent
    # nothing found => use a matching default namespace or fail
    if c_default_ns:
        if tree.xmlSearchNs(c_element.doc, c_element,
                            ffi.NULL) == c_default_ns:
            return c_default_ns
    return ffi.NULL

def _replaceNodeByChildren(doc, c_node):
    from .proxy import moveNodeToDocument
    # NOTE: this does not deallocate the node, just unlink it!
    if not c_node.children:
        tree.xmlUnlinkNode(c_node)
        return 0

    c_parent = c_node.parent
    # fix parent links of children
    c_child = c_node.children
    while c_child:
        c_child.parent = c_parent
        c_child = c_child.next

    # fix namespace references of children if their parent's namespace
    # declarations get lost
    if c_node.nsDef:
        c_child = c_node.children
        while c_child:
            moveNodeToDocument(doc, doc._c_doc, c_child)
            c_child = c_child.next

    # fix sibling links to/from child slice
    if not c_node.prev:
        c_parent.children = c_node.children
    else:
        c_node.prev.next = c_node.children
        c_node.children.prev = c_node.prev
    if not c_node.next:
        c_parent.last = c_node.last
    else:
        c_node.next.prev = c_node.last
        c_node.last.next = c_node.next

    # unlink c_node
    c_node.children = c_node.last = ffi.NULL
    c_node.parent = c_node.next = c_node.prev = ffi.NULL
    return 0

def _attributeValue(c_element, c_attrib_node):
    c_href = _getNs(c_attrib_node)
    value = tree.xmlGetNsProp(c_element, c_attrib_node.name, c_href)
    try:
        result = funicode(value)
    finally:
        tree.xmlFree(value)
    return result

def _attributeValueFromNsName(c_element,
                              c_href, c_name):
    c_result = tree.xmlGetNsProp(c_element, c_name, c_href)
    if not c_result:
        return None
    try:
        result = funicode(c_result)
    finally:
        tree.xmlFree(c_result)
    return result

def _getNodeAttributeValue(c_node, key, default):
    ns, tag = _getNsTag(key)
    c_href = ffi.NULL if ns is None else ns
    c_result = tree.xmlGetNsProp(c_node, tag, c_href)
    if not c_result:
        # XXX free namespace that is not in use..?
        return default
    try:
        result = funicode(c_result)
    finally:
        tree.xmlFree(c_result)
    return result

def _getAttributeValue(element, key, default):
    return _getNodeAttributeValue(element._c_node, key, default)

def _setAttributeValue(element, key, value):
    from .etree import QName
    ns, tag = _getNsTag(key)
    if not element._doc._parser._for_html:
        _attributeValidOrRaise(tag)
    c_tag = tag
    if isinstance(value, QName):
        value = _resolveQNameText(element, value)
    else:
        value = _utf8(value)
    c_value = value
    if ns is None:
        c_ns = ffi.NULL
    else:
        c_ns = element._doc._findOrBuildNodeNs(element._c_node,
                                               ns, ffi.NULL, 1)
    tree.xmlSetNsProp(element._c_node, c_ns, c_tag, c_value)
    return 0

def _delAttribute(element, key):
    ns, tag = _getNsTag(key)
    c_href = ns if ns is not None else ffi.NULL
    if _delAttributeFromNsName(element._c_node, c_href, tag):
        raise KeyError, key

def _delAttributeFromNsName(c_node, c_href, c_name):
    c_attr = tree.xmlHasNsProp(c_node, c_name, c_href)
    if not c_attr:
        # XXX free namespace that is not in use..?
        return -1
    tree.xmlRemoveProp(c_attr)
    return 0

def _collectAttributes(c_node, collecttype):
    u"""Collect all attributes of a node in a list.  Depending on collecttype,
    it collects either the name (1), the value (2) or the name-value tuples.
    """
    attributes = []
    c_attr = c_node.properties
    while c_attr:
        if c_attr.type == tree.XML_ATTRIBUTE_NODE:
            if collecttype == 1:
                item = _namespacedName(c_attr)
            elif collecttype == 2:
                item = _attributeValue(c_node, c_attr)
            else:
                item = (_namespacedName(c_attr),
                        _attributeValue(c_node, c_attr))

            attributes.append(item)
        c_attr = c_attr.next
    return attributes

__RE_XML_ENCODING = re.compile(
    ur'^(<\?xml[^>]+)\s+encoding\s*=\s*["\'][^"\']*["\'](\s*\?>|)', re.U)

__REPLACE_XML_ENCODING = __RE_XML_ENCODING.sub
__HAS_XML_ENCODING = __RE_XML_ENCODING.match

def _stripEncodingDeclaration(xml_string):
    # this is a hack to remove the XML encoding declaration from unicode
    return __REPLACE_XML_ENCODING(ur'\g<1>\g<2>', xml_string)

def _hasEncodingDeclaration(xml_string):
    # check if a (unicode) string has an XML encoding declaration
    return __HAS_XML_ENCODING(xml_string) is not None

def _hasText(c_node):
    return c_node and _textNodeOrSkip(c_node.children)

def _collectText(c_node):
    u"""Collect all text nodes and return them as a unicode string.

    Start collecting at c_node.

    If there was no text to collect, return None
    """
    # check for multiple text nodes
    scount = 0
    c_text = ffi.NULL
    c_node_cur = c_node = _textNodeOrSkip(c_node)
    while c_node_cur:
        if c_node_cur.content:
            c_text = c_node_cur.content
        scount += 1
        c_node_cur = _textNodeOrSkip(c_node_cur.next)

    # handle two most common cases first
    if not c_text:
        return '' if scount > 0 else None
    if scount == 1:
        return funicode(c_text)

    # the rest is not performance critical anymore
    result = b''
    while c_node:
        result = result + ffi.string(c_node.content)
        c_node = _textNodeOrSkip(c_node.next)
    return result.decode('utf8')

def _removeText(c_node):
    u"""Remove all text nodes.

    Start removing at c_node.
    """
    c_node = _textNodeOrSkip(c_node)
    while c_node:
        c_next = _textNodeOrSkip(c_node.next)
        tree.xmlUnlinkNode(c_node)
        tree.xmlFreeNode(c_node)
        c_node = c_next

def _setNodeText(c_node, value):
    # remove all text nodes at the start first
    from .etree import CDATA
    _removeText(c_node.children)
    if value is None:
        return 0
    # now add new text node with value at start
    if _isString(value):
        text = _utf8(value)
        c_text_node = tree.xmlNewDocText(c_node.doc, text)
    elif isinstance(value, CDATA):
        c_text_node = tree.xmlNewCDataBlock(
            c_node.doc, value._utf8_data,
            python.PyBytes_GET_SIZE(value._utf8_data))
    else:
        # this will raise the right error
       _utf8(value)
       return -1
    if not c_node.children:
        tree.xmlAddChild(c_node, c_text_node)
    else:
        tree.xmlAddPrevSibling(c_node.children, c_text_node)
    return 0

def _setTailText(c_node, value):
    # remove all text nodes at the start first
    _removeText(c_node.next)
    if value is None:
        return 0
    text = _utf8(value)
    c_text_node = tree.xmlNewDocText(c_node.doc, text)
    # XXX what if we're the top element?
    tree.xmlAddNextSibling(c_node, c_text_node)
    return 0

def _resolveQNameText(element, value):
    ns, tag = _getNsTag(value)
    if ns is None:
        return tag
    else:
        c_ns = element._doc._findOrBuildNodeNs(
            element._c_node, ns, ffi.NULL, 0)
        return (u'%s:%s' % (ffi.string(c_ns.prefix), tag)).encode()

def _hasChild(c_node):
    return bool(c_node and _findChildForwards(c_node, 0))

def _countElements(c_node):
    u"Counts the elements within the following siblings and the node itself."
    count = 0
    while c_node:
        if _isElement(c_node):
            count = count + 1
        c_node = c_node.next
    return count

def _findChildSlice(sliceobject, c_parent):
    u"""Resolve a children slice.

    Returns the start node, step size and the slice length in the
    pointer arguments.
    """
    start = 0
    stop = 0
    childcount = _countElements(c_parent.children)
    if childcount == 0:
        if sliceobject.step is None:
            step = 1
        else:
            step = sliceobject.step
        return ffi.NULL, step, 0
    start, stop, step = sliceobject.indices(childcount)
    if step > 0:
        length = (stop - 1 - start) // step + 1
    else:
        length = (stop - start ) // step
    if start > childcount / 2:
        c_start_node = _findChildBackwards(c_parent, childcount - start - 1)
    else:
        c_start_node = _findChild(c_parent, start)
    return c_start_node, step, length

def _isFullSlice(sliceobject):
    u"""Conservative guess if this slice is a full slice as in ``s[:]``.
    """
    step = 0
    if sliceobject is None:
        return 0
    if sliceobject.start is None and \
            sliceobject.stop is None:
        if sliceobject.step is None:
            return 1
        if sliceobject.step == 1:
            return 1
        return 0
    return 0

def _collectChildren(element):
    from .etree import _elementFactory
    result = []
    c_node = element._c_node.children
    if c_node:
        if not _isElement(c_node):
            c_node = _nextElement(c_node)
        while c_node:
            result.append(_elementFactory(element._doc, c_node))
            c_node = _nextElement(c_node)
    return result

def _findChild(c_node, index):
    if index < 0:
        return _findChildBackwards(c_node, -index - 1)
    else:
        return _findChildForwards(c_node, index)

def _findChildForwards(c_node, index):
    u"""Return child element of c_node with index, or return NULL if not found.
    """
    c_child = c_node.children
    c = 0
    while c_child:
        if _isElement(c_child):
            if c == index:
                return c_child
            c += 1
        c_child = c_child.next
    return ffi.NULL

def _findChildBackwards(c_node, index):
    u"""Return child element of c_node with index, or return NULL if not found.
    Search from the end.
    """
    c_child = c_node.last
    c = 0
    while c_child:
        if _isElement(c_child):
            if c == index:
                return c_child
            c += 1
        c_child = c_child.prev
    return ffi.NULL

def _textNodeOrSkip(c_node):
    u"""Return the node if it's a text node.  Skip over ignorable nodes in a
    series of text nodes.  Return NULL if a non-ignorable node is found.

    This is used to skip over XInclude nodes when collecting adjacent text
    nodes.
    """
    while c_node:
        if c_node.type == tree.XML_TEXT_NODE or \
               c_node.type == tree.XML_CDATA_SECTION_NODE:
            return c_node
        elif c_node.type == tree.XML_XINCLUDE_START or \
                 c_node.type == tree.XML_XINCLUDE_END:
            c_node = c_node.next
        else:
            return None

def _nextElement(c_node):
    u"""Given a node, find the next sibling that is an element.
    """
    if not c_node:
        return ffi.NULL
    c_node = c_node.next
    while c_node:
        if _isElement(c_node):
            return c_node
        c_node = c_node.next
    return ffi.NULL

def _previousElement(c_node):
    u"""Given a node, find the next sibling that is an element.
    """
    if not c_node:
        return ffi.NULL
    c_node = c_node.prev
    while c_node:
        if _isElement(c_node):
            return c_node
        c_node = c_node.prev
    return ffi.NULL

def _parentElement(c_node):
    u"Given a node, find the parent element."
    if not c_node or not _isElement(c_node):
        return ffi.NULL
    c_node = c_node.parent
    if not c_node or not _isElement(c_node):
        return ffi.NULL
    return c_node

def _tagMatches(c_node, c_href, c_name):
    u"""Tests if the node matches namespace URI and tag name.

    A node matches if it matches both c_href and c_name.

    A node matches c_href if any of the following is true:
    * c_href is NULL
    * its namespace is NULL and c_href is the empty string
    * its namespace string equals the c_href string

    A node matches c_name if any of the following is true:
    * c_name is NULL
    * its name string equals the c_name string
    """
    if not c_node:
        return 0
    if c_node.type != tree.XML_ELEMENT_NODE:
        # not an element, only succeed if we match everything
        return not c_name and not c_href
    if not c_name:
        if not c_href:
            # always match
            return 1
        else:
            c_node_href = _getNs(c_node)
            if not c_node_href:
                return c_href[0] == '\0'
            else:
                return tree.xmlStrcmp(c_node_href, c_href) == 0
    elif not c_href:
        if _getNs(c_node):
            return 0
        return c_node.name == c_name or tree.xmlStrcmp(c_node.name, c_name) == 0
    elif c_node.name == c_name or tree.xmlStrcmp(c_node.name, c_name) == 0:
        c_node_href = _getNs(c_node)
        if not c_node_href:
            return c_href[0] == '\0'
        else:
            return tree.xmlStrcmp(c_node_href, c_href) == 0
    else:
        return 0

def _tagMatchesExactly(c_node, c_qname):
    u"""Tests if the node matches namespace URI and tag name.

    This differs from _tagMatches() in that it does not consider a
    NULL value in qname.href a wildcard, and that it expects the c_name
    to be taken from the doc dict, i.e. it only compares the names by
    address.

    A node matches if it matches both href and c_name of the qname.

    A node matches c_href if any of the following is true:
    * its namespace is NULL and c_href is the empty string
    * its namespace string equals the c_href string

    A node matches c_name if any of the following is true:
    * c_name is NULL
    * its name string points to the same address (!) as c_name
    """
    return _nsTagMatchesExactly(_getNs(c_node), c_node.name, c_qname)

def _nsTagMatchesExactly(c_node_href, c_node_name, c_qname):
    u"""Tests if name and namespace URI match those of c_qname.

    This differs from _tagMatches() in that it does not consider a
    NULL value in qname.href a wildcard, and that it expects the c_name
    to be taken from the doc dict, i.e. it only compares the names by
    address.

    A node matches if it matches both href and c_name of the qname.

    A node matches c_href if any of the following is true:
    * its namespace is NULL and c_href is the empty string
    * its namespace string equals the c_href string

    A node matches c_name if any of the following is true:
    * c_name is NULL
    * its name string points to the same address (!) as c_name
    """
    if c_qname.c_name and c_qname.c_name != c_node_name:
        return 0
    if c_qname.href is None:
        return 1
    c_href = c_qname.href
    if c_href == '':
        return not c_node_href or c_node_href[0] == '\0'
    elif not c_node_href:
        return 0
    else:
        return c_href == ffi.string(c_node_href)

def _mapTagsToQnameMatchArray(c_doc, ns_tags, c_ns_tags, force_into_dict):
    u"""Map a sequence of (name, namespace) pairs to a qname array for efficient
    matching with _tagMatchesExactly() above.

    Note that each qname struct in the array owns its href byte string object
    if it is not NULL.
    """
    from .etree import qname
    count = 0
    for ns, tag in ns_tags:
        if tag is None:
            c_tag = ffi.NULL
        elif force_into_dict:
            c_tag = tree.xmlDictLookup(c_doc.dict, tag, len(tag))
            if not c_tag:
                raise MemoryError()
        else:
            c_tag = tree.xmlDictExists(c_doc.dict, tag, len(tag))
            if not c_tag:
                # name not in dict => not in document either
                continue
        item = qname()
        item.c_name = c_tag
        item.href = ns
        c_ns_tags.append(item)
        count += 1
    return count

def _removeNode(doc, c_node):
    u"""Unlink and free a node and subnodes if possible.  Otherwise, make sure
    it's self-contained.
    """
    from .proxy import attemptDeallocation, moveNodeToDocument
    c_next = c_node.next
    tree.xmlUnlinkNode(c_node)
    _moveTail(c_next, c_node)
    if not attemptDeallocation(c_node):
        # make namespaces absolute
        moveNodeToDocument(doc, c_node.doc, c_node)
    return 0

def _removeSiblings(c_element, node_type, with_tail):
    from .proxy import attemptDeallocation
    c_node = c_element.next
    while c_node:
        c_next = _nextElement(c_node)
        if c_node.type == node_type:
            if with_tail:
                _removeText(c_node.next)
            tree.xmlUnlinkNode(c_node)
            attemptDeallocation(c_node)
        c_node = c_next
    c_node = c_element.prev
    while c_node:
        c_next = _previousElement(c_node)
        if c_node.type == node_type:
            if with_tail:
                _removeText(c_node.next)
            tree.xmlUnlinkNode(c_node)
            attemptDeallocation(c_node)
        c_node = c_next
    return 0

def _moveTail(c_tail, c_target):
    # tail support: look for any text nodes trailing this node and
    # move them too
    c_tail = _textNodeOrSkip(c_tail)
    while c_tail:
        c_next = _textNodeOrSkip(c_tail.next)
        c_target = tree.xmlAddNextSibling(c_target, c_tail)
        c_tail = c_next

def _copyTail(c_tail, c_target):
    # tail copying support: look for any text nodes trailing this node and
    # copy it to the target node
    c_tail = _textNodeOrSkip(c_tail)
    while c_tail:
        if c_target.doc != c_tail.doc:
            c_new_tail = tree.xmlDocCopyNode(c_tail, c_target.doc, 0)
        else:
            c_new_tail = tree.xmlCopyNode(c_tail, 0)
        if not c_new_tail:
            python.PyErr_NoMemory()
        c_target = tree.xmlAddNextSibling(c_target, c_new_tail)
        c_tail = _textNodeOrSkip(c_tail.next)
    return 0

def _copyNonElementSiblings(c_node, c_target):
    c_sibling = c_node
    while c_sibling.prev and \
            (c_sibling.prev.type == tree.XML_PI_NODE or \
                 c_sibling.prev.type == tree.XML_COMMENT_NODE):
        c_sibling = c_sibling.prev
    while c_sibling != c_node:
        c_copy = tree.xmlDocCopyNode(c_sibling, c_target.doc, 1)
        if not c_copy:
            raise MemoryError()
        tree.xmlAddPrevSibling(c_target, c_copy)
        c_sibling = c_sibling.next
    while c_sibling.next and \
            (c_sibling.next.type == tree.XML_PI_NODE or \
                 c_sibling.next.type == tree.XML_COMMENT_NODE):
        c_sibling = c_sibling.next
        c_copy = tree.xmlDocCopyNode(c_sibling, c_target.doc, 1)
        if not c_copy:
            raise MemoryError()
        tree.xmlAddNextSibling(c_target, c_copy)

def _nextElement(c_node):
    u"""Given a node, find the next sibling that is an element.
    """
    if not c_node:
        return ffi.NULL
    c_node = c_node.next
    while c_node:
        if _isElement(c_node):
            return c_node
        c_node = c_node.next
    return ffi.NULL

def _deleteSlice(doc, c_node, count, step):
    u"""Delete slice, ``count`` items starting with ``c_node`` with a step
    width of ``step``.
    """
    if not c_node:
        return 0
    if step > 0:
        next_element = _nextElement
    else:
        step = -step
        next_element = _previousElement
    # now start deleting nodes
    c = 0
    c_next = c_node
    while c_node and c < count:
        for i in range(step):
            c_next = next_element(c_next)
        _removeNode(doc, c_node)
        c += 1
        c_node = c_next
    return 0

def _replaceSlice(parent, c_node,
                  slicelength, step,
                  left_to_right, elements):
    u"""Replace the slice of ``count`` elements starting at ``c_node`` with
    positive step width ``step`` by the Elements in ``elements``.  The
    direction is given by the boolean argument ``left_to_right``.

    ``c_node`` may be NULL to indicate the end of the children list.
    """
    from .proxy import moveNodeToDocument
    assert step > 0
    if left_to_right:
        next_element = _nextElement
    else:
        next_element = _previousElement

    if not isinstance(elements, (list, tuple)):
        elements = list(elements)

    if step > 1:
        # *replacing* children stepwise with list => check size!
        seqlength = len(elements)
        if seqlength != slicelength:
            raise ValueError, u"attempt to assign sequence of size %d " \
                u"to extended slice of size %d" % (seqlength, slicelength)

    if not c_node:
        # no children yet => add all elements straight away
        if left_to_right:
            for element in elements:
                assert element is not None, u"Node must not be None"
                _appendChild(parent, element)
        else:
            for element in elements:
                assert element is not None, u"Node must not be None"
                _prependChild(parent, element)
        return 0

    # remove the elements first as some might be re-added
    if left_to_right:
        # L->R, remember left neighbour
        c_orig_neighbour = _previousElement(c_node)
    else:
        # R->L, remember right neighbour
        c_orig_neighbour = _nextElement(c_node)

    # We remove the original slice elements one by one. Since we hold
    # a Python reference to all elements that we will insert, it is
    # safe to let _removeNode() try (and fail) to free them even if
    # the element itself or one of its descendents will be reinserted.
    c = 0
    c_next = c_node
    while c_node and c < slicelength:
        for i in range(step):
            c_next = next_element(c_next)
        _removeNode(parent._doc, c_node)
        c += 1
        c_node = c_next

    # make sure each element is inserted only once
    elements = iter(elements)

    # find the first node right of the new insertion point
    if left_to_right:
        if c_orig_neighbour:
            c_node = next_element(c_orig_neighbour)
        else:
            # before the first element
            c_node = _findChildForwards(parent._c_node, 0)
    elif not c_orig_neighbour:
        # at the end, but reversed stepping
        # append one element and go to the next insertion point
        for element in elements:
            assert element is not None, u"Node must not be None"
            _appendChild(parent, element)
            c_node = element._c_node
            if slicelength > 0:
                slicelength -= 1
                for i in range(1, step):
                    c_node = next_element(c_node)
            break

    if left_to_right:
        # adjust step size after removing slice as we are not stepping
        # over the newly inserted elements
        step -= 1

    # now insert elements where we removed them
    if c_node:
        for element in elements:
            assert element is not None, u"Node must not be None"
            _assertValidNode(element)
            # move element and tail over
            c_source_doc = element._c_node.doc
            c_next = element._c_node.next
            tree.xmlAddPrevSibling(c_node, element._c_node)
            _moveTail(c_next, element._c_node)

            # integrate element into new document
            moveNodeToDocument(parent._doc, c_source_doc, element._c_node)

            # stop at the end of the slice
            if slicelength > 0:
                slicelength = slicelength - 1
                for i in range(step):
                    c_node = next_element(c_node)
                if not c_node:
                    break
        else:
            # everything inserted
            return 0

    # append the remaining elements at the respective end
    if left_to_right:
        for element in elements:
            assert element is not None, u"Node must not be None"
            _assertValidNode(element)
            _appendChild(parent, element)
    else:
        for element in elements:
            assert element is not None, u"Node must not be None"
            _assertValidNode(element)
            _prependChild(parent, element)

    return 0

def _appendChild(parent, child):
    u"""Append a new child to a parent element.
    """
    from .proxy import moveNodeToDocument
    c_node = child._c_node
    c_source_doc = c_node.doc
    # prevent cycles
    if _isAncestorOrSame(c_node, parent._c_node):
        raise ValueError("cannot append parent to itself")
    # store possible text node
    c_next = c_node.next
    # move node itself
    tree.xmlUnlinkNode(c_node)
    tree.xmlAddChild(parent._c_node, c_node)
    _moveTail(c_next, c_node)
    # uh oh, elements may be pointing to different doc when
    # parent element has moved; change them too..
    moveNodeToDocument(parent._doc, c_source_doc, c_node)

def _prependChild(parent, child):
    u"""Prepend a new child to a parent element.
    """
    from .proxy import moveNodeToDocument
    c_node = child._c_node
    c_source_doc = c_node.doc
    # prevent cycles
    if _isAncestorOrSame(c_node, parent._c_node):
        raise ValueError("cannot append parent to itself")
    # store possible text node
    c_next = c_node.next
    # move node itself
    c_child = _findChildForwards(parent._c_node, 0)
    if not c_child:
        tree.xmlUnlinkNode(c_node)
        tree.xmlAddChild(parent._c_node, c_node)
    else:
        tree.xmlAddPrevSibling(c_child, c_node)
    _moveTail(c_next, c_node)
    # uh oh, elements may be pointing to different doc when
    # parent element has moved; change them too..
    moveNodeToDocument(parent._doc, c_source_doc, c_node)

def _appendSibling(element, sibling):
    u"""Add a new sibling behind an element.
    """
    from .proxy import moveNodeToDocument
    c_node = sibling._c_node
    # prevent cycles
    if _isAncestorOrSame(c_node, element._c_node):
        if element._c_node == c_node:
            return 0  # nothing to do
        raise ValueError("cannot add ancestor as sibling, please break cycle first")
    c_source_doc = c_node.doc
    # store possible text node
    c_next = c_node.next
    # move node itself
    tree.xmlAddNextSibling(element._c_node, c_node)
    _moveTail(c_next, c_node)
    # uh oh, elements may be pointing to different doc when
    # parent element has moved; change them too..
    moveNodeToDocument(element._doc, c_source_doc, c_node)

def _prependSibling(element, sibling):
    u"""Add a new sibling before an element.
    """
    from .proxy import moveNodeToDocument
    c_node = sibling._c_node
    if _isAncestorOrSame(c_node, element._c_node):
        if element._c_node == c_node:
            return 0  # nothing to do
        raise ValueError("cannot add ancestor as sibling, please break cycle first")
    c_source_doc = c_node.doc
    # store possible text node
    c_next = c_node.next
    # move node itself
    tree.xmlAddPrevSibling(element._c_node, c_node)
    _moveTail(c_next, c_node)
    # uh oh, elements may be pointing to different doc when
    # parent element has moved; change them too..
    moveNodeToDocument(element._doc, c_source_doc, c_node)

def isutf8(s):
    c = s[0]
    while c != 0:
        if c & 0x80:
            return 1
        s = s + 1
        c = s[0]
    return 0

def check_string_utf8(pystring):
    u"""Check if a string looks like valid UTF-8 XML content.  Returns 0
    for ASCII, 1 for UTF-8 and -1 in the case of errors, such as NULL
    bytes or ASCII control characters.
    """
    s = pystring
    end = len(pystring)
    i = 0
    is_non_ascii = 0
    while i < end:
        if ord(s[i]) & 0x80:
            # skip over multi byte sequences
            while i < end and ord(s[i]) & 0x80:
                i += 1
            is_non_ascii = 1
        if  i < end and not tree.xmlIsChar_ch(ord(s[i])):
            return -1 # invalid!
        i += 1
    return is_non_ascii

def funicodeOrNone(s):
    return funicode(s) if s else None

def funicodeOrEmpty(s):
    return funicode(s) if s else ''

def funicode(s):
    data = ffi.string(s)
    if python.LXML_UNICODE_STRINGS:
        return data.decode('utf8')
    else:
        try:
            data.decode('ascii')
        except UnicodeDecodeError:
            return data.decode('utf8')
        else:
            return data

def _utf8(s):
    """Test if a string is valid user input and encode it to UTF-8.
    Reject all bytes/unicode input that contains non-XML characters.
    Reject all bytes input that contains non-ASCII characters.
    """
    if not python.IS_PYTHON3 and type(s) is bytes:
        utf8_string = s
        invalid = check_string_utf8(utf8_string)
    elif isinstance(s, unicode):
        utf8_string = s.encode('utf8')
        invalid = check_string_utf8(utf8_string) == -1 # non-XML?
    elif isinstance(s, (bytes, bytearray)):
        utf8_string = bytes(s)
        invalid = check_string_utf8(utf8_string)
    else:
        raise TypeError("Argument must be bytes or unicode, got '%.200s'" % type(s).__name__)
    if invalid:
        raise ValueError(
            "All strings must be XML compatible: Unicode or ASCII, no NULL bytes or control characters")
    return utf8_string

def _utf8orNone(s):
    return _utf8(s) if s is not None else None

def _isFilePath(c_path):
    u"simple heuristic to see if a path is a filename"
    # test if it looks like an absolute Unix path or a Windows network path
    if not c_path:
        return 0
    if c_path[0] == '/':
        return 1
    # test if it looks like an absolute Windows path or URL
    if 'a' <= c_path[0] <= 'z' or 'A' <= c_path[0] <= 'Z':
        if c_path[1] == ':' and (len(c_path) == 2 or c_path[2] == '\\'):
            return 1  # C: or C:\...
        i = 0
        # test if it looks like a URL with scheme://
        while i < len(c_path) and (
            'a' <= c_path[i] <= 'z' or 'A' <= c_path[i] <= 'Z'):
            i += 1
        if c_path[i:i+2] == '://':
            return 0

    # assume it's a relative path
    return 1

_FILENAME_ENCODING = (sys.getfilesystemencoding() or sys.getdefaultencoding() or 'ascii')

def _encodeFilename(filename):
    u"""Make sure a filename is 8-bit encoded (or None).
    """
    if filename is None:
        return None
    elif isinstance(filename, bytes):
        return filename
    elif isinstance(filename, unicode):
        filename8 = filename.encode('utf8')
        if _isFilePath(filename8):
            try:
                return filename.encode(_FILENAME_ENCODING)
            except UnicodeEncodeError:
                pass
        return filename8
    else:
        raise TypeError("Argument must be string or unicode.")

def _decodeFilename(c_path):
    u"""Make the filename a unicode string if we are in Py3.
    """
    return _decodeFilenameWithLength(c_path, len(c_path))

def _decodeFilenameWithLength(c_path, c_len):
    """Make the filename a unicode string if we are in Py3.
    """
    if _isFilePath(c_path):
        try:
            return c_path.decode(sys.getfilesystemencoding())
        except UnicodeDecodeError:
            pass
    try:
        return c_path[:c_len].decode('UTF-8')
    except UnicodeDecodeError:
        # this is a stupid fallback, but it might still work...
        return c_path[:c_len].decode('latin-1', 'replace')

def _encodeFilenameUTF8(filename):
    u"""Recode filename as UTF-8. Tries ASCII, local filesystem encoding and
    UTF-8 as source encoding.
    """
    if filename is None:
        return None
    elif isinstance(filename, bytes):
        if not check_string_utf8(filename):
            # plain ASCII!
            return filename
        c_filename = filename
        try:
            # try to decode with default encoding
            filename = python.PyUnicode_Decode(
                c_filename, len(filename),
                _C_FILENAME_ENCODING, NULL)
        except UnicodeDecodeError as decode_exc:
            try:
                # try if it's proper UTF-8
                filename = filename.decode('utf8')
            except UnicodeDecodeError:
                raise decode_exc # otherwise re-raise original exception
    if isinstance(filename, unicode):
        return filename.encode('utf8')
    else:
        raise TypeError("Argument must be string or unicode.")

def _getNsTag(tag):
    u"""Given a tag, find namespace URI and tag name.
    Return None for NS uri if no namespace URI provided.
    """
    return __getNsTag(tag, 0)

def _getNsTagWithEmptyNs(tag):
    u"""Given a tag, find namespace URI and tag name.  Return None for NS uri
    if no namespace URI provided, or the empty string if namespace
    part is '{}'.
    """
    return __getNsTag(tag, 1)

def __getNsTag(tag, empty_ns):
    u"""Given a tag, find namespace URI and tag name.
    Return None for NS uri if no namespace URI provided.
    """
    from .etree import QName
    ns = None
    # _isString() is much faster than isinstance()
    if not _isString(tag) and isinstance(tag, QName):
        tag = tag.text
    tag = _utf8(tag)
    c_tag = tag
    if len(tag) == 0:
        raise ValueError, u"Empty tag name"
    elif c_tag[0] == '{':
        c_ns_end = c_tag.find('}')
        if c_ns_end < 0:
            raise ValueError, u"Invalid tag name"
        nslen  = c_ns_end + 1
        taglen = len(tag) - nslen
        if taglen == 0:
            raise ValueError, u"Empty tag name"
        if nslen > 2:
            ns = c_tag[1:nslen-1]
        elif empty_ns:
            ns = b''
        tag = c_tag[nslen:]
    return ns, tag

def _characterReferenceIsValid(c_name):
    if c_name[0] == 'x':
        c_name = c_name[1:]
        is_hex = 1
    else:
        is_hex = 0
    if not c_name:
        return 0
    for c in c_name:
        if c < '0' or c > '9':
            if not is_hex:
                return 0
            if not ('a' <= c <= 'f'):
                if not ('A' <= c <= 'F'):
                    return 0
    return 1

def _tagValidOrRaise(tag_utf):
    if not _pyXmlNameIsValid(tag_utf):
        raise ValueError(u"Invalid tag name %r" %
                         tag_utf.decode('utf8'))

def _htmlTagValidOrRaise(tag_utf):
    if not _pyHtmlNameIsValid(tag_utf):
        raise ValueError(u"Invalid HTML tag name %r" %
                         tag_utf.decode('utf8'))

def _attributeValidOrRaise(name_utf):
    if not _pyXmlNameIsValid(name_utf):
        raise ValueError(u"Invalid attribute name %r" %
                         name_utf.decode('utf8'))

def _prefixValidOrRaise(tag_utf):
    if not _pyXmlNameIsValid(tag_utf):
        raise ValueError(u"Invalid namespace prefix %r" %
                         tag_utf.decode('utf8'))

def _uriValidOrRaise(uri_utf):
    c_uri = uri.xmlParseURI(uri_utf)
    if not c_uri:
        raise ValueError(u"Invalid namespace URI %r" %
                         uri_utf.decode('utf8'))
    uri.xmlFreeURI(c_uri)
    return 0

def _pyXmlNameIsValid(name_utf8):
    return _xmlNameIsValid(name_utf8)

def _pyHtmlNameIsValid(name_utf8):
    return _htmlNameIsValid(name_utf8)

def _xmlNameIsValid(c_name):
    return tree.xmlValidateNCName(c_name, 0) == 0

def _htmlNameIsValid(c_name):
    if not c_name:
        return 0
    for c in c_name:
        if c in b'&<>/"\'\t\n\x0B\x0C\r ':
            return 0
    return 1

def _namespacedName(c_node):
    return _namespacedNameFromNsName(_getNs(c_node), c_node.name)

def _namespacedNameFromNsName(href, name):
    # XXX AFA consider accepting strings only
    if not href:
        return funicode(name)
    s = "{%s}%s" % (ffi.string(href), ffi.string(name))
    if python.LXML_UNICODE_STRINGS:
        return s.decode('utf8')
    try:
        s.decode('ascii')
    except UnicodeDecodeError:
        return s.decode('utf8')
    else:
        return s

def _getFilenameForFile(source):
    u"""Given a Python File or Gzip object, give filename back.

    Returns None if not a file object.
    """
    # urllib2 provides a geturl() method
    try:
        return source.geturl()
    except:
        pass
    # file instances have a name attribute
    try:
        filename = source.name
    except AttributeError:
        pass
    else:
        if _isString(filename):
            return os.path.abspath(filename)
    # gzip file instances have a filename attribute (before Py3k)
    try:
        filename = source.filename
    except AttributeError:
        pass
    else:
        if _isString(filename):
            return os.path.abspath(filename)
    # can't determine filename
    return None
