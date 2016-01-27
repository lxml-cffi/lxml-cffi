# Configurable Element class lookup

from .etree import _Comment, _Element, _ProcessingInstruction, _Entity
from .etree import _documentFactory
from .apihelpers import _getNs, _getNsTag, funicode, _utf8, _isString
from .apihelpers import _initNewElement, _attributeValueFromNsName
from .apihelpers import _appendChild, _setTailText, _collectText
from .apihelpers import _setNodeText
from .parser import HTMLParser, _newXMLDoc
from .proxy import _registerProxy
from ._libxml2 import ffi, lib as tree


################################################################################
# Custom Element classes

class ElementBase(_Element):
    u"""ElementBase(*children, attrib=None, nsmap=None, **_extra)

    The public Element class.  All custom Element classes must inherit
    from this one.  To create an Element, use the `Element()` factory.

    BIG FAT WARNING: Subclasses *must not* override __init__ or
    __new__ as it is absolutely undefined when these objects will be
    created or destroyed.  All persistent state of Elements must be
    stored in the underlying XML.  If you really need to initialize
    the object after creation, you can implement an ``_init(self)``
    method that will be called directly after object creation.

    Subclasses of this class can be instantiated to create a new
    Element.  By default, the tag name will be the class name and the
    namespace will be empty.  You can modify this with the following
    class attributes:

    * TAG - the tag name, possibly containing a namespace in Clark
      notation

    * NAMESPACE - the default namespace URI, unless provided as part
      of the TAG attribute.

    * HTML - flag if the class is an HTML tag, as opposed to an XML
      tag.  This only applies to un-namespaced tags and defaults to
      false (i.e. XML).

    * PARSER - the parser that provides the configuration for the
      newly created document.  Providing an HTML parser here will
      default to creating an HTML element.

    In user code, the latter three are commonly inherited in class
    hierarchies that implement a common namespace.
    """
    def __init__(self, *children, **_extra):
        u"""ElementBase(*children, attrib=None, nsmap=None, **_extra)
        """
        attrib = _extra.pop('attrib', None)
        nsmap = _extra.pop('nsmap', None)
        is_html = 0
        # don't use normal attribute access as it might be overridden
        _getattr = object.__getattribute__
        try:
            namespace = _utf8(_getattr(self, 'NAMESPACE'))
        except AttributeError:
            namespace = None
        try:
            ns, tag = _getNsTag(_getattr(self, 'TAG'))
            if ns is not None:
                namespace = ns
        except AttributeError:
            tag = _utf8(_getattr(_getattr(self, '__class__'), '__name__'))
            if b'.' in tag:
                tag = tag.split(b'.')[-1]
        try:
            parser = _getattr(self, 'PARSER')
        except AttributeError:
            parser = None
            for child in children:
                if isinstance(child, _Element):
                    parser = child._doc._parser
                    break
        if isinstance(parser, HTMLParser):
            is_html = 1
        if namespace is None:
            try:
                is_html = _getattr(self, 'HTML')
            except AttributeError:
                pass
        _initNewElement(self, is_html, tag, namespace, parser,
                        attrib, nsmap, _extra)
        last_child = None
        for child in children:
            if _isString(child):
                if last_child is None:
                    _setNodeText(self._c_node,
                                 (_collectText(self._c_node.children) or '') + child)
                else:
                    _setTailText(last_child._c_node,
                                 (_collectText(last_child._c_node.next) or '') + child)
            elif isinstance(child, _Element):
                last_child = child
                _appendChild(self, last_child)
            elif isinstance(child, type) and issubclass(child, ElementBase):
                last_child = child()
                _appendChild(self, last_child)
            else:
                raise TypeError, "Invalid child type: %r" % type(child)

class CommentBase(_Comment):
    u"""All custom Comment classes must inherit from this one.

    To create an XML Comment instance, use the ``Comment()`` factory.

    Subclasses *must not* override __init__ or __new__ as it is
    absolutely undefined when these objects will be created or
    destroyed.  All persistent state of Comments must be stored in the
    underlying XML.  If you really need to initialize the object after
    creation, you can implement an ``_init(self)`` method that will be
    called after object creation.
    """
    def __init__(self, text):
        # copied from Comment() factory
        from .etree import _createComment
        if text is None:
            text = b''
        else:
            text = _utf8(text)
        c_doc = _newXMLDoc()
        doc = _documentFactory(c_doc, None)
        self._c_node = _createComment(c_doc, text)
        tree.xmlAddChild(ffi.cast("xmlNodePtr", c_doc), self._c_node)
        _registerProxy(self, doc, self._c_node)
        self._init()

