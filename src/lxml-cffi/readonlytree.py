# read-only tree implementation

from .apihelpers import _collectText, _moveTail, _isElement, _setNodeText
from .apihelpers import funicode, _namespacedName, _findChild
from .apihelpers import _collectAttributes, _findChildBackwards
from .apihelpers import _getNodeAttributeValue, _nextElement, _previousElement
from .apihelpers import _isFullSlice, _findChildSlice
from .parser import _copyNodeToDoc, _copyDocRoot
from .etree import _Element, QName, _documentFactory
from . import python
from ._libxml2 import ffi, lib as tree


class _ReadOnlyProxy(object):
    u"A read-only proxy class suitable for PIs/Comments (for internal use only!)."
    _c_node = ffi.NULL
    _free_after_use = 0

    def _assertNode(self):
        u"""This is our way of saying: this proxy is invalid!
        """
        if not self._c_node:
            raise ReferenceError("Proxy invalidated!")
        return 0

    def free_after_use(self):
        u"""Should the xmlNode* be freed when releasing the proxy?
        """
        self._free_after_use = 1

    @property
    def tag(self):
        u"""Element tag
        """
        self._assertNode()
        if self._c_node.type == tree.XML_ELEMENT_NODE:
            return _namespacedName(self._c_node)
        elif self._c_node.type == tree.XML_PI_NODE:
            return ProcessingInstruction
        elif self._c_node.type == tree.XML_COMMENT_NODE:
            return Comment
        elif self._c_node.type == tree.XML_ENTITY_REF_NODE:
            return Entity
        else:
            self._raise_unsupported_type()

    @property
    def text(self):
        u"""Text before the first subelement. This is either a string or
        the value None, if there was no text.
        """
        self._assertNode()
        if self._c_node.type == tree.XML_ELEMENT_NODE:
            return _collectText(self._c_node.children)
        elif self._c_node.type in (tree.XML_PI_NODE,
                                   tree.XML_COMMENT_NODE):
            if not self._c_node.content:
                return ''
            else:
                return funicode(self._c_node.content)
        elif self._c_node.type == tree.XML_ENTITY_REF_NODE:
            return u'&%s;' % funicode(self._c_node.name)
        else:
            self._raise_unsupported_type()

    @property
    def tail(self):
        u"""Text after this element's end tag, but before the next sibling
        element's start tag. This is either a string or the value None, if
        there was no text.
        """
        self._assertNode()
        return _collectText(self._c_node.next)

    @property
    def sourceline(self):
        u"""Original line number as found by the parser or None if unknown.
        """
        self._assertNode()
        line = tree.xmlGetLineNo(self._c_node)
        if line > 0:
            return line
        else:
            return None

    def __repr__(self):
        self._assertNode()
        if self._c_node.type == tree.XML_ELEMENT_NODE:
            return u"<Element %s at 0x%x>" % (self.tag, id(self))
        elif self._c_node.type == tree.XML_COMMENT_NODE:
            return u"<!--%s-->" % self.text
        elif self._c_node.type == tree.XML_ENTITY_NODE:
            return u"&%s;" % funicode(self._c_node.name)
        elif self._c_node.type == tree.XML_PI_NODE:
            text = self.text
            if text:
                return u"<?%s %s?>" % (self.target, text)
            else:
                return u"<?%s?>" % self.target
        else:
            self._raise_unsupported_type()

    def __getitem__(self, x):
        u"""Returns the subelement at the given position or the requested
        slice.
        """
        c_node = ffi.NULL
        step = 0
        slicelength = 0
        self._assertNode()
        if isinstance(x, slice):
            # slicing
            if _isFullSlice(x):
                return _collectChildren(self)
            c_node, step, slicelength = _findChildSlice(x, self._c_node)
            if not c_node:
                return []
            if step > 0:
                next_element = _nextElement
            else:
                step = -step
                next_element = _previousElement
            result = []
            c = 0
            while c_node is not NULL and c < slicelength:
                result.append(_newReadOnlyProxy(self._source_proxy, c_node))
                result.append(_elementFactory(self._doc, c_node))
                c = c + 1
                for i in xrange(step):
                    c_node = next_element(c_node)
            return result
        else:
            # indexing
            c_node = _findChild(self._c_node, x)
            if not c_node:
                raise IndexError, u"list index out of range"
            return _newReadOnlyProxy(self._source_proxy, c_node)

    def __len__(self):
        u"""Returns the number of subelements.
        """
        self._assertNode()
        c = 0
        c_node = self._c_node.children
        while c_node:
            if _isElement(c_node):
                c = c + 1
            c_node = c_node.next
        return c

    def __nonzero__(self):
        self._assertNode()
        c_node = _findChildBackwards(self._c_node, 0)
        return bool(c_node)

    def __deepcopy__(self, memo):
        u"__deepcopy__(self, memo)"
        return self.__copy__()

    def __copy__(self):
        u"__copy__(self)"
        if not self._c_node:
            return self
        c_doc = _copyDocRoot(self._c_node.doc, self._c_node) # recursive
        new_doc = _documentFactory(c_doc, None)
        root = new_doc.getroot()
        if root is not None:
            return root
        # Comment/PI
        c_node = c_doc.children
        while c_node and c_node.type != self._c_node.type:
            c_node = c_node.next
        if not c_node:
            return None
        return _elementFactory(new_doc, c_node)

    def __iter__(self):
        return iter(self.getchildren())

    def iterchildren(self, tag=None, reversed=False):
        u"""iterchildren(self, tag=None, reversed=False)

        Iterate over the children of this element.
        """
        children = self.getchildren()
        if tag is not None and tag != '*':
            children = [ el for el in children if el.tag == tag ]
        if reversed:
            children = children[::-1]
        return iter(children)

    def getchildren(self):
        u"""Returns all subelements. The elements are returned in document
        order.
        """
        self._assertNode()
        result = []
        c_node = self._c_node.children
        while c_node:
            if _isElement(c_node):
                result.append(_newReadOnlyProxy(self._source_proxy, c_node))
            c_node = c_node.next
        return result

    def getparent(self):
        u"""Returns the parent of this element or None for the root element.
        """
        self._assertNode()
        c_parent = self._c_node.parent
        if not c_parent or not _isElement(c_parent):
            return None
        else:
            return _newReadOnlyProxy(self._source_proxy, c_parent)

    def getnext(self):
        u"""Returns the following sibling of this element or None.
        """
        self._assertNode()
        c_node = _nextElement(self._c_node)
        if c_node:
            return _newReadOnlyProxy(self._source_proxy, c_node)
        return None

    def getprevious(self):
        u"""Returns the preceding sibling of this element or None.
        """
        self._assertNode()
        c_node = _previousElement(self._c_node)
        if c_node:
            return _newReadOnlyProxy(self._source_proxy, c_node)
        return None


