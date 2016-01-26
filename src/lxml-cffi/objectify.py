u"""The ``lxml.objectify`` module implements a Python object API for
XML.  It is based on `lxml.etree`.
"""

import re

from .etree import ElementBase, ElementClassLookup, _Element
from .etree import _elementFactory as elementFactory
from .proxy import getProxy, detachProxy
from . import etree
from . import cetree
from . import python
from .cetree import textOf
from .includes import tree
from .includes.etree_defs import FOR_EACH_ELEMENT_FROM

IGNORABLE_ERRORS = (ValueError, TypeError)
is_special_method = re.compile(u'__.*__$').match

def _typename(t):
    return t.__class__.__name__.rsplit('.', 1)[-1]

TREE_PYTYPE_NAME = u"TREE"

def _unicodeAndUtf8(s):
    return s, s.encode('utf8')

def set_pytype_attribute_tag(attribute_tag=None):
    u"""set_pytype_attribute_tag(attribute_tag=None)
    Change name and namespace of the XML attribute that holds Python type
    information.

    Do not use this unless you know what you are doing.

    Reset by calling without argument.

    Default: "{http://codespeak.net/lxml/objectify/pytype}pytype"
    """
    global PYTYPE_ATTRIBUTE, _PYTYPE_NAMESPACE, _PYTYPE_ATTRIBUTE_NAME
    global PYTYPE_NAMESPACE, PYTYPE_NAMESPACE_UTF8
    global PYTYPE_ATTRIBUTE_NAME, PYTYPE_ATTRIBUTE_NAME_UTF8
    if attribute_tag is None:
        PYTYPE_NAMESPACE, PYTYPE_NAMESPACE_UTF8 = \
            _unicodeAndUtf8(u"http://codespeak.net/lxml/objectify/pytype")
        PYTYPE_ATTRIBUTE_NAME, PYTYPE_ATTRIBUTE_NAME_UTF8 = \
            _unicodeAndUtf8(u"pytype")
    else:
        PYTYPE_NAMESPACE_UTF8, PYTYPE_ATTRIBUTE_NAME_UTF8 = \
            cetree.getNsTag(attribute_tag)
        PYTYPE_NAMESPACE = PYTYPE_NAMESPACE_UTF8.decode('utf8')
        PYTYPE_ATTRIBUTE_NAME = PYTYPE_ATTRIBUTE_NAME_UTF8.decode('utf8')

    _PYTYPE_NAMESPACE      = PYTYPE_NAMESPACE_UTF8
    _PYTYPE_ATTRIBUTE_NAME = PYTYPE_ATTRIBUTE_NAME_UTF8
    PYTYPE_ATTRIBUTE = "{%s}%s" % (
        _PYTYPE_NAMESPACE, _PYTYPE_ATTRIBUTE_NAME)

set_pytype_attribute_tag()

XML_SCHEMA_NS, XML_SCHEMA_NS_UTF8 = \
    _unicodeAndUtf8(u"http://www.w3.org/2001/XMLSchema")

XML_SCHEMA_INSTANCE_NS, XML_SCHEMA_INSTANCE_NS_UTF8 = \
    _unicodeAndUtf8(u"http://www.w3.org/2001/XMLSchema-instance")
_XML_SCHEMA_INSTANCE_NS = XML_SCHEMA_INSTANCE_NS_UTF8

XML_SCHEMA_INSTANCE_NIL_ATTR = u"{%s}nil" % XML_SCHEMA_INSTANCE_NS
XML_SCHEMA_INSTANCE_TYPE_ATTR = u"{%s}type" % XML_SCHEMA_INSTANCE_NS

################################################################################
# Element class for the main API

class ObjectifiedElement(ElementBase):
    u"""Main XML Element class.

    Element children are accessed as object attributes.  Multiple children
    with the same name are available through a list index.  Example::

       >>> root = XML("<root><c1><c2>0</c2><c2>1</c2></c1></root>")
       >>> second_c2 = root.c1.c2[1]
       >>> print(second_c2.text)
       1

    Note that you cannot (and must not) instantiate this class or its
    subclasses.
    """
    def __str__(self):
        if _RECURSIVE_STR:
            return _dump(self, 0)
        else:
            return textOf(self._c_node) or u''

    # pickle support for objectified Element
    def __reduce__(self):
        return (fromstring, (etree.tostring(self),))

    @property
    def __dict__(self):
        u"""A fake implementation for __dict__ to support dir() etc.

        Note that this only considers the first child with a given name.
        """
        c_ns = cetree._getNs(self._c_node)
        tag = u"{%s}*" % tree.ffi.string(c_ns) if c_ns else None
        children = {}
        for child in etree.ElementChildIterator(self, tag=tag):
            if not c_ns and cetree._getNs(child._c_node):
                continue
            name = tree.ffi.string(child._c_node.name)
            if name not in children:
                children[name] = child
        return children

    def __len__(self):
        u"""Count self and siblings with the same tag.
        """
        return _countSiblings(self._c_node)

    def countchildren(self):
        u"""countchildren(self)

        Return the number of children of this element, regardless of their
        name.
        """
        # copied from etree
        c = 0
        c_node = self._c_node.children
        while c_node:
            if cetree._isElement(c_node):
                c = c + 1
            c_node = c_node.next
        return c

    def __getattr__(self, tag):
        u"""Return the (first) child with the given tag name.  If no namespace
        is provided, the child will be looked up in the same one as self.
        """
        if is_special_method(tag):
            return object.__getattr__(self, tag)
        return _lookupChildOrRaise(self, tag)

    def __setattr__(self, tag, value):
        u"""Set the value of the (first) child with the given tag name.  If no
        namespace is provided, the child will be looked up in the same one as
        self.
        """
        # XXX AFA interp_level object members!
        if tag.startswith('_'):
            object.__setattr__(self, tag, value)
            return
        # properties are looked up /after/ __setattr__, so we must emulate them
        if tag == u'text' or tag == u'pyval':
            # read-only !
            raise TypeError, u"attribute '%s' of '%s' objects is not writable" % \
                            (tag, _typename(self))
        elif tag == u'tail':
            cetree.setTailText(self._c_node, value)
            return
        elif tag == u'tag':
            ElementBase.tag.__set__(self, value)
            return
        elif tag == u'base':
            ElementBase.base.__set__(self, value)
            return
        tag = _buildChildTag(self, tag)
        element = _lookupChild(self, tag)
        if element is None:
            _appendValue(self, tag, value)
        else:
            _replaceElement(element, value)

    def __delattr__(self, tag):
        # XXX AFA interp_level object members!
        if tag.startswith('_'):
            object.__delattr__(self, tag)
            return
        child = _lookupChildOrRaise(self, tag)
        self.remove(child)

    def addattr(self, tag, value):
        u"""addattr(self, tag, value)

        Add a child value to the element.

        As opposed to append(), it sets a data value, not an element.
        """
        _appendValue(self, _buildChildTag(self, tag), value)

    def __getitem__(self, key):
        u"""Return a sibling, counting from the first child of the parent.  The
        method behaves like both a dict and a sequence.

        * If argument is an integer, returns the sibling at that position.

        * If argument is a string, does the same as getattr().  This can be
          used to provide namespaces for element lookup, or to look up
          children with special names (``text`` etc.).

        * If argument is a slice object, returns the matching slice.
        """
        if python._isString(key):
            return _lookupChildOrRaise(self, key)
        elif isinstance(key, slice):
            return list(self)[key]
        # normal item access
        c_index = key   # raises TypeError if necessary
        c_self_node = self._c_node
        c_parent = c_self_node.parent
        if not c_parent:
            if c_index == 0:
                return self
            else:
                raise IndexError, unicode(key)
        if c_index < 0:
            c_node = c_parent.last
        else:
            c_node = c_parent.children
        c_node = _findFollowingSibling(
            c_node, cetree._getNs(c_self_node), c_self_node.name, c_index)
        if not c_node:
            raise IndexError, unicode(key)
        return elementFactory(self._doc, c_node)

    def __setitem__(self, key, value):
        u"""Set the value of a sibling, counting from the first child of the
        parent.  Implements key assignment, item assignment and slice
        assignment.

        * If argument is an integer, sets the sibling at that position.

        * If argument is a string, does the same as setattr().  This is used
          to provide namespaces for element lookup.

        * If argument is a sequence (list, tuple, etc.), assign the contained
          items to the siblings.
        """
        if python._isString(key):
            key = _buildChildTag(self, key)
            element = _lookupChild(self, key)
            if element is None:
                _appendValue(self, key, value)
            else:
                _replaceElement(element, value)
            return

        if not self._c_node.parent:
            # the 'root[i] = ...' case
            raise TypeError, u"assignment to root element is invalid"

        if isinstance(key, slice):
            # slice assignment
            _setSlice(key, self, value)
        else:
            # normal index assignment
            if key < 0:
                c_node = self._c_node.parent.last
            else:
                c_node = self._c_node.parent.children
            c_node = _findFollowingSibling(
                c_node, cetree._getNs(self._c_node), self._c_node.name, key)
            if not c_node:
                raise IndexError, unicode(key)
            element = elementFactory(self._doc, c_node)
            _replaceElement(element, value)

    def __delitem__(self, key):
        parent = self.getparent()
        if parent is None:
            raise TypeError, u"deleting items not supported by root element"
        if isinstance(key, slice):
            # slice deletion
            del_items = list(self)[key]
            remove = parent.remove
            for el in del_items:
                remove(el)
        else:
            # normal index deletion
            sibling = self.__getitem__(key)
            parent.remove(sibling)

    def descendantpaths(self, prefix=None):
        u"""descendantpaths(self, prefix=None)

        Returns a list of object path expressions for all descendants.
        """
        if prefix is not None and not python._isString(prefix):
            prefix = u'.'.join(prefix)
        return _buildDescendantPaths(self._c_node, prefix)