class PIBase(_ProcessingInstruction):
    u"""All custom Processing Instruction classes must inherit from this one.

    To create an XML ProcessingInstruction instance, use the ``PI()``
    factory.

    Subclasses *must not* override __init__ or __new__ as it is
    absolutely undefined when these objects will be created or
    destroyed.  All persistent state of PIs must be stored in the
    underlying XML.  If you really need to initialize the object after
    creation, you can implement an ``_init(self)`` method that will be
    called after object creation.
    """
    def __init__(self, target, text=None):
        # copied from PI() factory
        from .etree import _createPI
        target = _utf8(target)
        if text is None:
            text = b''
        else:
            text = _utf8(text)
        c_doc = _newXMLDoc()
        doc = _documentFactory(c_doc, None)
        self._c_node = _createPI(c_doc, target, text)
        tree.xmlAddChild(ffi.cast("xmlNodePtr", c_doc), self._c_node)
        _registerProxy(self, doc, self._c_node)
        self._init()

class EntityBase(_Entity):
    u"""All custom Entity classes must inherit from this one.

    To create an XML Entity instance, use the ``Entity()`` factory.

    Subclasses *must not* override __init__ or __new__ as it is
    absolutely undefined when these objects will be created or
    destroyed.  All persistent state of Entities must be stored in the
    underlying XML.  If you really need to initialize the object after
    creation, you can implement an ``_init(self)`` method that will be
    called after object creation.
    """
    def __init__(self, name):
        name_utf = _utf8(name)
        c_name = _xcstr(name_utf)
        if c_name[0] == '#':
            if not _characterReferenceIsValid(c_name + 1):
                raise ValueError, u"Invalid character reference: '%s'" % name
        elif not _xmlNameIsValid(c_name):
            raise ValueError, u"Invalid entity reference: '%s'" % name
        c_doc = _newXMLDoc()
        doc = _documentFactory(c_doc, None)
        self._c_node = _createEntity(c_doc, c_name)
        tree.xmlAddChild(c_doc, self._c_node)
        _registerProxy(self, doc, self._c_node)
        self._init()


def _validateNodeClass(c_node, cls):
    if c_node.type == tree.XML_ELEMENT_NODE:
        expected = ElementBase
    elif c_node.type == tree.XML_COMMENT_NODE:
        expected = CommentBase
    elif c_node.type == tree.XML_ENTITY_REF_NODE:
        expected = EntityBase
    elif c_node.type == tree.XML_PI_NODE:
        expected = PIBase
    else:
        assert 0, u"Unknown node type: %s" % c_node.type

    if not (isinstance(cls, type) and issubclass(cls, expected)):
        raise TypeError(
            "result of class lookup must be subclass of %s, got %s"
            % (expected, cls))


################################################################################
# Element class lookup

# class to store element class lookup functions
class ElementClassLookup(object):
    u"""ElementClassLookup(self)
    Superclass of Element class lookups.
    """
    def __init__(self):
        self._lookup_function = None # use default lookup

class FallbackElementClassLookup(ElementClassLookup):
    u"""FallbackElementClassLookup(self, fallback=None)

    Superclass of Element class lookups with additional fallback.
    """
    fallback = None

    def __init__(self, fallback=None):
        if fallback is not None:
            self._setFallback(fallback)
        else:
            self._fallback_function = _lookupDefaultElementClass

    def _setFallback(self, lookup):
        u"""Sets the fallback scheme for this lookup method.
        """
        self.fallback = lookup
        self._fallback_function = lookup._lookup_function
        if not self._fallback_function:
            self._fallback_function = _lookupDefaultElementClass

def _callLookupFallback(lookup, doc, c_node):
    return lookup._fallback_function(lookup.fallback, doc, c_node)


################################################################################
# default lookup scheme

