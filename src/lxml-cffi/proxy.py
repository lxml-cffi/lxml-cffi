from .includes import tree
from .includes.etree_defs import FOR_EACH_ELEMENT_FROM, FOR_EACH_FROM
from .includes import ffi
from .parser import _copyDoc

from .apihelpers import _removeText

def getProxy(c_node):
    u"""Get a proxy for a given node.
    """
    #print "getProxy for:", <int>c_node
    userdata = c_node._private
    if not userdata:
        return None
    try:
        proxy = ffi.from_handle(userdata)
    except RuntimeError:
        return None
    return proxy

def hasProxy(c_node):
    return bool(c_node._private)

def _registerProxy(proxy, doc, c_node):
    u"""Register a proxy and type for the node it's proxying for.
    """
    #print "registering for:", <int>proxy._c_node
    assert not hasProxy(c_node), u"double registering proxy!"
    proxy._doc = doc
    proxy._c_node = c_node
    userdata = ffi.new_handle(proxy)
    proxy._keepalive = userdata
    c_node._private = userdata

def _unregisterProxy(proxy):
    u"""Unregister a proxy for the node it's proxying for.
    """
    c_node = proxy._c_node
    userdata = c_node._private
    try:
        obj = ffi.from_handle(userdata)
    except RuntimeError:
        # Our proxy is dying, nothing else to do
        pass
    else:
        assert obj is proxy, u"Tried to unregister unknown proxy"
    assert proxy._keepalive == userdata
    c_node._private = ffi.NULL
    del proxy._keepalive
    return 0

def detachProxy(proxy):
    _unregisterProxy(proxy)
    proxy._c_node = tree.ffi.NULL

################################################################################
# temporarily make a node the root node of its document

def _fakeRootDoc(c_base_doc, c_node):
    return _plainFakeRootDoc(c_base_doc, c_node, 1)

def _plainFakeRootDoc(c_base_doc, c_node, with_siblings):
    # build a temporary document that has the given node as root node
    # note that copy and original must not be modified during its lifetime!!
    # always call _destroyFakeDoc() after use!
    if with_siblings or (not c_node.prev and not c_node.next):
        c_root = tree.xmlDocGetRootElement(c_base_doc)
        if c_root == c_node:
            # already the root node, no siblings
            return c_base_doc

    c_doc  = _copyDoc(c_base_doc, 0)                   # non recursive!
    c_new_root = tree.xmlDocCopyNode(c_node, c_doc, 2) # non recursive!
    tree.xmlDocSetRootElement(c_doc, c_new_root)
    _copyParentNamespaces(c_node, c_new_root)

    c_new_root.children = c_node.children
    c_new_root.last = c_node.last
    c_new_root.next = c_new_root.prev = tree.ffi.NULL

    # store original node
    c_doc._private = c_node

    # divert parent pointers of children
    c_child = c_new_root.children
    while c_child:
        c_child.parent = c_new_root
        c_child = c_child.next

    c_doc.children = c_new_root
    return c_doc

def _destroyFakeDoc(c_base_doc, c_doc):
    # delete a temporary document
    if c_doc == c_base_doc:
        return
    c_root = tree.xmlDocGetRootElement(c_doc)

    # restore parent pointers of children
    c_parent = tree.ffi.cast("xmlNodePtr", c_doc._private)
    c_child = c_root.children
    while c_child:
        c_child.parent = c_parent
        c_child = c_child.next

    # prevent recursive removal of children
    c_root.children = c_root.last = tree.ffi.NULL
    tree.xmlFreeDoc(c_doc)

def _fakeDocElementFactory(doc, c_element):
    u"""Special element factory for cases where we need to create a fake
    root document, but still need to instantiate arbitrary nodes from
    it.  If we instantiate the fake root node, things will turn bad
    when it's destroyed.

    Instead, if we are asked to instantiate the fake root node, we
    instantiate the original node instead.
    """
    from .etree import _elementFactory
    if c_element.doc != doc._c_doc:
        if c_element.doc._private:
            if c_element == c_element.doc.children:
                c_element = tree.ffi.cast("xmlNodePtr", c_element.doc._private)
                #assert c_element.type == tree.XML_ELEMENT_NODE
    return _elementFactory(doc, c_element)

################################################################################
# support for freeing tree elements when proxy objects are destroyed

def attemptDeallocation(c_node):
    u"""Attempt deallocation of c_node (or higher up in tree).
    """
    # could be we actually aren't referring to the tree at all
    if not c_node:
        #print "not freeing, node is NULL"
        return 0
    c_top = getDeallocationTop(c_node)
    if c_top:
        #print "freeing:", c_top.name
        _removeText(c_top.next) # tail
        tree.xmlFreeNode(c_top)
        return 1
    return 0