class _ReadOnlyPIProxy(_ReadOnlyProxy):
    u"A read-only proxy for processing instructions (for internal use only!)"
    @property
    def target(self):
        self._assertNode()
        return funicode(self._c_node.name)


class _ReadOnlyElementProxy(_ReadOnlyProxy):
    u"The main read-only Element proxy class (for internal use only!)."

    @property
    def attrib(self):
        self._assertNode()
        return dict(_collectAttributes(self._c_node, 3))

    @property
    def prefix(self):
        u"""Namespace prefix or None.
        """
        self._assertNode()
        if self._c_node.ns:
            if self._c_node.ns.prefix:
                return funicode(self._c_node.ns.prefix)
        return None

    def get(self, key, default=None):
        u"""Gets an element attribute.
        """
        self._assertNode()
        return _getNodeAttributeValue(self._c_node, key, default)

    def keys(self):
        u"""Gets a list of attribute names. The names are returned in an
        arbitrary order (just like for an ordinary Python dictionary).
        """
        self._assertNode()
        return _collectAttributes(self._c_node, 1)

    def values(self):
        u"""Gets element attributes, as a sequence. The attributes are returned
        in an arbitrary order.
        """
        self._assertNode()
        return _collectAttributes(self._c_node, 2)

    def items(self):
        u"""Gets element attributes, as a sequence. The attributes are returned
        in an arbitrary order.
        """
        self._assertNode()
        return _collectAttributes(self._c_node, 3)


def _newReadOnlyProxy(source_proxy, c_node):
    if c_node.type == tree.XML_ELEMENT_NODE:
        el = _ReadOnlyElementProxy.__new__(_ReadOnlyElementProxy)
    elif c_node.type == tree.XML_PI_NODE:
        el = _ReadOnlyPIProxy.__new__(_ReadOnlyPIProxy)
    elif c_node.type in (tree.XML_COMMENT_NODE,
                         tree.XML_ENTITY_REF_NODE):
        el = _ReadOnlyProxy.__new__(_ReadOnlyProxy)
    else:
        raise TypeError("Unsupported element type: %d" % c_node.type)
    el._c_node = c_node
    _initReadOnlyProxy(el, source_proxy)
    return el

def _initReadOnlyProxy(el, source_proxy):
    if source_proxy is None:
        el._source_proxy = el
        el._dependent_proxies = [el]
    else:
        el._source_proxy = source_proxy
        source_proxy._dependent_proxies.append(el)

def _freeReadOnlyProxies(sourceProxy):
    if sourceProxy is None:
        return
    if sourceProxy._dependent_proxies is None:
        return
    for el in sourceProxy._dependent_proxies:
        c_node = el._c_node
        el._c_node = ffi.NULL
        if el._free_after_use:
            tree.xmlFreeNode(c_node)
    del sourceProxy._dependent_proxies[:]