def _tagMatches(c_node, c_href, c_name):
    if c_node.name != c_name:
        return 0
    if c_href == tree.ffi.NULL:
        return 1
    c_node_href = cetree._getNs(c_node)
    if c_node_href == tree.ffi.NULL:
        return c_href == ''
    return tree.xmlStrcmp(c_node_href, c_href) == 0

def _countSiblings(c_start_node):
    c_tag  = c_start_node.name
    c_href = cetree._getNs(c_start_node)
    count = 1
    c_node = c_start_node.next
    while c_node:
        if c_node.type == tree.XML_ELEMENT_NODE and \
               _tagMatches(c_node, c_href, c_tag):
            count += 1
        c_node = c_node.next
    c_node = c_start_node.prev
    while c_node:
        if c_node.type == tree.XML_ELEMENT_NODE and \
               _tagMatches(c_node, c_href, c_tag):
            count += 1
        c_node = c_node.prev
    return count

def _findFollowingSibling(c_node, href, name, index):
    if index >= 0:
        next = cetree.nextElement
    else:
        index = -1 - index
        next = cetree.previousElement
    while c_node:
        if c_node.type == tree.XML_ELEMENT_NODE and \
               _tagMatches(c_node, href, name):
            index = index - 1
            if index < 0:
                return c_node
        c_node = next(c_node)
    return tree.ffi.NULL

def _findFollowingSibling(c_node, href, name, index):
    if index >= 0:
        next = cetree.nextElement
    else:
        index = -1 - index
        next = cetree.previousElement
    while c_node:
        if c_node.type == tree.XML_ELEMENT_NODE and \
               _tagMatches(c_node, href, name):
            index = index - 1
            if index < 0:
                return c_node
        c_node = next(c_node)
    return tree.ffi.NULL

def _lookupChild(parent, tag):
    c_node = parent._c_node
    ns, tag = cetree.getNsTagWithEmptyNs(tag)
    c_tag = tree.xmlDictExists(
        c_node.doc.dict, tag, len(tag))
    if not c_tag:
        return None # not in the hash map => not in the tree
    if ns is None:
        # either inherit ns from parent or use empty (i.e. no) namespace
        c_href = cetree._getNs(c_node) or ''
    else:
        c_href = ns
    c_result = _findFollowingSibling(c_node.children, c_href, c_tag, 0)
    if not c_result:
        return None
    return elementFactory(parent._doc, c_result)

def _lookupChildOrRaise(parent, tag):
    element = _lookupChild(parent, tag)
    if element is None:
        raise AttributeError, \
            u"no such child: " + _buildChildTag(parent, tag)
    return element

def _buildChildTag(parent, tag):
    ns, tag = cetree.getNsTag(tag)
    c_tag = tree.ffi.new('char[]', tag)
    c_href = cetree._getNs(parent._c_node) if ns is None else tree.ffi.new('char[]', ns)
    return cetree.namespacedNameFromNsName(c_href, c_tag)

def _replaceElement(element, value):
    if isinstance(value, _Element):
        # deep copy the new element
        new_element = cetree.deepcopyNodeToDocument(
            element._doc, value._c_node)
        new_element.tag = element.tag
    elif isinstance(value, (list, tuple)):
        element[:] = value
        return
    else:
        new_element = element.makeelement(element.tag)
        _setElementValue(new_element, value)
    element.getparent().replace(element, new_element)
    detachProxy(new_element)

def _appendValue(parent, tag, value):
    if isinstance(value, _Element):
        # deep copy the new element
        new_element = cetree.deepcopyNodeToDocument(
            parent._doc, value._c_node)
        new_element.tag = tag
        cetree.appendChildToElement(parent, new_element)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _appendValue(parent, tag, item)
    else:
        new_element = cetree.makeElement(
            tag, None, parent._doc, None, None, None, None, None, None)
        _setElementValue(new_element, value)
        cetree.appendChildToElement(parent, new_element)
        detachProxy(new_element)

def _setElementValue(element, value):
    if value is None:
        cetree.setAttributeValue(
            element, XML_SCHEMA_INSTANCE_NIL_ATTR, u"true")
    elif isinstance(value, _Element):
        _replaceElement(element, value)
        return
    else:
        cetree.delAttributeFromNsName(
            element._c_node, _XML_SCHEMA_INSTANCE_NS, "nil")
        if python._isString(value):
            pytype_name = u"str"
            _pytype = _PYTYPE_DICT.get(pytype_name)
        else:
            pytype_name = _typename(value)
            _pytype = _PYTYPE_DICT.get(pytype_name)
            if _pytype is not None:
                value = _pytype.stringify(value)
            else:
                value = unicode(value)
        if _pytype is not None:
            cetree.setAttributeValue(element, PYTYPE_ATTRIBUTE, pytype_name)
        else:
            cetree.delAttributeFromNsName(
                element._c_node, _PYTYPE_NAMESPACE, _PYTYPE_ATTRIBUTE_NAME)
    cetree.setNodeText(element._c_node, value)

