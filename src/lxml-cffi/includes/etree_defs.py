from .._libxml2 import ffi, lib as tree

def _isString(obj):
    return isinstance(obj, basestring)

def _getNs(c_node):
    if not c_node.ns:
        return ffi.NULL
    else:
        return c_node.ns.href

def _isElement(c_node):
    c_type = c_node.type
    return (c_type == tree.XML_ELEMENT_NODE or
            c_type == tree.XML_COMMENT_NODE or
            c_type == tree.XML_ENTITY_REF_NODE or
            c_type == tree.XML_PI_NODE)

def _isElementOrXInclude(c_node):
    return _isElement(c_node) or c_node.type in (
        tree.XML_XINCLUDE_START,
        tree.XML_XINCLUDE_END)

def ELEMENT_MATCH(c_node, only_elements):
    if only_elements:
        return _isElement(c_node)
    return True

def ADVANCE_TO_NEXT(c_node, only_elements):
    while c_node and not ELEMENT_MATCH(c_node, only_elements):
        c_node = c_node.next
    return c_node

class ForEachFrom(object):
    def __init__(self, c_tree_top, c_node, inclusive, only_elements):
        self.c_tree_top = c_tree_top
        self.only_elements = only_elements
        self.c_node = c_node
        if not c_node:
            self.c_current = None
            return
        elif not ELEMENT_MATCH(c_node, only_elements):
            # we skip the node, so 'inclusive' is irrelevant
            if c_node == c_tree_top:
                self.c_node = ffi.NULL  # Nothing to traverse
            else:
                c_node = c_node.next
                self.c_node = ADVANCE_TO_NEXT(c_node, only_elements)
        elif not inclusive:
            # skip the first node
            self.c_node = self.TRAVERSE_TO_NEXT()
        self.c_current = self.c_node

    def __iter__(self):
        return self

    def __next__(self):
        if self.c_current:
            c_next, self.c_current = self.c_current, None
            return c_next
        if not self.c_node:
            raise StopIteration
        self.c_node = self.TRAVERSE_TO_NEXT()
        if not self.c_node:
            raise StopIteration
        return self.c_node
    next = __next__

    def TRAVERSE_TO_NEXT(self):
        # walk through children first
        c_node = self.c_node
        c_next = c_node.children
        if c_next:
            if (c_node.type == tree.XML_ENTITY_REF_NODE or
                c_node.type == tree.XML_DTD_NODE):
                c_next = ffi.NULL
            else:
                c_next = ADVANCE_TO_NEXT(c_next, self.only_elements)
        if not c_next and c_node != self.c_tree_top:
            # try siblings
            c_next = c_node.next
            c_next = ADVANCE_TO_NEXT(c_next, self.only_elements)
            # back off through parents
            while not c_next:
                c_node = c_node.parent
                if not c_node:
                    break
                if c_node == self.c_tree_top:
                    break
                if self.only_elements and not _isElement(c_node):
                    break
                # we already traversed the parents -> siblings
                c_next = c_node.next
                c_next = ADVANCE_TO_NEXT(c_next, self.only_elements)
        return c_next


def FOR_EACH_FROM(c_tree_top, c_node, inclusive):
    return ForEachFrom(c_tree_top, c_node, inclusive,
                       only_elements=False)

def FOR_EACH_ELEMENT_FROM(c_tree_top, c_node, inclusive):
    return ForEachFrom(c_tree_top, c_node, inclusive,
                       only_elements=True)


