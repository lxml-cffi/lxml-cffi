from .xpath import XPath
from .etree import XML, _elementFactory, _elementTreeFactory
from .apihelpers import _documentOrRaise, _utf8, funicode
from .parser import _parseDocument
from .includes import tree

_find_id_attributes = None

def XMLID(text, parser=None, base_url=None):
    u"""XMLID(text, parser=None, base_url=None)

    Parse the text and return a tuple (root node, ID dictionary).  The root
    node is the same as returned by the XML() function.  The dictionary
    contains string-element pairs.  The dictionary keys are the values of 'id'
    attributes.  The elements referenced by the ID are stored as dictionary
    values.
    """
    global _find_id_attributes
    if _find_id_attributes is None:
        _find_id_attributes = XPath(u'//*[string(@id)]')

    # ElementTree compatible implementation: parse and look for 'id' attributes
    root = XML(text, parser, base_url=base_url)
    dic = {}
    for elem in _find_id_attributes(root):
        dic[elem.get(u'id')] = elem
    return (root, dic)

def XMLDTDID(text, parser=None, base_url=None):
    u"""XMLDTDID(text, parser=None, base_url=None)

    Parse the text and return a tuple (root node, ID dictionary).  The root
    node is the same as returned by the XML() function.  The dictionary
    contains string-element pairs.  The dictionary keys are the values of ID
    attributes as defined by the DTD.  The elements referenced by the ID are
    stored as dictionary values.

    Note that you must not modify the XML tree if you use the ID dictionary.
    The results are undefined.
    """
    root = XML(text, parser, base_url=base_url)
    # xml:id spec compatible implementation: use DTD ID attributes from libxml2
    if not root._doc._c_doc.ids:
        return (root, {})
    else:
        return (root, _IDDict(root))

def parseid(source, parser=None, base_url=None):
    u"""parseid(source, parser=None)

    Parses the source into a tuple containing an ElementTree object and an
    ID dictionary.  If no parser is provided as second argument, the default
    parser is used.

    Note that you must not modify the XML tree if you use the ID dictionary.
    The results are undefined.
    """
    doc = _parseDocument(source, parser, base_url)
    return (_elementTreeFactory(doc, None), _IDDict(doc))

class _IDDict:
    u"""IDDict(self, etree)
    A dictionary-like proxy class that mapps ID attributes to elements.

    The dictionary must be instantiated with the root element of a parsed XML
    document, otherwise the behaviour is undefined.  Elements and XML trees
    that were created or modified 'by hand' are not supported.
    """
    def __init__(self, etree):
        doc = _documentOrRaise(etree)
        if not doc._c_doc.ids:
            raise ValueError, u"No ID dictionary available."
        self._doc = doc
        self._keys  = None
        self._items = None

    def __contains__(self, id_name):
        id_utf = _utf8(id_name)
        c_id = tree.xmlHashLookup(
            self._doc._c_doc.ids, id_utf)
        return bool(c_id)

    def has_key(self, id_name):
        return id_name in self

    def keys(self):
        if self._keys is None:
            self._keys = self._build_keys()
        return self._keys[:]

    def __iter__(self):
        if self._keys is None:
            self._keys = self._build_keys()
        return iter(self._keys)

    def iterkeys(self):
        return self

    def __len__(self):
        if self._keys is None:
            self._keys = self._build_keys()
        return len(self._keys)

    def items(self):
        if self._items is None:
            self._items = self._build_items()
        return self._items[:]

    def iteritems(self):
        if self._items is None:
            self._items = self._build_items()
        return iter(self._items)

    def values(self):
        values = []
        if self._items is None:
            self._items = self._build_items()
        return [item[1] for item in self._items]

    def itervalues(self):
        return iter(self.values())

    def _build_keys(self):
        keys = []
        handle = tree.ffi.new_handle(keys)
        tree.xmlHashScan(self._doc._c_doc.ids, _collectIdHashKeys, handle)
        return keys

    def _build_items(self):
        items = []
        context = (items, self._doc)
        handle = tree.ffi.new_handle(context)
        tree.xmlHashScan(self._doc._c_doc.ids, _collectIdHashItemList, handle)
        return items

@tree.ffi.callback("xmlHashScanner")
def _collectIdHashItemList(payload, context, name):
    # collect elements from ID attribute hash table
    c_id = tree.ffi.cast("xmlIDPtr", payload)
    if not c_id or not c_id.attr or not c_id.attr.parent:
        return
    lst, doc = tree.ffi.from_handle(context)
    element = _elementFactory(doc, c_id.attr.parent)
    lst.append( (funicode(name), element) )

@tree.ffi.callback("xmlHashScanner")
def _collectIdHashKeys(payload, context, name):
    c_id = tree.ffi.cast("xmlIDPtr", payload)
    if not c_id or not c_id.attr or not c_id.attr.parent:
        return
    collect_list = tree.ffi.from_handle(context)
    collect_list.append(funicode(name))