def _setSlice(sliceobject, target, items):
    # collect existing slice
    if sliceobject.step is None:
        c_step = 1
    else:
        c_step = sliceobject.step
    if c_step == 0:
        raise ValueError, u"Invalid slice"
    del_items = target[sliceobject]

    # collect new values
    new_items = []
    tag = target.tag
    for item in items:
        if isinstance(item, _Element):
            # deep copy the new element
            new_element = cetree.deepcopyNodeToDocument(
                target._doc, item._c_node)
            new_element.tag = tag
        else:
            new_element = cetree.makeElement(
                tag, None, target._doc, None, None, None, None, None, None)
            _setElementValue(new_element, item)
        new_items.append(new_element)

    # sanity check - raise what a list would raise
    if c_step != 1 and \
            len(del_items) != len(new_items):
        raise ValueError, \
            u"attempt to assign sequence of size %d to extended slice of size %d" % (
            len(new_items),
            len(del_items))

    # replace existing items
    pos = 0
    parent = target.getparent()
    replace = parent.replace
    while pos < len(new_items) and \
            pos < len(del_items):
        replace(del_items[pos], new_items[pos])
        pos += 1
    # remove leftover items
    if pos < len(del_items):
        remove = parent.remove
        while pos < len(del_items):
            remove(del_items[pos])
            pos += 1
    # append remaining new items
    if pos < len(new_items):
        # the sanity check above guarantees (step == 1)
        if pos > 0:
            item = new_items[pos-1]
        else:
            if sliceobject.start > 0:
                c_node = parent._c_node.children
            else:
                c_node = parent._c_node.last
            c_node = _findFollowingSibling(
                c_node, cetree._getNs(target._c_node), target._c_node.name,
                sliceobject.start - 1)
            if not c_node:
                while pos < len(new_items):
                    cetree.appendChildToElement(parent, new_items[pos])
                    detachProxy(new_items[pos])
                    pos += 1
                return
            item = cetree.elementFactory(parent._doc, c_node)
        while pos < len(new_items):
            add = item.addnext
            item = new_items[pos]
            add(item)
            pos += 1
    for new_item in new_items:
        detachProxy(new_item)

################################################################################
# Data type support in subclasses

class ObjectifiedDataElement(ObjectifiedElement):
    u"""This is the base class for all data type Elements.  Subclasses should
    override the 'pyval' property and possibly the __str__ method.
    """
    @property
    def pyval(self):
        return textOf(self._c_node)

    def __str__(self):
        return textOf(self._c_node) or u''


class NumberElement(ObjectifiedDataElement):
    def _setValueParser(self, function):
        u"""Set the function that parses the Python value from a string.

        Do not use this unless you know what you are doing.
        """
        self._parse_value = function

    @property
    def pyval(self):
        return _parseNumber(self)

    def __int__(self):
        return int(_parseNumber(self))

    def __long__(self):
        return long(_parseNumber(self))

    def __float__(self):
        return float(_parseNumber(self))

    def __complex__(self):
        return complex(_parseNumber(self))

    def __str__(self):
        return unicode(_parseNumber(self))

    def __repr__(self):
        return repr(_parseNumber(self))

    def __oct__(self):
        return oct(_parseNumber(self))

    def __hex__(self):
        return hex(_parseNumber(self))

    def __cmp__(self, other):
        return _cmpPyvals(self, other)

    def __hash__(self):
        return hash(_parseNumber(self))

    def __add__(self, other):
        return _numericValueOf(self) + _numericValueOf(other)

    def __radd__(self, other):
        return _numericValueOf(other) + _numericValueOf(self)

    def __sub__(self, other):
        return _numericValueOf(self) - _numericValueOf(other)

    def __rsub__(self, other):
        return _numericValueOf(other) - _numericValueOf(self)

    def __mul__(self, other):
        return _numericValueOf(self) * _numericValueOf(other)

    def __div__(self, other):
        return _numericValueOf(self) / _numericValueOf(other)

    def __truediv__(self, other):
        return _numericValueOf(self) / _numericValueOf(other)

    def __mod__(self, other):
        return _numericValueOf(self) % _numericValueOf(other)

    def __pow__(self, other, modulo):
        if modulo is None:
            return _numericValueOf(self) ** _numericValueOf(other)
        else:
            return pow(_numericValueOf(self), _numericValueOf(other), modulo)

    def __neg__(self):
        return - _numericValueOf(self)

    def __pos__(self):
        return + _numericValueOf(self)

    def __abs__(self):
        return abs( _numericValueOf(self) )

    def __nonzero__(self):
        return bool(_numericValueOf(self))

    def __invert__(self):
        return ~ _numericValueOf(self)

    def __lshift__(self, other):
        return _numericValueOf(self) << _numericValueOf(other)

    def __rshift__(self, other):
        return _numericValueOf(self) >> _numericValueOf(other)

    def __and__(self, other):
        return _numericValueOf(self) & _numericValueOf(other)

    def __or__(self, other):
        return _numericValueOf(self) | _numericValueOf(other)

    def __xor__(self, other):
        return _numericValueOf(self) ^ _numericValueOf(other)

class IntElement(NumberElement):
    def _init(self):
        self._parse_value = int

class FloatElement(NumberElement):
    def _init(self):
        self._parse_value = float

class StringElement(ObjectifiedDataElement):
    u"""String data class.

    Note that this class does *not* support the sequence protocol of strings:
    len(), iter(), str_attr[0], str_attr[0:1], etc. are *not* supported.
    Instead, use the .text attribute to get a 'real' string.
    """
    @property
    def pyval(self):
        return textOf(self._c_node) or u''

    def __repr__(self):
        return repr(textOf(self._c_node) or u'')

    def strlen(self):
        text = textOf(self._c_node)
        if text is None:
            return 0
        else:
            return len(text)

    def __nonzero__(self):
        return bool(textOf(self._c_node))

    def __cmp__(self, other):
        return _cmpPyvals(self, other)

    def __hash__(self):
        return hash(textOf(self._c_node) or u'')

    def __add__(self, other):
        text  = _strValueOf(self)
        other = _strValueOf(other)
        if text is None:
            return other
        if other is None:
            return text
        return text + other

    def __radd__(self, other):
        text  = _strValueOf(self)
        other = _strValueOf(other)
        if text is None:
            return other
        if other is None:
            return text
        return other + text

    def __mul__(self, other):
        return textOf(self._c_node) * _numericValueOf(other)
    __rmul__ = __mul__

    def __mod__(self, other):
        return _strValueOf(self) % other

    def __int__(self):
        return int(textOf(self._c_node))

    def __long__(self):
        return long(textOf(self._c_node))

    def __float__(self):
        return float(textOf(self._c_node))

    def __complex__(self):
        return complex(textOf(self._c_node))


class NoneElement(ObjectifiedDataElement):
    def __str__(self):
        return u"None"

    def __repr__(self):
        return u"None"

    def __nonzero__(self):
        return False

    def __cmp__(self, other):
        return cmp(None, other)

    def __hash__(self):
        return hash(None)

    @property
    def pyval(self):
        return None

class BoolElement(IntElement):
    u"""Boolean type base on string values: 'true' or 'false'.

    Note that this inherits from IntElement to mimic the behaviour of
    Python's bool type.
    """
    def _init(self):
        self._parse_value = _parseBool

    def __nonzero__(self):
        return _parseBool(textOf(self._c_node))

    def __cmp__(self, other):
        return _cmpPyvals(self, other)

    def __hash__(self):
        return hash(_parseBool(textOf(self._c_node)))

    def __str__(self):
        return unicode(_parseBool(textOf(self._c_node)))

    def __repr__(self):
        return repr(_parseBool(textOf(self._c_node)))

    @property
    def pyval(self):
        return _parseBool(textOf(self._c_node))