def _lookupDefaultElementClass(state, _doc, c_node):
    u"Trivial class lookup function that always returns the default class."
    from .etree import _Element, _Comment, _ProcessingInstruction
    if c_node.type == tree.XML_ELEMENT_NODE:
        if state is not None:
            return state.element_class
        else:
            return _Element
    elif c_node.type == tree.XML_COMMENT_NODE:
        if state is not None:
            return state.comment_class
        else:
            return _Comment
    elif c_node.type == tree.XML_ENTITY_REF_NODE:
        if state is not None:
            return state.entity_class
        else:
            return _Entity
    elif c_node.type == tree.XML_PI_NODE:
        if state is None or state.pi_class is None:
            # special case XSLT-PI
            if c_node.name and c_node.content:
                if tree.xmlStrcmp(c_node.name, "xml-stylesheet") == 0:
                    if (tree.xmlStrstr(c_node.content, "text/xsl") or
                        tree.xmlStrstr(c_node.content, "text/xml")):
                        from .xslt import _XSLTProcessingInstruction
                        return _XSLTProcessingInstruction
            return _ProcessingInstruction
        else:
            return state.pi_class
    else:
        assert 0, u"Unknown node type: %s" % c_node.type


class ElementDefaultClassLookup(ElementClassLookup):
    u"""ElementDefaultClassLookup(self, element=None, comment=None, pi=None, entity=None)
    Element class lookup scheme that always returns the default Element
    class.

    The keyword arguments ``element``, ``comment``, ``pi`` and ``entity``
    accept the respective Element classes.
    """
    _lookup_function = staticmethod(_lookupDefaultElementClass)

    def __init__(self, element=None, comment=None, pi=None, entity=None):
        if element is None:
            self.element_class = _Element
        elif issubclass(element, ElementBase):
            self.element_class = element
        else:
            raise TypeError, u"element class must be subclass of ElementBase"

        if comment is None:
            self.comment_class = _Comment
        elif issubclass(comment, CommentBase):
            self.comment_class = comment
        else:
            raise TypeError, u"comment class must be subclass of CommentBase"

        if entity is None:
            self.entity_class = _Entity
        elif issubclass(entity, EntityBase):
            self.entity_class = entity
        else:
            raise TypeError, u"Entity class must be subclass of EntityBase"

        if pi is None:
            self.pi_class = None # special case, see below
        elif issubclass(pi, PIBase):
            self.pi_class = pi
        else:
            raise TypeError, u"PI class must be subclass of PIBase"


################################################################################
# attribute based lookup scheme

def _attribute_class_lookup(state, doc, c_node):
    lookup = state
    if c_node.type == tree.XML_ELEMENT_NODE:
        value = _attributeValueFromNsName(
            c_node, lookup._c_ns, lookup._c_name)
        try:
            cls = lookup._class_mapping[value]
        except KeyError:
            pass
        else:
            _validateNodeClass(c_node, cls)
            return cls
    return _callLookupFallback(lookup, doc, c_node)


class AttributeBasedElementClassLookup(FallbackElementClassLookup):
    u"""AttributeBasedElementClassLookup(self, attribute_name, class_mapping, fallback=None)
    Checks an attribute of an Element and looks up the value in a
    class dictionary.

    Arguments:
      - attribute name - '{ns}name' style string
      - class mapping  - Python dict mapping attribute values to Element classes
      - fallback       - optional fallback lookup mechanism

    A None key in the class mapping will be checked if the attribute is
    missing.
    """
    _lookup_function = staticmethod(_attribute_class_lookup)

    def __init__(self, attribute_name, class_mapping, fallback=None):
        self._pytag = _getNsTag(attribute_name)
        ns, name = self._pytag
        if ns is None:
            self._c_ns = ffi.NULL
        else:
            self._c_ns = ns
        self._c_name = name
        self._class_mapping = dict(class_mapping)

        FallbackElementClassLookup.__init__(self, fallback)


################################################################################
#  per-parser lookup scheme

class ParserBasedElementClassLookup(FallbackElementClassLookup):
    u"""ParserBasedElementClassLookup(self, fallback=None)
    Element class lookup based on the XML parser.
    """
    def __init__(self):
        FallbackElementClassLookup.__init__(self)
        self._lookup_function = _parser_class_lookup

def _parser_class_lookup(state, doc, c_node):
    if doc._parser._class_lookup is not None:
        return doc._parser._class_lookup._lookup_function(
            doc._parser._class_lookup, doc, c_node)
    return _callLookupFallback(state, doc, c_node)


################################################################################
#  custom class lookup based on node type, namespace, name

