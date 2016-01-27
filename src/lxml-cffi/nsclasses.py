# module-level API for namespace implementations

from .classlookup import FallbackElementClassLookup, ElementBase
from .classlookup import _callLookupFallback
from .apihelpers import _utf8, _getNs
from . import python
from ._libxml2 import ffi, lib as tree

class _NamespaceRegistry(object):
    u"Dictionary-like namespace registry"
    def __init__(self, ns_uri):
        self._ns_uri = ns_uri
        if ns_uri is None:
            self._ns_uri_utf = None
            self._c_ns_uri_utf = ffi.NULL
        else:
            self._ns_uri_utf = _utf8(ns_uri)
            self._c_ns_uri_utf = self._ns_uri_utf
        self._entries = {}

    def update(self, class_dict_iterable):
        u"""update(self, class_dict_iterable)

        Forgivingly update the registry.

        ``class_dict_iterable`` may be a dict or some other iterable
        that yields (name, value) pairs.

        If a value does not match the required type for this registry,
        or if the name starts with '_', it will be silently discarded.
        This allows registrations at the module or class level using
        vars(), globals() etc."""
        if hasattr(class_dict_iterable, u'items'):
            class_dict_iterable = class_dict_iterable.items()
        for name, item in class_dict_iterable:
            if (name is None or name[:1] != '_') and callable(item):
                self[name] = item

    def __getitem__(self, name):
        if name is not None:
            name = _utf8(name)
        return self._get(name)

    def __delitem__(self, name):
        if name is not None:
            name = _utf8(name)
        del self._entries[name]

    def _get(self, name):
        try:
            return self._entries[name]
        except KeyError:
            raise KeyError, u"Name not registered."

    def __iter__(self):
        return iter(self._entries)

    def items(self):
        return list(self._entries.items())

    def iteritems(self):
        return iter(self._entries.items())

    def clear(self):
        self._entries.clear()

class _ClassNamespaceRegistry(_NamespaceRegistry):
    u"Dictionary-like registry for namespace implementation classes"
    def __setitem__(self, name, item):
        if not python.PyType_Check(item) or not issubclass(item, ElementBase):
            raise NamespaceRegistryError, \
                u"Registered element classes must be subtypes of ElementBase"
        if name is not None:
            name = _utf8(name)
        self._entries[name] = item

    def __repr__(self):
        return u"Namespace(%r)" % self._ns_uri


class ElementNamespaceClassLookup(FallbackElementClassLookup):
    u"""ElementNamespaceClassLookup(self, fallback=None)

    Element class lookup scheme that searches the Element class in the
    Namespace registry.
    """
    def __init__(self, fallback=None):
        self._namespace_registries = {}
        FallbackElementClassLookup.__init__(self, fallback)
        self._lookup_function = _find_nselement_class

    def get_namespace(self, ns_uri):
        u"""get_namespace(self, ns_uri)

        Retrieve the namespace object associated with the given URI.
        Pass None for the empty namespace.

        Creates a new namespace object if it does not yet exist."""
        if ns_uri:
            ns_utf = _utf8(ns_uri)
        else:
            ns_utf = None
        try:
            return self._namespace_registries[ns_utf]
        except KeyError:
            registry = self._namespace_registries[ns_utf] = \
                       _ClassNamespaceRegistry(ns_uri)
            return registry


def _find_nselement_class(state, doc, c_node):
    if state is None:
        return _lookupDefaultElementClass(None, doc, c_node)

    lookup = state
    if c_node.type != tree.XML_ELEMENT_NODE:
        return _callLookupFallback(lookup, doc, c_node)

    c_namespace_utf = _getNs(c_node)
    if c_namespace_utf:
        dict_result = lookup._namespace_registries.get(
            ffi.string(c_namespace_utf), None)
    else:
        dict_result = lookup._namespace_registries.get(None)
    if dict_result:
        registry = dict_result
        classes = registry._entries

        if c_node.name:
            dict_result = classes.get(ffi.string(c_node.name), None)
        else:
            dict_result = ffi.NULL

        if not dict_result:
            dict_result = classes.get(None)

        if dict_result:
            return dict_result
    return _callLookupFallback(lookup, doc, c_node)


################################################################################
# XPath extension functions

_FUNCTION_NAMESPACE_REGISTRIES = {}

def FunctionNamespace(ns_uri):
    u"""FunctionNamespace(ns_uri)

    Retrieve the function namespace object associated with the given
    URI.

    Creates a new one if it does not yet exist. A function namespace
    can only be used to register extension functions."""
    ns_utf = _utf8(ns_uri) if ns_uri else None
    try:
        return _FUNCTION_NAMESPACE_REGISTRIES[ns_utf]
    except KeyError:
        registry = _FUNCTION_NAMESPACE_REGISTRIES[ns_utf] = \
                   _XPathFunctionNamespaceRegistry(ns_uri)
        return registry

class _FunctionNamespaceRegistry(_NamespaceRegistry):
    def __setitem__(self, name, item):
        if not callable(item):
            raise NamespaceRegistryError, \
                u"Registered functions must be callable."
        if not name:
            raise ValueError, \
                u"extensions must have non empty names"
        self._entries[_utf8(name)] = item

    def __repr__(self):
        return u"FunctionNamespace(%r)" % self._ns_uri

class _XPathFunctionNamespaceRegistry(_FunctionNamespaceRegistry):
    _prefix = None
    _prefix_utf = None

    @property
    def prefix(self):
        u"Namespace prefix for extension functions."
        if self._prefix is None:
            return ''
        else:
            return self._prefix
    @prefix.setter
    def prefix(self, prefix):
        if prefix == '':
            prefix = None # empty prefix
        if prefix is None:
            self._prefix_utf = None
        else:
            self._prefix_utf = _utf8(prefix)
        self._prefix = prefix
    @prefix.deleter
    def prefix(self):
        del self._prefix
        del self._prefix_utf


def _find_all_extension_prefixes():
    u"Internal lookup function to find all function prefixes for XSLT/XPath."
    ns_prefixes = []
    for registry in _FUNCTION_NAMESPACE_REGISTRIES.itervalues():
        if registry._prefix_utf is not None:
            if registry._ns_uri_utf is not None:
                ns_prefixes.append(
                    (registry._prefix_utf, registry._ns_uri_utf))
    return ns_prefixes