def __checkBool(s):
    value = -1
    if s is not None:
        value = _parseBoolAsInt(s)
    if value == -1:
        raise ValueError

def _parseBool(s):
    if s is None:
        return False
    value = _parseBoolAsInt(s)
    if value == -1:
        raise ValueError, u"Invalid boolean value: '%s'" % s
    return bool(value)

def _parseBoolAsInt(text):
    if text == 'false':
        return 0
    elif text == 'true':
        return 1
    elif text == '0':
        return 0
    elif text == '1':
        return 1
    return -1

def _strValueOf(obj):
    if python._isString(obj):
        return obj
    if isinstance(obj, _Element):
        return textOf(obj._c_node) or u''
    if obj is None:
        return u''
    return unicode(obj)

def _numericValueOf(obj):
    if isinstance(obj, NumberElement):
        return _parseNumber(obj)
    try:
        # not always numeric, but Python will raise the right exception
        return obj.pyval
    except AttributeError:
        pass
    return obj

def _parseNumber(element):
    return element._parse_value(textOf(element._c_node))

def _cmpPyvals(left, right):
    left  = getattr(left,  'pyval', left)
    right = getattr(right, 'pyval', right)
    return cmp(left, right)


################################################################################
# Python type registry

class PyType(object):
    u"""PyType(self, name, type_check, type_class, stringify=None)
    User defined type.

    Named type that contains a type check function and a type class that
    inherits from ObjectifiedDataElement.  The type check must take a string
    as argument and raise ValueError or TypeError if it cannot handle the
    string value.  It may be None in which case it is not considered for type
    guessing.

    Example::

        PyType('int', int, MyIntClass).register()

    Note that the order in which types are registered matters.  The first
    matching type will be used.
    """
    def __init__(self, name, type_check, type_class, stringify=None):
        if isinstance(name, bytes):
            name = name.decode('ascii')
        elif not isinstance(name, unicode):
            raise TypeError, u"Type name must be a string"
        if type_check is not None and not callable(type_check):
            raise TypeError, u"Type check function must be callable (or None)"
        if name != TREE_PYTYPE_NAME and \
               not issubclass(type_class, ObjectifiedDataElement):
            raise TypeError, \
                u"Data classes must inherit from ObjectifiedDataElement"
        self.name  = name
        self._type = type_class
        self.type_check = type_check
        if stringify is None:
            stringify = unicode
        self.stringify = stringify
        self._schema_types = []

    def __repr__(self):
        return u"PyType(%s, %s)" % (self.name, self._type.__name__)

    def register(self, before=None, after=None):
        u"""register(self, before=None, after=None)

        Register the type.

        The additional keyword arguments 'before' and 'after' accept a
        sequence of type names that must appear before/after the new type in
        the type list.  If any of them is not currently known, it is simply
        ignored.  Raises ValueError if the dependencies cannot be fulfilled.
        """
        if self.name == TREE_PYTYPE_NAME:
            raise ValueError, u"Cannot register tree type"
        if self.type_check is not None:
            for item in _TYPE_CHECKS:
                if item[0] is self.type_check:
                    _TYPE_CHECKS.remove(item)
                    break
            entry = (self.type_check, self)
            first_pos = 0
            last_pos = -1
            if before or after:
                if before is None:
                    before = ()
                elif after is None:
                    after = ()
                for i, (check, pytype) in enumerate(_TYPE_CHECKS):
                    if last_pos == -1 and pytype.name in before:
                        last_pos = i
                    if pytype.name in after:
                        first_pos = i+1
            if last_pos == -1:
                _TYPE_CHECKS.append(entry)
            elif first_pos > last_pos:
                raise ValueError, u"inconsistent before/after dependencies"
            else:
                _TYPE_CHECKS.insert(last_pos, entry)

        _PYTYPE_DICT[self.name] = self
        for xs_type in self._schema_types:
            _SCHEMA_TYPE_DICT[xs_type] = self

    def unregister(self):
        u"unregister(self)"
        if _PYTYPE_DICT.get(self.name) is self:
            del _PYTYPE_DICT[self.name]
        for xs_type, pytype in list(_SCHEMA_TYPE_DICT.items()):
            if pytype is self:
                del _SCHEMA_TYPE_DICT[xs_type]
        if self.type_check is None:
            return
        try:
            _TYPE_CHECKS.remove( (self.type_check, self) )
        except ValueError:
            pass

    @property
    def xmlSchemaTypes(self):
        u"""The list of XML Schema datatypes this Python type maps to.

        Note that this must be set before registering the type!
        """
        return self._schema_types
    @xmlSchemaTypes.setter
    def xmlSchemaTypes(self, types):
        self._schema_types = list(map(unicode, types))


_PYTYPE_DICT = {}
_SCHEMA_TYPE_DICT = {}
_TYPE_CHECKS = []

def _lower_bool(b):
    return u"true" if b else u"false"

def __lower_bool(b):
    return _lower_bool(b)

def _pytypename(obj):
    return u"str" if python._isString(obj) else _typename(obj)

def pytypename(obj):
    u"""pytypename(obj)

    Find the name of the corresponding PyType for a Python object.
    """
    return _pytypename(obj)

def _registerPyTypes():
    pytype = PyType(u'int', int, IntElement)
    pytype.xmlSchemaTypes = (u"integer", u"int", u"short", u"byte", u"unsignedShort",
                             u"unsignedByte", u"nonPositiveInteger",
                             u"negativeInteger", u"long", u"nonNegativeInteger",
                             u"unsignedLong", u"unsignedInt", u"positiveInteger",)
    pytype.register()

    # 'long' type just for backwards compatibility
    pytype = PyType(u'long', None, IntElement)
    pytype.register()

    pytype = PyType(u'float', float, FloatElement)
    pytype.xmlSchemaTypes = (u"double", u"float")
    pytype.register()

    pytype = PyType(u'bool', __checkBool, BoolElement, __lower_bool)
    pytype.xmlSchemaTypes = (u"boolean",)
    pytype.register()

    pytype = PyType(u'str', None, StringElement)
    pytype.xmlSchemaTypes = (u"string", u"normalizedString", u"token", u"language",
                             u"Name", u"NCName", u"ID", u"IDREF", u"ENTITY",
                             u"NMTOKEN", )
    pytype.register()

    # since lxml 2.0
    pytype = PyType(u'NoneType', None, NoneElement)
    pytype.register()

    # backwards compatibility
    pytype = PyType(u'none', None, NoneElement)
    pytype.register()

# non-registered PyType for inner tree elements
TREE_PYTYPE = PyType(TREE_PYTYPE_NAME, None, ObjectifiedElement)

_registerPyTypes()

def getRegisteredTypes():
    u"""getRegisteredTypes()

    Returns a list of the currently registered PyType objects.

    To add a new type, retrieve this list and call unregister() for all
    entries.  Then add the new type at a suitable position (possibly replacing
    an existing one) and call register() for all entries.

    This is necessary if the new type interferes with the type check functions
    of existing ones (normally only int/float/bool) and must the tried before
    other types.  To add a type that is not yet parsable by the current type
    check functions, you can simply register() it, which will append it to the
    end of the type list.
    """
    types = []
    known = set()
    for check, pytype in _TYPE_CHECKS:
        name = pytype.name
        if name not in known:
            known.add(name)
            types.append(pytype)
    for pytype in _PYTYPE_DICT.values():
        name = pytype.name
        if name not in known:
            known.add(name)
            types.append(pytype)
    return types