# opaque wrapper around non-element nodes, e.g. the document node
#
# This class does not imply any restrictions on modifiability or
# read-only status of the node, so use with caution.

class _OpaqueNodeWrapper(object):
    def __init__(self):
        raise TypeError, u"This type cannot be instantiated from Python"

class _OpaqueDocumentWrapper(_OpaqueNodeWrapper):
    def _assertNode(self):
        u"""This is our way of saying: this proxy is invalid!
        """
        assert self._c_node, u"Proxy invalidated!"
        return 0

    def append(self, other_element):
        u"""Append a copy of an Element to the list of children.
        """
        self._assertNode()
        c_node = _roNodeOf(other_element)
        if c_node.type == tree.XML_ELEMENT_NODE:
            if tree.xmlDocGetRootElement(ffi.cast("xmlDocPtr", self._c_node)):
                raise ValueError, u"cannot append, document already has a root element"
        elif c_node.type not in (tree.XML_PI_NODE, tree.XML_COMMENT_NODE):
            raise TypeError, u"unsupported element type for top-level node: %d" % c_node.type
        c_node = _copyNodeToDoc(c_node, ffi.cast("xmlDocPtr", self._c_node))
        c_next = c_node.next
        tree.xmlAddChild(self._c_node, c_node)
        _moveTail(c_next, c_node)

    def extend(self, elements):
        u"""Append a copy of all Elements from a sequence to the list of
        children.
        """
        self._assertNode()
        for element in elements:
            self.append(element)

def _newOpaqueAppendOnlyNodeWrapper(c_node):
    if c_node.type in (tree.XML_DOCUMENT_NODE, tree.XML_HTML_DOCUMENT_NODE):
        node = _OpaqueDocumentWrapper.__new__(_OpaqueDocumentWrapper)
    else:
        node = _OpaqueNodeWrapper.__new__(_OpaqueNodeWrapper)
    node._c_node = c_node
    return node

# element proxies that allow restricted modification

class _AppendOnlyElementProxy(_ReadOnlyElementProxy):
    u"""A read-only element that allows adding children and changing the
    text content (i.e. everything that adds to the subtree).
    """
    def append(self, other_element):
        u"""Append a copy of an Element to the list of children.
        """
        self._assertNode()
        c_node = _roNodeOf(other_element)
        c_node = _copyNodeToDoc(c_node, self._c_node.doc)
        c_next = c_node.next
        tree.xmlAddChild(self._c_node, c_node)
        _moveTail(c_next, c_node)

    def extend(self, elements):
        u"""Append a copy of all Elements from a sequence to the list of
        children.
        """
        self._assertNode()
        for element in elements:
            self.append(element)

    @property
    def text(self):
        u"""Text before the first subelement. This is either a string or the
        value None, if there was no text.
        """
        self._assertNode()
        return _collectText(self._c_node.children)
    @text.setter
    def text(self, value):
        self._assertNode()
        if isinstance(value, QName):
            value = _resolveQNameText(self, value).decode('utf8')
        _setNodeText(self._c_node, value)


def _newAppendOnlyProxy(source_proxy, c_node):
    if c_node.type == tree.XML_ELEMENT_NODE:
        el = _AppendOnlyElementProxy.__new__(_AppendOnlyElementProxy)
    elif c_node.type == tree.XML_PI_NODE:
        el = _ModifyContentOnlyPIProxy.__new__(_ModifyContentOnlyPIProxy)
    elif c_node.type == tree.XML_COMMENT_NODE:
        el = _ModifyContentOnlyProxy.__new__(_ModifyContentOnlyProxy)
    else:
        raise TypeError("Unsupported element type: %d" % c_node.type)
    el._c_node = c_node
    _initReadOnlyProxy(el, source_proxy)
    return el

def _roNodeOf(element):
    if isinstance(element, _Element):
        c_node = element._c_node
    elif isinstance(element, _ReadOnlyProxy):
        c_node = element._c_node
    elif isinstance(element, _OpaqueNodeWrapper):
        c_node = element._c_node
    else:
        raise TypeError, u"invalid argument type %s" % type(element)

    if not c_node:
        raise TypeError, u"invalid element"
    return c_node

def _nonRoNodeOf(element):
    if isinstance(element, _Element):
        c_node = element._c_node
    elif isinstance(element, _AppendOnlyElementProxy):
        c_node = element._c_node
    elif isinstance(element, _OpaqueNodeWrapper):
        c_node = element._c_node
    else:
        raise TypeError, u"invalid argument type %s" % type(element)

    if not c_node:
        raise TypeError, u"invalid element"
    return c_node