def getDeallocationTop(c_node):
    u"""Return the top of the tree that can be deallocated, or None.
    """
    #print "trying to do deallocating:", c_node.type
    if c_node._private:
        #print "Not freeing: proxies still exist"
        return None
    while c_node.parent:
        c_node = c_node.parent
        #print "checking:", c_current.type
        if c_node.type == tree.XML_DOCUMENT_NODE or \
               c_node.type == tree.XML_HTML_DOCUMENT_NODE:
            #print "not freeing: still in doc"
            return None
        # if we're still attached to the document, don't deallocate
        if hasProxy(c_node):
            #print "Not freeing: proxies still exist"
            return None
    # see whether we have children to deallocate
    if canDeallocateChildNodes(c_node):
        return c_node
    else:
        return tree.ffi.NULL

def canDeallocateChildNodes(c_parent):
    c_node = c_parent.children
    for c_node in FOR_EACH_ELEMENT_FROM(c_parent, c_parent, 0):
        if c_node._private:
            return 0
    return 1

################################################################################
# fix _Document references and namespaces when a node changes documents

def _copyParentNamespaces(c_from_node, c_to_node):
    u"""Copy the namespaces of all ancestors of c_from_node to c_to_node.
    """
    c_parent = c_from_node.parent
    while c_parent and (tree._isElementOrXInclude(c_parent) or
                        c_parent.type == tree.XML_DOCUMENT_NODE):
        c_new_ns = c_parent.nsDef
        while c_new_ns:
            # libxml2 will check if the prefix is already defined
            tree.xmlNewNs(c_to_node, c_new_ns.href, c_new_ns.prefix)
            c_new_ns = c_new_ns.next
        c_parent = c_parent.parent

class _nscache:
    pass

def _appendToNsCache(c_ns_cache,
                     c_old_ns, c_new_ns):
    c_ns_cache.old.append(c_old_ns)
    c_ns_cache.new.append(c_new_ns)

def _stripRedundantNamespaceDeclarations(c_element, c_ns_cache, c_del_ns_list):
    u"""Removes namespace declarations from an element that are already
    defined in its parents.  Does not free the xmlNs's, just prepends
    them to the c_del_ns_list.
    """
    # use a xmlNs** to handle assignments to "c_element.nsDef" correctly
    c_nsdef = tree.ffi.addressof(c_element, 'nsDef')
    while c_nsdef[0]:
        c_ns = tree.xmlSearchNsByHref(
            c_element.doc, c_element.parent, c_nsdef[0].href)
        if not c_ns:
            # new namespace href => keep and cache the ns declaration
            _appendToNsCache(c_ns_cache, c_nsdef[0], c_nsdef[0])
            c_nsdef = tree.ffi.addressof(c_nsdef[0], 'next')
        else:
            # known namespace href => cache mapping and strip old ns
            _appendToNsCache(c_ns_cache, c_nsdef[0], c_ns)
            # cut out c_nsdef.next and prepend it to garbage chain
            c_ns_next = c_nsdef[0].next
            c_nsdef[0].next = c_del_ns_list
            c_del_ns_list = c_nsdef[0]
            c_nsdef[0] = c_ns_next
    return c_del_ns_list

def moveNodeToDocument(doc, c_source_doc, c_element):
    u"""Fix the xmlNs pointers of a node and its subtree that were moved.

    Originally copied from libxml2's xmlReconciliateNs().  Expects
    libxml2 doc pointers of node to be correct already, but fixes
    _Document references.

    For each node in the subtree, we do this:

    1) Remove redundant declarations of namespace that are already
       defined in its parents.

    2) Replace namespaces that are *not* defined on the node or its
       parents by the equivalent namespace declarations that *are*
       defined on the node or its parents (possibly using a different
       prefix).  If a namespace is unknown, declare a new one on the
       node.

    3) Reassign the names of tags and attribute from the dict of the
       target document *iff* it is different from the dict used in the
       source subtree.

    4) Set the Document reference to the new Document (if different).
       This is done on backtracking to keep the original Document
       alive as long as possible, until all its elements are updated.

    Note that the namespace declarations are removed from the tree in
    step 1), but freed only after the complete subtree was traversed
    and all occurrences were replaced by tree-internal pointers.
    """
    proxy_count = 0

    if not tree._isElementOrXInclude(c_element):
        return 0

    c_start_node = c_element
    c_del_ns_list = tree.ffi.NULL

    c_ns_cache = _nscache()
    c_ns_cache.new = []
    c_ns_cache.old = []

    for c_element in FOR_EACH_FROM(c_element, c_element, 1):
        if tree._isElementOrXInclude(c_element):
            if hasProxy(c_element):
                proxy_count += 1

            # 1) cut out namespaces defined here that are already known by
            #    the ancestors
            if c_element.nsDef:
                c_del_ns_list = _stripRedundantNamespaceDeclarations(
                    c_element, c_ns_cache, c_del_ns_list)

            # 2) make sure the namespaces of an element and its attributes
            #    are declared in this document (i.e. on the node or its parents)
            c_node = c_element
            while c_node:
                if c_node.ns:
                    c_ns = None
                    for i in xrange(len(c_ns_cache.old)):
                        if c_node.ns == c_ns_cache.old[i]:
                            if (c_node.type == tree.XML_ATTRIBUTE_NODE
                                and c_node.ns.prefix
                                and not c_ns_cache.new[i].prefix):
                                # avoid dropping prefix from attributes
                                continue
                            c_ns = c_ns_cache.new[i]
                            break

                    if not c_ns:
                        # not in cache or not acceptable
                        # => find a replacement from this document
                        c_href = tree.ffi.string(c_node.ns.href)
                        c_ns = doc._findOrBuildNodeNs(
                            c_start_node, c_href, c_node.ns.prefix,
                            c_node.type == tree.XML_ATTRIBUTE_NODE)
                        _appendToNsCache(c_ns_cache, c_node.ns, c_ns)
                    c_node.ns = c_ns

                if c_node == c_element:
                    # after the element, continue with its attributes
                    c_node = c_element.properties
                else:
                    c_node = c_node.next

    # free now unused namespace declarations
    if c_del_ns_list:
        tree.xmlFreeNsList(c_del_ns_list)

    # 3) fix the names in the tree if we moved it from a different thread
    if doc._c_doc.dict != c_source_doc.dict:
        fixThreadDictNames(c_start_node, c_source_doc.dict, doc._c_doc.dict)

    # 4) fix _Document references
    #    (and potentially deallocate the source document)
    if proxy_count > 0:
        if proxy_count == 1 and c_start_node._private:
            proxy = getProxy(c_start_node)
            if proxy is not None:
                proxy._doc = doc
            else:
                fixElementDocument(c_start_node, doc, proxy_count)
        else:
            fixElementDocument(c_start_node, doc, proxy_count)
    return 0