def _guessPyType(value, defaulttype):
    if value is None:
        return None
    for type_check, tested_pytype in _TYPE_CHECKS:
        try:
            type_check(value)
            return tested_pytype
        except IGNORABLE_ERRORS:
            # could not be parsed as the specified type => ignore
            pass
    return defaulttype

def _guessElementClass(c_node):
    value = textOf(c_node)
    if value is None:
        return None
    if value == '':
        return StringElement

    for type_check, pytype in _TYPE_CHECKS:
        try:
            type_check(value)
            return pytype._type
        except IGNORABLE_ERRORS:
            pass
    return None

################################################################################
# adapted ElementMaker supports registered PyTypes

class _ObjectifyElementMakerCaller(object):
    def __call__(self, *children, **attrib):
        u"__call__(self, *children, **attrib)"
        if self._element_factory is None:
            element = _makeElement(self._tag, None, attrib, self._nsmap)
        else:
            element = self._element_factory(self._tag, attrib, self._nsmap)

        pytype_name = None
        has_children = 0
        has_string_value = 0
        for child in children:
            if child is None:
                if len(children) == 1:
                    cetree.setAttributeValue(
                        element, XML_SCHEMA_INSTANCE_NIL_ATTR, u"true")
            elif python._isString(child):
                _add_text(element, child)
                has_string_value = 1
            elif isinstance(child, _Element):
                cetree.appendChildToElement(element, child)
                detachProxy(child)
                has_children = 1
            elif isinstance(child, _ObjectifyElementMakerCaller):
                elementMaker = child
                if elementMaker._element_factory is None:
                    cetree.makeSubElement(element, elementMaker._tag,
                                          None, None, None, None, None)
                else:
                    childElement = elementMaker._element_factory(
                        elementMaker._tag)
                    cetree.appendChildToElement(element, childElement)
                has_children = 1
            elif isinstance(child, dict):
                for name, value in child.items():
                    # keyword arguments in attrib take precedence
                    if name in attrib:
                        continue
                    pytype = _PYTYPE_DICT.get(_typename(value))
                    if pytype is not None:
                        value = pytype.stringify(value)
                    elif not python._isString(value):
                        value = unicode(value)
                    cetree.setAttributeValue(element, name, value)
            else:
                if pytype_name is not None:
                    # concatenation always makes the result a string
                    has_string_value = 1
                pytype_name = _typename(child)
                pytype = _PYTYPE_DICT.get(pytype_name)
                if pytype is not None:
                    _add_text(element, pytype.stringify(child))
                else:
                    has_string_value = 1
                    child = unicode(child)
                    _add_text(element, child)

        if self._annotate and not has_children:
            if has_string_value:
                cetree.setAttributeValue(element, PYTYPE_ATTRIBUTE, u"str")
            elif pytype_name is not None:
                cetree.setAttributeValue(element, PYTYPE_ATTRIBUTE, pytype_name)

        return element

def _add_text(elem, text):
    # add text to the tree in construction, either as element text or
    # tail text, depending on the current tree state
    c_child = cetree.findChildBackwards(elem._c_node, 0)
    if c_child:
        old = cetree.tailOf(c_child)
        if old is not None:
            text = old + text
        cetree.setTailText(c_child, text)
    else:
        old = cetree.textOf(elem._c_node)
        if old is not None:
            text = old + text
        cetree.setNodeText(elem._c_node, text)

class ElementMaker(object):
    u"""ElementMaker(self, namespace=None, nsmap=None, annotate=True, makeelement=None)

    An ElementMaker that can be used for constructing trees.

    Example::

      >>> M = ElementMaker(annotate=False)
      >>> attributes = {'class': 'par'}
      >>> html = M.html( M.body( M.p('hello', attributes, M.br, 'objectify', style="font-weight: bold") ) )

      >>> from lxml.etree import tostring
      >>> print(tostring(html, method='html').decode('ascii'))
      <html><body><p style="font-weight: bold" class="par">hello<br>objectify</p></body></html>

    To create tags that are not valid Python identifiers, call the factory
    directly and pass the tag name as first argument::

      >>> root = M('tricky-tag', 'some text')
      >>> print(root.tag)
      tricky-tag
      >>> print(root.text)
      some text

    Note that this module has a predefined ElementMaker instance called ``E``.
    """
    def __init__(self, namespace=None, nsmap=None, annotate=True,
                 makeelement=None):
        if nsmap is None:
            nsmap = _DEFAULT_NSMAP if annotate else {}
        self._nsmap = nsmap
        self._namespace = None if namespace is None else u"{%s}" % namespace
        self._annotate = annotate
        if makeelement is not None:
            assert callable(makeelement)
            self._makeelement = makeelement
        else:
            self._makeelement = None
        self._cache = {}

    def _build_element_maker(self, tag):
        element_maker = _ObjectifyElementMakerCaller.__new__(_ObjectifyElementMakerCaller)
        if self._namespace is not None and tag[0] != u"{":
            element_maker._tag = self._namespace + tag
        else:
            element_maker._tag = tag
        element_maker._nsmap = self._nsmap
        element_maker._annotate = self._annotate
        element_maker._element_factory = self._makeelement
        if len(self._cache) > 200:
            self._cache.clear()
        self._cache[tag] = element_maker
        return element_maker

    def __getattr__(self, tag):
        element_maker = self._cache.get(tag, None)
        if element_maker is None:
            if is_special_method(tag):
                return object.__getattr__(self, tag)
            return self._build_element_maker(tag)
        return element_maker

    def __call__(self, tag, *args, **kwargs):
        element_maker = self._cache.get(tag, None)
        if element_maker is None:
            element_maker = self._build_element_maker(tag)
        return element_maker(*args, **kwargs)


################################################################################
# Recursive element dumping

_RECURSIVE_STR = 0 # default: off

def enable_recursive_str(on=True):
    u"""enable_recursive_str(on=True)

    Enable a recursively generated tree representation for str(element),
    based on objectify.dump(element).
    """
    global _RECURSIVE_STR
    _RECURSIVE_STR = on

def dump(element):
    u"""dump(_Element element not None)

    Return a recursively generated string representation of an element.
    """
    return _dump(element, 0)

def _dump(element, indent):
    indentstr = u"    " * indent
    if isinstance(element, ObjectifiedDataElement):
        value = repr(element)
    else:
        value = textOf(element._c_node)
        if value is not None:
            if not value.strip():
                value = None
            else:
                value = repr(value)
    result = u"%s%s = %s [%s]\n" % (indentstr, element.tag,
                                    value, _typename(element))
    xsi_ns    = u"{%s}" % XML_SCHEMA_INSTANCE_NS
    pytype_ns = u"{%s}" % PYTYPE_NAMESPACE
    for name, value in cetree.iterattributes(element, 3):
        if u'{' in name:
            if name == PYTYPE_ATTRIBUTE:
                if value == TREE_PYTYPE_NAME:
                    continue
                else:
                    name = name.replace(pytype_ns, u'py:')
            name = name.replace(xsi_ns, u'xsi:')
        result += u"%s  * %s = %r\n" % (indentstr, name, value)

    indent += 1
    for child in element.iterchildren():
        result += _dump(child, indent)
    if indent == 1:
        return result[:-1] # strip last '\n'
    else:
        return result


################################################################################
# Pickle support for objectified ElementTree

def __unpickleElementTree(data):
    return etree.ElementTree(fromstring(data))