def _custom_class_lookup(state, doc, c_node):
    lookup = state

    if c_node.type == tree.XML_ELEMENT_NODE:
        element_type = u"element"
    elif c_node.type == tree.XML_COMMENT_NODE:
        element_type = u"comment"
    elif c_node.type == tree.XML_PI_NODE:
        element_type = u"PI"
    elif c_node.type == tree.XML_ENTITY_REF_NODE:
        element_type = u"entity"
    else:
        element_type = u"element"
    if not c_node.name:
        name = None
    else:
        name = funicode(c_node.name)
    c_str = _getNs(c_node)
    ns = funicode(c_str) if c_str else None

    cls = lookup.lookup(element_type, doc, ns, name)
    if cls is not None:
        _validateNodeClass(c_node, cls)
        return cls
    return _callLookupFallback(lookup, doc, c_node)

class CustomElementClassLookup(FallbackElementClassLookup):
    u"""CustomElementClassLookup(self, fallback=None)
    Element class lookup based on a subclass method.

    You can inherit from this class and override the method::

        lookup(self, type, doc, namespace, name)

    to lookup the element class for a node. Arguments of the method:
    * type:      one of 'element', 'comment', 'PI', 'entity'
    * doc:       document that the node is in
    * namespace: namespace URI of the node (or None for comments/PIs/entities)
    * name:      name of the element/entity, None for comments, target for PIs

    If you return None from this method, the fallback will be called.
    """
    _lookup_function = staticmethod(_custom_class_lookup)

    def lookup(self, type, doc, namespace, name):
        u"lookup(self, type, doc, namespace, name)"
        return None

################################################################################
# read-only tree based class lookup

class PythonElementClassLookup(FallbackElementClassLookup):
    u"""PythonElementClassLookup(self, fallback=None)
    Element class lookup based on a subclass method.

    This class lookup scheme allows access to the entire XML tree in
    read-only mode.  To use it, re-implement the ``lookup(self, doc,
    root)`` method in a subclass::

        from lxml import etree, pyclasslookup

        class MyElementClass(etree.ElementBase):
            honkey = True

        class MyLookup(pyclasslookup.PythonElementClassLookup):
            def lookup(self, doc, root):
                if root.tag == "sometag":
                    return MyElementClass
                else:
                    for child in root:
                        if child.tag == "someothertag":
                            return MyElementClass
                # delegate to default
                return None

    If you return None from this method, the fallback will be called.

    The first argument is the opaque document instance that contains
    the Element.  The second argument is a lightweight Element proxy
    implementation that is only valid during the lookup.  Do not try
    to keep a reference to it.  Once the lookup is done, the proxy
    will be invalid.

    Also, you cannot wrap such a read-only Element in an ElementTree,
    and you must take care not to keep a reference to them outside of
    the `lookup()` method.

    Note that the API of the Element objects is not complete.  It is
    purely read-only and does not support all features of the normal
    `lxml.etree` API (such as XPath, extended slicing or some
    iteration methods).

    See http://codespeak.net/lxml/element_classes.html
    """
    def __init__(self):
        self._lookup_function = _python_class_lookup

    def lookup(self, doc, element):
        u"""lookup(self, doc, element)

        Override this method to implement your own lookup scheme.
        """
        return None

def _python_class_lookup(state, doc, c_node):
    from .readonlytree import _newReadOnlyProxy, _freeReadOnlyProxies
    lookup = state

    proxy = _newReadOnlyProxy(None, c_node)
    cls = lookup.lookup(doc, proxy)
    _freeReadOnlyProxies(proxy)

    if cls is not None:
        _validateNodeClass(c_node, cls)
        return cls
    return _callLookupFallback(lookup, doc, c_node)

################################################################################
# Global setup

def _setElementClassLookupFunction(function, state):
    global LOOKUP_ELEMENT_CLASS, ELEMENT_CLASS_LOOKUP_STATE
    if not function:
        state    = DEFAULT_ELEMENT_CLASS_LOOKUP
        function = DEFAULT_ELEMENT_CLASS_LOOKUP._lookup_function

    ELEMENT_CLASS_LOOKUP_STATE = state
    LOOKUP_ELEMENT_CLASS = function

def set_element_class_lookup(lookup = None):
    u"""set_element_class_lookup(lookup = None)

    Set the global default element class lookup method.
    """
    if lookup is None or not lookup._lookup_function:
        _setElementClassLookupFunction(ffi.NULL, None)
    else:
        _setElementClassLookupFunction(lookup._lookup_function, lookup)

# default setup: parser delegation
DEFAULT_ELEMENT_CLASS_LOOKUP = ParserBasedElementClassLookup()

set_element_class_lookup(DEFAULT_ELEMENT_CLASS_LOOKUP)