def fixElementDocument(c_element, doc, proxy_count):
    for c_node in FOR_EACH_FROM(c_element, c_element, 1):
        proxy = getProxy(c_node)
        if proxy is not None:
            proxy._doc = doc
            proxy_count -= 1
            if proxy_count == 0:
                return

def fixThreadDictNames(c_element, c_src_dict, c_dict):
    # re-assign the names of tags and attributes
    #
    # this should only be called when the element is based on a
    # different libxml2 tag name dictionary
    if c_element.type == tree.XML_DOCUMENT_NODE or \
            c_element.type == tree.XML_HTML_DOCUMENT_NODE:
        # may define "xml" namespace
        fixThreadDictNsForNode(c_element, c_src_dict, c_dict)
        c_element = c_element.children
        while c_element:
            fixThreadDictNamesForNode(c_element, c_src_dict, c_dict)
            c_element = c_element.next
    elif tree._isElementOrXInclude(c_element):
        fixThreadDictNamesForNode(c_element, c_src_dict, c_dict)

def fixThreadDictNamesForNode(c_element, c_src_dict, c_dict):
    for c_node in FOR_EACH_FROM(c_element, c_element, 1):
        if c_node.name:
            fixThreadDictNameForNode(c_node, c_src_dict, c_dict)
        if c_node.type in (tree.XML_ELEMENT_NODE, tree.XML_XINCLUDE_START):
            fixThreadDictNamesForAttributes(
                c_node.properties, c_src_dict, c_dict)
            fixThreadDictNsForNode(c_node, c_src_dict, c_dict)
        elif c_node.type == tree.XML_TEXT_NODE:
            # libxml2's SAX2 parser interns some indentation space
            fixThreadDictContentForNode(c_node, c_src_dict, c_dict)

def fixThreadDictNamesForAttributes(c_attr, c_src_dict, c_dict):
    c_node = c_attr
    while c_node:
        fixThreadDictNameForNode(c_node, c_src_dict, c_dict)
        # libxml2 keeps some (!) attribute values in the dict
        c_child = c_node.children
        while c_child:
            fixThreadDictContentForNode(c_child, c_src_dict, c_dict)
            c_child = c_child.next
        c_node = c_node.next

def fixThreadDictNameForNode(c_node, c_src_dict, c_dict):
    c_name = c_node.name
    if (c_name and
        c_node.type not in (tree.XML_TEXT_NODE, tree.XML_COMMENT_NODE)):
        if tree.xmlDictOwns(c_src_dict, c_node.name):
            # c_name can be NULL on memory error, but we don't handle that here
            c_name = tree.xmlDictLookup(c_dict, c_name, -1)
            if c_name:
                c_node.name = c_name

def fixThreadDictContentForNode(c_node, c_src_dict, c_dict):
    if (c_node.content and
        c_node.content != tree.ffi.addressof(c_node, 'properties')):
        if tree.xmlDictOwns(c_src_dict, c_node.content):
            # result can be NULL on memory error, but we don't handle that here
            c_node.content = tree.xmlDictLookup(c_dict, c_node.content, -1)

def fixThreadDictNsForNode(c_node, c_src_dict, c_dict):
    c_ns = c_node.nsDef
    while c_ns:
        if c_ns.href:
            if tree.xmlDictOwns(c_src_dict, c_ns.href):
                c_ns.href = tree.xmlDictLookup(c_dict, c_ns.href, -1)
        if c_ns.prefix:
            if tree.xmlDictOwns(c_src_dict, c_ns.prefix):
                c_ns.prefix = tree.xmlDictLookup(c_dict, c_ns.prefix, -1)
        c_ns = c_ns.next