def _setupPickle(elementTreeReduceFunction):
    if python.IS_PYTHON3:
        import copyreg
    else:
        import copy_reg as copyreg
    copyreg.pickle(etree._ElementTree,
                   elementTreeReduceFunction, __unpickleElementTree)

def pickleReduceElementTree(obj):
    return (__unpickleElementTree, (etree.tostring(obj),))

_setupPickle(pickleReduceElementTree)
del pickleReduceElementTree

################################################################################
# Element class lookup

class ObjectifyElementClassLookup(ElementClassLookup):
    u"""ObjectifyElementClassLookup(self, tree_class=None, empty_data_class=None)
    Element class lookup method that uses the objectify classes.
    """
    def __init__(self, tree_class=None, empty_data_class=None):
        u"""Lookup mechanism for objectify.

        The default Element classes can be replaced by passing subclasses of
        ObjectifiedElement and ObjectifiedDataElement as keyword arguments.
        'tree_class' defines inner tree classes (defaults to
        ObjectifiedElement), 'empty_data_class' defines the default class for
        empty data elements (defauls to StringElement).
        """
        self._lookup_function = _lookupElementClass
        if tree_class is None:
            tree_class = ObjectifiedElement
        self.tree_class = tree_class
        if empty_data_class is None:
            empty_data_class = StringElement
        self.empty_data_class = empty_data_class

def _lookupElementClass(state, doc, c_node):
    lookup = state
    # if element has children => no data class
    if cetree.hasChild(c_node):
        return lookup.tree_class

    # if element is defined as xsi:nil, return NoneElement class
    if u"true" == cetree.attributeValueFromNsName(
        c_node, _XML_SCHEMA_INSTANCE_NS, "nil"):
        return NoneElement

    # check for Python type hint
    value = cetree.attributeValueFromNsName(
        c_node, _PYTYPE_NAMESPACE, _PYTYPE_ATTRIBUTE_NAME)
    if value is not None:
        if value == TREE_PYTYPE_NAME:
            return lookup.tree_class
        dict_result = _PYTYPE_DICT.get(value)
        if dict_result is not None:
            return dict_result._type
        # unknown 'pyval' => try to figure it out ourself, just go on

    # check for XML Schema type hint
    value = cetree.attributeValueFromNsName(
        c_node, _XML_SCHEMA_INSTANCE_NS, "type")

    if value is not None:
        dict_result = _SCHEMA_TYPE_DICT.get(value)
        if dict_result is None and u':' in value:
            prefix, value = value.split(u':', 1)
            dict_result = _SCHEMA_TYPE_DICT.get(value)
        if dict_result is not None:
            return dict_result._type

    # otherwise determine class based on text content type
    el_class = _guessElementClass(c_node)
    if el_class is not None:
        return el_class

    # if element is a root node => default to tree node
    if not c_node.parent or not cetree._isElement(c_node.parent):
        return lookup.tree_class

    return lookup.empty_data_class

################################################################################
# Type annotations

def _check_type(c_node, pytype):
    if pytype is None:
        return None
    value = textOf(c_node)
    try:
        pytype.type_check(value)
        return pytype
    except IGNORABLE_ERRORS:
        # could not be parsed as the specified type => ignore
        pass
    return None

def pyannotate(element_or_tree, ignore_old=False, ignore_xsi=False,
               empty_pytype=None):
    u"""pyannotate(element_or_tree, ignore_old=False, ignore_xsi=False, empty_pytype=None)

    Recursively annotates the elements of an XML tree with 'pytype'
    attributes.

    If the 'ignore_old' keyword argument is True (the default), current 'pytype'
    attributes will be ignored and replaced.  Otherwise, they will be checked
    and only replaced if they no longer fit the current text value.

    Setting the keyword argument ``ignore_xsi`` to True makes the function
    additionally ignore existing ``xsi:type`` annotations.  The default is to
    use them as a type hint.

    The default annotation of empty elements can be set with the
    ``empty_pytype`` keyword argument.  The default is not to annotate empty
    elements.  Pass 'str', for example, to make string values the default.
    """
    element = cetree.rootNodeOrRaise(element_or_tree)
    _annotate(element, 0, 1, ignore_xsi, ignore_old, None, empty_pytype)

def xsiannotate(element_or_tree, ignore_old=False, ignore_pytype=False,
                empty_type=None):
    u"""xsiannotate(element_or_tree, ignore_old=False, ignore_pytype=False, empty_type=None)

    Recursively annotates the elements of an XML tree with 'xsi:type'
    attributes.

    If the 'ignore_old' keyword argument is True (the default), current
    'xsi:type' attributes will be ignored and replaced.  Otherwise, they will be
    checked and only replaced if they no longer fit the current text value.

    Note that the mapping from Python types to XSI types is usually ambiguous.
    Currently, only the first XSI type name in the corresponding PyType
    definition will be used for annotation.  Thus, you should consider naming
    the widest type first if you define additional types.

    Setting the keyword argument ``ignore_pytype`` to True makes the function
    additionally ignore existing ``pytype`` annotations.  The default is to
    use them as a type hint.

    The default annotation of empty elements can be set with the
    ``empty_type`` keyword argument.  The default is not to annotate empty
    elements.  Pass 'string', for example, to make string values the default.
    """
    element = cetree.rootNodeOrRaise(element_or_tree)
    _annotate(element, 1, 0, ignore_old, ignore_pytype, empty_type, None)

def annotate(element_or_tree, ignore_old=True, ignore_xsi=False,
             empty_pytype=None, empty_type=None, annotate_xsi=0,
             annotate_pytype=1):
    u"""annotate(element_or_tree, ignore_old=True, ignore_xsi=False, empty_pytype=None, empty_type=None, annotate_xsi=0, annotate_pytype=1)

    Recursively annotates the elements of an XML tree with 'xsi:type'
    and/or 'py:pytype' attributes.

    If the 'ignore_old' keyword argument is True (the default), current
    'py:pytype' attributes will be ignored for the type annotation. Set to False
    if you want reuse existing 'py:pytype' information (iff appropriate for the
    element text value).

    If the 'ignore_xsi' keyword argument is False (the default), existing
    'xsi:type' attributes will be used for the type annotation, if they fit the
    element text values.

    Note that the mapping from Python types to XSI types is usually ambiguous.
    Currently, only the first XSI type name in the corresponding PyType
    definition will be used for annotation.  Thus, you should consider naming
    the widest type first if you define additional types.

    The default 'py:pytype' annotation of empty elements can be set with the
    ``empty_pytype`` keyword argument. Pass 'str', for example, to make
    string values the default.

    The default 'xsi:type' annotation of empty elements can be set with the
    ``empty_type`` keyword argument.  The default is not to annotate empty
    elements.  Pass 'string', for example, to make string values the default.

    The keyword arguments 'annotate_xsi' (default: 0) and 'annotate_pytype'
    (default: 1) control which kind(s) of annotation to use.
    """
    element = cetree.rootNodeOrRaise(element_or_tree)
    _annotate(element, annotate_xsi, annotate_pytype, ignore_xsi,
              ignore_old, empty_type, empty_pytype)


