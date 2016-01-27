################################################################################
# ObjectPath

import re

from . import python
from . import cetree
from .apihelpers import _getNs, _tagMatches
from .objectify import _findFollowingSibling, _appendValue, _replaceElement
from ._libxml2 import ffi, lib as tree

class _ObjectPath(object):
    pass


class ObjectPath(object):
    u"""ObjectPath(path)
    Immutable object that represents a compiled object path.

    Example for a path: 'root.child[1].{other}child[25]'
    """
    def __init__(self, path):
        if python._isString(path):
            self._path = _parseObjectPathString(path)
            self._path_str = path
        else:
            self._path = _parseObjectPathList(path)
            self._path_str = u'.'.join(path)
        self._c_path = _buildObjectPathSegments(self._path)
        self.find = self.__call__

    def __str__(self):
        return self._path_str

    def __call__(self, root, *default):
        u"""Follow the attribute path in the object structure and return the
        target attribute value.

        If it it not found, either returns a default value (if one was passed
        as second argument) or raises AttributeError.
        """
        use_default = len(default)
        if use_default == 1:
            default = default[0]
            use_default = 1
        elif use_default > 1:
            raise TypeError, u"invalid number of arguments: needs one or two"
        return _findObjectPath(root, self._c_path, default, use_default)

    def hasattr(self, root):
        u"hasattr(self, root)"
        try:
            _findObjectPath(root, self._c_path, None, 0)
        except AttributeError:
            return False
        return True

    def setattr(self, root, value):
        u"""setattr(self, root, value)

        Set the value of the target element in a subtree.

        If any of the children on the path does not exist, it is created.
        """
        _createObjectPath(root, self._c_path, 1, value)

    def addattr(self, root, value):
        u"""addattr(self, root, value)

        Append a value to the target element in a subtree.

        If any of the children on the path does not exist, it is created.
        """
        _createObjectPath(root, self._c_path, 0, value)

__MATCH_PATH_SEGMENT = re.compile(
    ur"(\.?)\s*(?:\{([^}]*)\})?\s*([^.{}\[\]\s]+)\s*(?:\[\s*([-0-9]+)\s*\])?",
    re.U).match

_RELATIVE_PATH_SEGMENT = (None, None, 0)

def _parseObjectPathString(path):
    u"""Parse object path string into a (ns, name, index) list.
    """
    new_path = []
    if isinstance(path, bytes):
        path = path.decode('ascii')
    path = path.strip()
    if path == u'.':
        return [_RELATIVE_PATH_SEGMENT]
    path_pos = 0
    while path:
        match = __MATCH_PATH_SEGMENT(path, path_pos)
        if match is None:
            break

        dot, ns, name, index = match.groups()
        if index is None or not index:
            index = 0
        else:
            index = int(index)
        has_dot = dot == u'.'
        if not new_path:
            if has_dot:
                # path '.child' => ignore root
                new_path.append(_RELATIVE_PATH_SEGMENT)
            elif index != 0:
                raise ValueError, u"index not allowed on root node"
        elif not has_dot:
            raise ValueError, u"invalid path"
        if ns is not None:
            ns = python.PyUnicode_AsUTF8String(ns)
        name = python.PyUnicode_AsUTF8String(name)
        new_path.append( (ns, name, index) )

        path_pos = match.end()
    if not new_path or len(path) > path_pos:
        raise ValueError, u"invalid path"
    return new_path

def _parseObjectPathList(path):
    u"""Parse object path sequence into a (ns, name, index) list.
    """
    new_path = []
    for item in path:
        item = item.strip()
        if not new_path and item == u'':
            # path '.child' => ignore root
            ns = name = None
            index = 0
        else:
            ns, name = cetree.getNsTag(item)
            c_name = name
            index_pos = c_name.find('[')
            if index_pos < 0:
                index = 0
            else:
                index_end = c_name.find(']', index_pos)
                if index_end < 0:
                    raise ValueError, u"index must be enclosed in []"
                index = int(c_name[index_pos+1:index_end])
                if not new_path and index != 0:
                    raise ValueError, u"index not allowed on root node"
                name = c_name[:index_pos]
        new_path.append( (ns, name, index) )
    if not new_path:
        raise ValueError, u"invalid path"
    return new_path

def _buildObjectPathSegments(path_list):
    c_path_segments = []
    for href, name, index in path_list:
        c_path = _ObjectPath()
        c_path.href = ffi.new("xmlChar[]", href) if href else ffi.NULL
        c_path.name = ffi.new("xmlChar[]", name) if name else ffi.NULL
        c_path.index = index
        c_path_segments.append(c_path)
    return c_path_segments