def _annotate(element, annotate_xsi, annotate_pytype,
              ignore_xsi, ignore_pytype,
              empty_type_name, empty_pytype_name):
    if not annotate_xsi and not annotate_pytype:
        return

    if empty_type_name is not None:
        if isinstance(empty_type_name, bytes):
            empty_type_name = empty_type_name.decode("ascii")
        dict_result = _SCHEMA_TYPE_DICT.get(empty_type_name)
    elif empty_pytype_name is not None:
        if isinstance(empty_pytype_name, bytes):
            empty_pytype_name = empty_pytype_name.decode("ascii")
        dict_result = _PYTYPE_DICT.get(empty_pytype_name)
    else:
        dict_result = None
    empty_pytype = dict_result

    StrType  = _PYTYPE_DICT.get(u'str')
    NoneType = _PYTYPE_DICT.get(u'NoneType')

    doc = element._doc
    c_node = element._c_node
    for c_node in FOR_EACH_ELEMENT_FROM(c_node, c_node, 1):
        if c_node.type == tree.XML_ELEMENT_NODE:
            _annotate_element(c_node, doc, annotate_xsi, annotate_pytype,
                              ignore_xsi, ignore_pytype,
                              empty_type_name, empty_pytype, StrType, NoneType)
            proxy = getProxy(c_node)
            if proxy is not None and proxy is not element:
                detachProxy(proxy)

def _annotate_element(c_node, doc,
                      annotate_xsi, annotate_pytype,
                      ignore_xsi, ignore_pytype,
                      empty_type_name, empty_pytype,
                      StrType, NoneType):
    pytype = None
    typename = None
    istree = 0

    # if element is defined as xsi:nil, represent it as None
    if cetree.attributeValueFromNsName(
        c_node, _XML_SCHEMA_INSTANCE_NS, "nil") == "true":
        pytype = NoneType

    if  pytype is None and not ignore_xsi:
        # check that old xsi type value is valid
        typename = cetree.attributeValueFromNsName(
            c_node, _XML_SCHEMA_INSTANCE_NS, "type")
        if typename is not None:
            dict_result = _SCHEMA_TYPE_DICT.get(typename)
            if dict_result is None and u':' in typename:
                prefix, typename = typename.split(u':', 1)
                dict_result = _SCHEMA_TYPE_DICT.get(typename)
            if dict_result is not None:
                pytype = dict_result
                if pytype is not StrType:
                    # StrType does not have a typecheck but is the default
                    # anyway, so just accept it if given as type
                    # information
                    pytype = _check_type(c_node, pytype)
                    if pytype is None:
                        typename = None

    if pytype is None and not ignore_pytype:
        # check that old pytype value is valid
        old_pytypename = cetree.attributeValueFromNsName(
            c_node, _PYTYPE_NAMESPACE, _PYTYPE_ATTRIBUTE_NAME)
        if old_pytypename is not None:
            if old_pytypename == TREE_PYTYPE_NAME:
                if not cetree.hasChild(c_node):
                    # only case where we should keep it,
                    # everything else is clear enough
                    pytype = TREE_PYTYPE
            else:
                if old_pytypename == 'none':
                    # transition from lxml 1.x
                    old_pytypename = "NoneType"
                dict_result = _PYTYPE_DICT.get(old_pytypename)
                if dict_result is not None:
                    pytype = dict_result
                    if pytype is not StrType:
                        # StrType does not have a typecheck but is the
                        # default anyway, so just accept it if given as
                        # type information
                        pytype = _check_type(c_node, pytype)

    if pytype is None:
        # try to guess type
        if not cetree.hasChild(c_node):
            # element has no children => data class
            pytype = _guessPyType(textOf(c_node), StrType)
        else:
            istree = 1

    if pytype is None:
        # use default type for empty elements
        if cetree.hasText(c_node):
            pytype = StrType
        else:
            pytype = empty_pytype
            if typename is None:
                typename = empty_type_name

    if pytype is not None:
        if typename is None:
            if not istree:
                if pytype._schema_types:
                    # pytype->xsi:type is a 1:n mapping
                    # simply take the first
                    typename = pytype._schema_types[0]
        elif typename not in pytype._schema_types:
            typename = pytype._schema_types[0]

    if annotate_xsi:
        if typename is None or istree:
            cetree.delAttributeFromNsName(
                c_node, XML_SCHEMA_INSTANCE_NS_UTF8, "type")
        else:
            # update or create attribute
            typename_utf8 = cetree.utf8(typename)
            c_ns = cetree.findOrBuildNodeNsPrefix(
                doc, c_node, XML_SCHEMA_NS_UTF8, 'xsd')
            if c_ns:
                if b':' in typename_utf8:
                    prefix, name = typename_utf8.split(b':', 1)
                    if not c_ns.prefix or c_ns.prefix[0] == '\0':
                        typename_utf8 = name
                    elif tree.xmlStrcmp(prefix, c_ns.prefix) != 0:
                        typename_utf8 = tree.ffi.string(c_ns.prefix) + b':' + name
                elif c_ns.prefix and c_ns.prefix[0] != '\0':
                    typename_utf8 = tree.ffi.string(c_ns.prefix) + b':' + typename_utf8
            c_ns = cetree.findOrBuildNodeNsPrefix(
                doc, c_node, _XML_SCHEMA_INSTANCE_NS, 'xsi')
            tree.xmlSetNsProp(c_node, c_ns, "type", typename_utf8)

    if annotate_pytype:
        if pytype is None:
            # delete attribute if it exists
            cetree.delAttributeFromNsName(
                c_node, _PYTYPE_NAMESPACE, _PYTYPE_ATTRIBUTE_NAME)
        else:
            # update or create attribute
            c_ns = cetree.findOrBuildNodeNsPrefix(
                doc, c_node, _PYTYPE_NAMESPACE, 'py')
            pytype_name = cetree.utf8(pytype.name)
            tree.xmlSetNsProp(c_node, c_ns, _PYTYPE_ATTRIBUTE_NAME,
                              pytype_name)
            if pytype is NoneType:
                c_ns = cetree.findOrBuildNodeNsPrefix(
                    doc, c_node, _XML_SCHEMA_INSTANCE_NS, 'xsi')
                tree.xmlSetNsProp(c_node, c_ns, "nil", "true")

_strip_attributes = etree.strip_attributes
_cleanup_namespaces = etree.cleanup_namespaces

def deannotate(element_or_tree, pytype=True, xsi=True,
               xsi_nil=False, cleanup_namespaces=False):
    u"""deannotate(element_or_tree, pytype=True, xsi=True, xsi_nil=False, cleanup_namespaces=False)

    Recursively de-annotate the elements of an XML tree by removing 'py:pytype'
    and/or 'xsi:type' attributes and/or 'xsi:nil' attributes.

    If the 'pytype' keyword argument is True (the default), 'py:pytype'
    attributes will be removed. If the 'xsi' keyword argument is True (the
    default), 'xsi:type' attributes will be removed.
    If the 'xsi_nil' keyword argument is True (default: False), 'xsi:nil'
    attributes will be removed.

    Note that this does not touch the namespace declarations by
    default.  If you want to remove unused namespace declarations from
    the tree, pass the option ``cleanup_namespaces=True``.
    """
    attribute_names = []

    if pytype:
        attribute_names.append(PYTYPE_ATTRIBUTE)
    if xsi:
        attribute_names.append(XML_SCHEMA_INSTANCE_TYPE_ATTR)
    if xsi_nil:
        attribute_names.append(XML_SCHEMA_INSTANCE_NIL_ATTR)

    _strip_attributes(element_or_tree, *attribute_names)
    if cleanup_namespaces:
        _cleanup_namespaces(element_or_tree)


################################################################################
# Module level parser setup

__DEFAULT_PARSER = etree.XMLParser(remove_blank_text=True)
__DEFAULT_PARSER.set_element_class_lookup( ObjectifyElementClassLookup() )

objectify_parser = __DEFAULT_PARSER

def makeparser(**kw):
    u"""makeparser(remove_blank_text=True, **kw)

    Create a new XML parser for objectify trees.

    You can pass all keyword arguments that are supported by
    ``etree.XMLParser()``.  Note that this parser defaults to removing
    blank text.  You can disable this by passing the
    ``remove_blank_text`` boolean keyword option yourself.
    """
    if 'remove_blank_text' not in kw:
        kw['remove_blank_text'] = True
    parser = etree.XMLParser(**kw)
    parser.set_element_class_lookup( ObjectifyElementClassLookup() )
    return parser

def _makeElement(tag, text, attrib, nsmap):
    return cetree.makeElement(tag, None, None, objectify_parser, text, None, attrib, nsmap, None)

################################################################################
# Module level factory functions

_fromstring = etree.fromstring

SubElement = etree.SubElement

def fromstring(xml, parser=None, base_url=None):
    u"""fromstring(xml, parser=None, base_url=None)

    Objectify specific version of the lxml.etree fromstring() function
    that uses the objectify parser.

    You can pass a different parser as second argument.

    The ``base_url`` keyword argument allows to set the original base URL of
    the document to support relative Paths when looking up external entities
    (DTD, XInclude, ...).
    """
    if parser is None:
        parser = objectify_parser
    return _fromstring(xml, parser, base_url=base_url)

def XML(xml, parser=None, base_url=None):
    u"""XML(xml, parser=None, base_url=None)

    Objectify specific version of the lxml.etree XML() literal factory
    that uses the objectify parser.

    You can pass a different parser as second argument.

    The ``base_url`` keyword argument allows to set the original base URL of
    the document to support relative Paths when looking up external entities
    (DTD, XInclude, ...).
    """
    if parser is None:
        parser = objectify_parser
    return _fromstring(xml, parser, base_url=base_url)

_parse = etree.parse

def parse(f, parser=None, base_url=None):
    u"""parse(f, parser=None, base_url=None)

    Parse a file or file-like object with the objectify parser.

    You can pass a different parser as second argument.

    The ``base_url`` keyword allows setting a URL for the document
    when parsing from a file-like object.  This is needed when looking
    up external entities (DTD, XInclude, ...) with relative paths.
    """
    if parser is None:
        parser = objectify_parser
    return _parse(f, parser, base_url=base_url)

_DEFAULT_NSMAP = {
    "py"  : PYTYPE_NAMESPACE,
    "xsi" : XML_SCHEMA_INSTANCE_NS,
    "xsd" : XML_SCHEMA_NS
}

E = ElementMaker()

def Element(_tag, attrib=None, nsmap=None, _pytype=None, **_attributes):
    u"""Element(_tag, attrib=None, nsmap=None, _pytype=None, **_attributes)

    Objectify specific version of the lxml.etree Element() factory that
    always creates a structural (tree) element.

    NOTE: requires parser based element class lookup activated in lxml.etree!
    """
    if attrib is not None:
        if python.PyDict_Size(_attributes):
            attrib = dict(attrib)
            attrib.update(_attributes)
        _attributes = attrib
    if _pytype is None:
        _pytype = TREE_PYTYPE_NAME
    if nsmap is None:
        nsmap = _DEFAULT_NSMAP
    _attributes[PYTYPE_ATTRIBUTE] = _pytype
    return _makeElement(_tag, None, _attributes, nsmap)

def DataElement(_value, attrib=None, nsmap=None, _pytype=None, _xsi=None,
                **_attributes):
    u"""DataElement(_value, attrib=None, nsmap=None, _pytype=None, _xsi=None, **_attributes)

    Create a new element from a Python value and XML attributes taken from
    keyword arguments or a dictionary passed as second argument.

    Automatically adds a 'pytype' attribute for the Python type of the value,
    if the type can be identified.  If '_pytype' or '_xsi' are among the
    keyword arguments, they will be used instead.

    If the _value argument is an ObjectifiedDataElement instance, its py:pytype,
    xsi:type and other attributes and nsmap are reused unless they are redefined
    in attrib and/or keyword arguments.
    """
    if nsmap is None:
        nsmap = _DEFAULT_NSMAP
    if attrib is not None and attrib:
        if _attributes:
            attrib = dict(attrib)
            attrib.update(_attributes)
        _attributes = attrib
    if isinstance(_value, ObjectifiedElement):
        if _pytype is None:
            if _xsi is None and not _attributes and nsmap is _DEFAULT_NSMAP:
                # special case: no change!
                return _value.__copy__()
    if isinstance(_value, ObjectifiedDataElement):
        # reuse existing nsmap unless redefined in nsmap parameter
        temp = _value.nsmap
        if temp is not None and temp:
            temp = dict(temp)
            temp.update(nsmap)
            nsmap = temp
        # reuse existing attributes unless redefined in attrib/_attributes
        temp = _value.attrib
        if temp is not None and temp:
            temp = dict(temp)
            temp.update(_attributes)
            _attributes = temp
        # reuse existing xsi:type or py:pytype attributes, unless provided as
        # arguments
        if _xsi is None and _pytype is None:
            dict_result = _attributes.get(XML_SCHEMA_INSTANCE_TYPE_ATTR)
            if dict_result is not None:
                _xsi = dict_result
            dict_result = _attributes.get(PYTYPE_ATTRIBUTE)
            if dict_result is not None:
                _pytype = dict_result

    if _xsi is not None:
        if u':' in _xsi:
            prefix, name = _xsi.split(u':', 1)
            ns = nsmap.get(prefix)
            if ns != XML_SCHEMA_NS:
                raise ValueError, u"XSD types require the XSD namespace"
        elif nsmap is _DEFAULT_NSMAP:
            name = _xsi
            _xsi = u'xsd:' + _xsi
        else:
            name = _xsi
            for prefix, ns in nsmap.items():
                if ns == XML_SCHEMA_NS:
                    if prefix is not None and prefix:
                        _xsi = prefix + u':' + _xsi
                    break
            else:
                raise ValueError, u"XSD types require the XSD namespace"
        _attributes[XML_SCHEMA_INSTANCE_TYPE_ATTR] = _xsi
        if _pytype is None:
            # allow using unregistered or even wrong xsi:type names
            dict_result = _SCHEMA_TYPE_DICT.get(_xsi)
            if dict_result is None:
                dict_result = _SCHEMA_TYPE_DICT.get(name)
            if dict_result is not None:
                _pytype = dict_result.name

    if _pytype is None:
        _pytype = _pytypename(_value)

    if _value is None and _pytype != u"str":
        _pytype = _pytype or u"NoneType"
        strval = None
    elif python._isString(_value):
        strval = _value
    elif isinstance(_value, bool):
        if _value:
            strval = u"true"
        else:
            strval = u"false"
    else:
        stringify = unicode
        dict_result = _PYTYPE_DICT.get(_pytype)
        if dict_result is not None:
            stringify = dict_result.stringify
        strval = stringify(_value)

    if _pytype is not None:
        if _pytype == u"NoneType" or _pytype == u"none":
            strval = None
            _attributes[XML_SCHEMA_INSTANCE_NIL_ATTR] = u"true"
        else:
            # check if type information from arguments is valid
            dict_result = _PYTYPE_DICT.get(_pytype)
            if dict_result is not None:
                type_check = dict_result.type_check
                if type_check is not None:
                    type_check(strval)

                _attributes[PYTYPE_ATTRIBUTE] = _pytype

    return _makeElement(u"value", strval, _attributes, nsmap)


################################################################################
# ObjectPath

from .objectpath import ObjectPath, _buildDescendantPaths