def _findObjectPath(root, c_path, default_value, use_default):
    u"""Follow the path to find the target element.
    """
    c_node = root._c_node
    c_name = c_path[0].name
    c_href = c_path[0].href
    if not c_href:
        c_href = _getNs(c_node)
    if not _tagMatches(c_node, c_href, c_name):
        if use_default:
            return default_value
        else:
            raise ValueError, \
                u"root element does not match: need %s, got %s" % \
                (cetree.namespacedNameFromNsName(c_href, c_name), root.tag)

    for c_path_item in c_path[1:]:
        if not c_node:
            break

        if c_path_item.href:
            c_href = c_path_item.href # otherwise: keep parent namespace
        c_name = tree.xmlDictExists(c_node.doc.dict, c_path_item.name, -1)
        if not c_name:
            c_name = c_path_item.name
            c_node = ffi.NULL
            break
        c_index = c_path_item.index
        c_node = c_node.last if c_index < 0 else c_node.children
        c_node = _findFollowingSibling(c_node, c_href, c_name, c_index)

    if c_node:
        return cetree.elementFactory(root._doc, c_node)
    elif use_default:
        return default_value
    else:
        tag = cetree.namespacedNameFromNsName(c_href, c_name)
        raise AttributeError, u"no such child: " + tag

def _createObjectPath(root, c_path, replace, value):
    u"""Follow the path to find the target element, build the missing children
    as needed and set the target element to 'value'.  If replace is true, an
    existing value is replaced, otherwise the new value is added.
    """
    if len(c_path) == 1:
        raise TypeError, u"cannot update root node"

    c_node = root._c_node
    c_name = c_path[0].name
    c_href = c_path[0].href
    if not c_href:
        c_href = _getNs(c_node)
    if not _tagMatches(c_node, c_href, c_name):
        raise ValueError, \
            u"root element does not match: need %s, got %s" % \
            (cetree.namespacedNameFromNsName(c_href, c_name), root.tag)

    for c_path_item in c_path[1:]:
        if c_path_item.href:
            c_href = c_path_item.href # otherwise: keep parent namespace
        c_index = c_path_item.index
        c_name = tree.xmlDictExists(c_node.doc.dict, c_path_item.name, -1)
        if not c_name:
            c_name = c_path_item.name
            c_child = ffi.NULL
        else:
            c_child = c_node.last if c_index < 0 else c_node.children
            c_child = _findFollowingSibling(c_child, c_href, c_name, c_index)

        if c_child:
            c_node = c_child
        elif c_index != 0:
            raise TypeError, \
                u"creating indexed path attributes is not supported"
        elif c_path_item is c_path[-1]:
            _appendValue(cetree.elementFactory(root._doc, c_node),
                         cetree.namespacedNameFromNsName(c_href, c_name),
                         value)
            return
        else:
            child = cetree.makeSubElement(
                cetree.elementFactory(root._doc, c_node),
                cetree.namespacedNameFromNsName(c_href, c_name),
                None, None, None, None, None)
            c_node = child._c_node

    # if we get here, the entire path was already there
    if replace:
        element = cetree.elementFactory(root._doc, c_node)
        _replaceElement(element, value)
    else:
        _appendValue(cetree.elementFactory(root._doc, c_node.parent),
                     cetree.namespacedName(c_node), value)

def _buildDescendantPaths(c_node, prefix_string):
    u"""Returns a list of all descendant paths.
    """
    tag = cetree.namespacedName(c_node)
    if prefix_string:
        if prefix_string[-1] != u'.':
            prefix_string += u'.'
        prefix_string = prefix_string + tag
    else:
        prefix_string = tag
    path = [prefix_string]
    path_list = []
    _recursiveBuildDescendantPaths(c_node, path, path_list)
    return path_list

def _recursiveBuildDescendantPaths(c_node, path, path_list):
    u"""Fills the list 'path_list' with all descendant paths, initial prefix
    being in the list 'path'.
    """
    tags = {}
    path_list.append( u'.'.join(path) )
    c_href = cetree._getNs(c_node)
    c_child = c_node.children
    while c_child:
        while c_child.type != tree.XML_ELEMENT_NODE:
            c_child = c_child.next
            if not c_child:
                return
        if c_href == cetree._getNs(c_child):
            tag = ffi.string(c_child.name)
        elif c_href and not cetree._getNs(c_child):
            # special case: parent has namespace, child does not
            tag = u'{}' + ffi.string(c_child.name)
        else:
            tag = cetree.namespacedName(c_child)
        count = tags.get(tag, -1) + 1
        tags[tag] = count
        if count > 0:
            tag += u'[%d]' % count
        path.append(tag)
        _recursiveBuildDescendantPaths(c_child, path, path_list)
        del path[-1]
        c_child = c_child.next
