# SAX-like interfaces

from .parser import _ParserContext, _fixHtmlDictNodeNames
from inspect import getargspec as inspect_getargspec
from .apihelpers import _namespacedNameFromNsName, _makeElement, _makeSubElement
from .apihelpers import funicode, funicodeOrNone, funicodeOrEmpty, _appendChild
from .etree import IMMUTABLE_EMPTY_MAPPING
from .etree import _documentFactory, _elementFactory, _Element
from . import python
from ._libxml2 import ffi, lib

xmlparser = xmlerror = tree = lib


SAX_EVENT_START   =  1
SAX_EVENT_END     =  2
SAX_EVENT_DATA    =  4
SAX_EVENT_DOCTYPE =  8
SAX_EVENT_PI      = 16
SAX_EVENT_COMMENT = 32

PARSE_EVENT_FILTER_START     =  1
PARSE_EVENT_FILTER_END       =  2
PARSE_EVENT_FILTER_START_NS  =  4
PARSE_EVENT_FILTER_END_NS    =  8
PARSE_EVENT_FILTER_COMMENT   = 16
PARSE_EVENT_FILTER_PI        = 32

def _buildParseEventFilter(events):
    event_filter = 0
    for event in events:
        if event == 'start':
            event_filter |= PARSE_EVENT_FILTER_START
        elif event == 'end':
            event_filter |= PARSE_EVENT_FILTER_END
        elif event == 'start-ns':
            event_filter |= PARSE_EVENT_FILTER_START_NS
        elif event == 'end-ns':
            event_filter |= PARSE_EVENT_FILTER_END_NS
        elif event == 'comment':
            event_filter |= PARSE_EVENT_FILTER_COMMENT
        elif event == 'pi':
            event_filter |= PARSE_EVENT_FILTER_PI
        else:
            raise ValueError, u"invalid event name '%s'" % event
    return event_filter

class _SaxParserTarget(object):
    def __init__(self):
        self._sax_event_filter = 0

    def _handleSaxStart(self, tag, attrib, nsmap):
        return None
    def _handleSaxEnd(self, tag):
        return None
    def _handleSaxData(self, data):
        return 0
    def _handleSaxDoctype(self, root_tag, public_id, system_id):
        return 0
    def _handleSaxPi(self, target, data):
        return None
    def _handleSaxComment(self, comment):
        return None

class _SaxParserContext(_ParserContext):
    u"""This class maps SAX2 events to parser target events.
    """
    _origSaxCData = None
    _target = None
    _event_filter = 0
    _root = None

    def __init__(self, parser):
        _ParserContext.__init__(self)
        self._ns_stack = []
        self._node_stack = []
        self._parser = parser
        self.events_iterator = _ParseEventsIterator()

    def _setSaxParserTarget(self, target):
        self._target = target

    def _initParserContext(self, c_ctxt):
        _ParserContext._initParserContext(self, c_ctxt)
        if self._target is not None:
            self._connectTarget(c_ctxt)
        elif self._event_filter:
            self._connectEvents(c_ctxt)

    def _connectTarget(self, c_ctxt):
        """wrap original SAX2 callbacks to call into parser target"""
        sax = c_ctxt.sax
        self._origSaxStart = sax.startElementNs = ffi.NULL
        self._origSaxStartNoNs = sax.startElement = ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_START:
            # intercept => overwrite orig callback
            # FIXME: also intercept on when collecting END events
            if sax.initialized == xmlparser.XML_SAX2_MAGIC:
                sax.startElementNs = _handleSaxTargetStart
            sax.startElement = _handleSaxTargetStartNoNs

        self._origSaxEnd = sax.endElementNs = ffi.NULL
        self._origSaxEndNoNs = sax.endElement = ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_END:
            if sax.initialized == xmlparser.XML_SAX2_MAGIC:
                sax.endElementNs = _handleSaxEnd
            sax.endElement = _handleSaxEndNoNs

        self._origSaxData = sax.characters = sax.cdataBlock = ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_DATA:
            sax.characters = sax.cdataBlock = _handleSaxData

        # doctype propagation is always required for entity replacement
        self._origSaxDoctype = sax.internalSubset
        if self._target._sax_event_filter & SAX_EVENT_DOCTYPE:
            sax.internalSubset = _handleSaxTargetDoctype

        self._origSaxPI = sax.processingInstruction = ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_PI:
            sax.processingInstruction = _handleSaxPI

        self._origSaxComment = sax.comment = ffi.NULL
        if self._target._sax_event_filter & SAX_EVENT_COMMENT:
            sax.comment = _handleSaxTargetComment

        # enforce entity replacement
        sax.reference = ffi.NULL
        c_ctxt.replaceEntities = 1

    def _connectEvents(self, c_ctxt):
        """wrap original SAX2 callbacks to collect parse events"""
        sax = c_ctxt.sax
        self._origSaxStartDocument = sax.startDocument
        sax.startDocument = _handleSaxStartDocument
        self._origSaxStart = sax.startElementNs
        self._origSaxStartNoNs = sax.startElement
        # only override start event handler if needed
        if (self._event_filter == 0 or
            self._event_filter & (PARSE_EVENT_FILTER_START |
                                  PARSE_EVENT_FILTER_END |
                                  PARSE_EVENT_FILTER_START_NS |
                                  PARSE_EVENT_FILTER_END_NS)):
            sax.startElementNs = _handleSaxStart
            sax.startElement = _handleSaxStartNoNs

        self._origSaxEnd = sax.endElementNs
        self._origSaxEndNoNs = sax.endElement
        # only override end event handler if needed
        if (self._event_filter == 0 or
            self._event_filter & (PARSE_EVENT_FILTER_END |
                                  PARSE_EVENT_FILTER_END_NS)):
            sax.endElementNs = _handleSaxEnd
            sax.endElement = _handleSaxEndNoNs

        self._origSaxComment = sax.comment
        if self._event_filter & PARSE_EVENT_FILTER_COMMENT:
            sax.comment = _handleSaxComment

        self._origSaxPI = sax.processingInstruction
        if self._event_filter & PARSE_EVENT_FILTER_PI:
            sax.processingInstruction = _handleSaxPIEvent

    def _setEventFilter(self, events, tag):
        self._event_filter = _buildParseEventFilter(events)
        if not self._event_filter or tag is None or tag == '*':
            self._matcher = None
        else:
            from .etree import _MultiTagMatcher
            self._matcher = _MultiTagMatcher(tag)

    def startDocument(self, c_doc):
        try:
            self._doc = _documentFactory(c_doc, self._parser)
        finally:
            self._parser = None  # clear circular reference ASAP
        if self._matcher is not None:
            self._matcher.cacheTags(self._doc, True) # force entry in libxml2 dict

    def pushEvent(self, event, c_node):
        if self._root is None:
            root = self._doc.getroot()
            if root is not None and root._c_node.type == tree.XML_ELEMENT_NODE:
                self._root = root
        node = _elementFactory(self._doc, c_node)
        self.events_iterator._events.append( (event, node) )

    def flushEvents(self):
        events = self.events_iterator._events
        while self._node_stack:
            events.append( ('end', self._node_stack.pop()) )
            _pushSaxNsEndEvents(self)
        while self._ns_stack:
            _pushSaxNsEndEvents(self)

    def _handleSaxException(self, c_ctxt):
        if c_ctxt.errNo == xmlerror.XML_ERR_OK:
            c_ctxt.errNo = xmlerror.XML_ERR_INTERNAL_ERROR
        # stop parsing immediately
        c_ctxt.wellFormed = 0
        c_ctxt.disableSAX = 1
        self._store_raised()

class _ParseEventsIterator(object):
    """A reusable parse events iterator"""

    def __init__(self):
        self._events = []
        self._event_index = 0

    def __iter__(self):
        return self

    def __next__(self):
        events = self._events
        event_index = self._event_index
        if event_index * 2 >= len(events):
            if event_index:
                # clean up from time to time
                del events[:event_index]
                self._event_index = event_index = 0
            if event_index >= len(events):
                raise StopIteration
        item = events[event_index]
        self._event_index = event_index + 1
        return item
    next = __next__

def _appendNsEvents(context, c_nb_namespaces, c_namespaces):
    for i in xrange(c_nb_namespaces):
        ns_tuple = (funicodeOrEmpty(c_namespaces[0]),
                    funicode(c_namespaces[1]))
        context.events_iterator._events.append( ("start-ns", ns_tuple) )
        c_namespaces += 2

@ffi.callback("startElementNsSAX2Func")
def _handleSaxStart(ctxt, c_localname, c_prefix,
                    c_namespace, c_nb_namespaces,
                    c_namespaces,
                    c_nb_attributes, c_nb_defaulted,
                    c_attributes):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        if (c_nb_namespaces and
                context._event_filter & PARSE_EVENT_FILTER_START_NS):
            _appendNsEvents(context, c_nb_namespaces, c_namespaces)
        context._origSaxStart(c_ctxt, c_localname, c_prefix, c_namespace,
                              c_nb_namespaces, c_namespaces, c_nb_attributes,
                              c_nb_defaulted, c_attributes)
        if c_ctxt.html:
            _fixHtmlDictNodeNames(c_ctxt.dict, c_ctxt.node)

        if context._event_filter & PARSE_EVENT_FILTER_END_NS:
            context._ns_stack.append(c_nb_namespaces)
        if context._event_filter & (PARSE_EVENT_FILTER_END |
                                    PARSE_EVENT_FILTER_START):
            _pushSaxStartEvent(context, c_ctxt, c_namespace,
                               c_localname, None)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions

@ffi.callback("startElementNsSAX2Func")
def _handleSaxTargetStart(
        ctxt, c_localname, c_prefix,
        c_namespace, c_nb_namespaces,
        c_namespaces,
        c_nb_attributes, c_nb_defaulted,
        c_attributes):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        if (c_nb_namespaces and
            context._event_filter & PARSE_EVENT_FILTER_START_NS):
            _appendNsEvents(context, c_nb_namespaces, c_namespaces)
        if c_nb_defaulted > 0:
            # only add default attributes if we asked for them
            if c_ctxt.loadsubset & xmlparser.XML_COMPLETE_ATTRS == 0:
                c_nb_attributes -= c_nb_defaulted
        if c_nb_attributes == 0:
            attrib = IMMUTABLE_EMPTY_MAPPING
        else:
            attrib = {}
            for i in xrange(c_nb_attributes):
                name = _namespacedNameFromNsName(
                    c_attributes[2], c_attributes[0])
                if not c_attributes[3]:
                    value = ''
                else:
                    value = ffi.buffer(
                        c_attributes[3],
                        c_attributes[4] - c_attributes[3])[:]
                    value = value.decode('utf8')
                attrib[name] = value
                c_attributes += 5
        if c_nb_namespaces == 0:
            nsmap = IMMUTABLE_EMPTY_MAPPING
        else:
            nsmap = {}
            for i in xrange(c_nb_namespaces):
                prefix = funicodeOrNone(c_namespaces[0])
                nsmap[prefix] = funicode(c_namespaces[1])
                c_namespaces += 2
        element = _callTargetSaxStart(
            context, c_ctxt,
            _namespacedNameFromNsName(c_namespace, c_localname),
            attrib, nsmap)

        if context._event_filter & PARSE_EVENT_FILTER_END_NS:
            context._ns_stack.append(c_nb_namespaces)
        if context._event_filter & (PARSE_EVENT_FILTER_END |
                                    PARSE_EVENT_FILTER_START):
            _pushSaxStartEvent(context, c_ctxt, c_namespace,
                               c_localname, element)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("startElementSAXFunc")
def _handleSaxStartNoNs(ctxt, c_name, c_attributes):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        context._origSaxStartNoNs(c_ctxt, c_name, c_attributes)
        if c_ctxt.html:
            _fixHtmlDictNodeNames(c_ctxt.dict, c_ctxt.node)
        if context._event_filter & (PARSE_EVENT_FILTER_END |
                                    PARSE_EVENT_FILTER_START):
            _pushSaxStartEvent(context, c_ctxt, ffi.NULL, c_name, None)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("startElementSAXFunc")
def _handleSaxTargetStartNoNs(ctxt, c_name, c_attributes):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        if not c_attributes:
            attrib = IMMUTABLE_EMPTY_MAPPING
        else:
            attrib = {}
            while c_attributes[0]:
                name = funicode(c_attributes[0])
                attrib[name] = funicodeOrEmpty(c_attributes[1])
                c_attributes += 2
        element = _callTargetSaxStart(
            context, c_ctxt, funicode(c_name),
            attrib, IMMUTABLE_EMPTY_MAPPING)
        if context._event_filter & (PARSE_EVENT_FILTER_END |
                                    PARSE_EVENT_FILTER_START):
            _pushSaxStartEvent(context, c_ctxt, ffi.NULL, c_name, element)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


def _callTargetSaxStart(context, c_ctxt,
                        tag, attrib, nsmap):
    element = context._target._handleSaxStart(tag, attrib, nsmap)
    if element is not None and c_ctxt.input:
        if isinstance(element, _Element):
            element._c_node.line = (
                c_ctxt.input.line if c_ctxt.input.line < 65535 else 65535)
    return element

def _pushSaxStartEvent(context, c_ctxt,
                       c_href, c_name, node):
    if (context._matcher is None or
        context._matcher.matchesNsTag(c_href, c_name)):
        if node is None and context._target is None:
            assert context._doc is not None
            node = _elementFactory(context._doc, c_ctxt.node)
        if context._event_filter & PARSE_EVENT_FILTER_START:
            context.events_iterator._events.append(('start', node))
        if (context._target is None and
                context._event_filter & PARSE_EVENT_FILTER_END):
            context._node_stack.append(node)

@ffi.callback("endElementNsSAX2Func")
def _handleSaxEnd(ctxt, c_localname, c_prefix, c_namespace):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        if context._target is not None:
            node = context._target._handleSaxEnd(
                _namespacedNameFromNsName(c_namespace, c_localname))
        else:
            context._origSaxEnd(c_ctxt, c_localname, c_prefix, c_namespace)
            node = None
        _pushSaxEndEvent(context, c_namespace, c_localname, node)
        _pushSaxNsEndEvents(context)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("endElementSAXFunc")
def _handleSaxEndNoNs(ctxt, c_name):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        if context._target is not None:
            node = context._target._handleSaxEnd(funicode(c_name))
        else:
            context._origSaxEndNoNs(c_ctxt, c_name)
            node = None
        _pushSaxEndEvent(context, ffi.NULL, c_name, node)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


NS_END_EVENT = ('end-ns', None)

def _pushSaxNsEndEvents(context):
    if context._event_filter & PARSE_EVENT_FILTER_END_NS:
        for i in range(context._ns_stack.pop()):
            context.events_iterator._events.append(NS_END_EVENT)


def _pushSaxEndEvent(context, c_href, c_name, node):
    if context._event_filter & PARSE_EVENT_FILTER_END:
        if (context._matcher is None or
                context._matcher.matchesNsTag(c_href, c_name)):
            if context._target is None:
                node = context._node_stack.pop()
            context.events_iterator._events.append(('end', node))


@ffi.callback("charactersSAXFunc")
def _handleSaxData(ctxt, c_data, data_len):
    # can only be called if parsing with a target
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        data = ffi.buffer(c_data, data_len)[:]
        data = data.decode('utf8')
        context._target._handleSaxData(data)
    except:
        context._handleSaxException(c_ctxt)


@ffi.callback("internalSubsetSAXFunc")
def _handleSaxTargetDoctype(ctxt, c_name,
                            c_public, c_system):
    # can only be called if parsing with a target
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        context._target._handleSaxDoctype(
            funicodeOrNone(c_name),
            funicodeOrNone(c_public),
            funicodeOrNone(c_system))
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("startDocumentSAXFunc")
def _handleSaxStartDocument(ctxt):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    context._origSaxStartDocument(ctxt)
    c_doc = c_ctxt.myDoc
    try:
        context.startDocument(c_doc)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("processingInstructionSAXFunc")
def _handleSaxPI(ctxt, c_target, c_data):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        pi = context._target._handleSaxPi(
            funicodeOrNone(c_target),
            funicodeOrEmpty(c_data))
        if context._event_filter & PARSE_EVENT_FILTER_PI:
            context.events_iterator._events.append(('pi', pi))
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("processingInstructionSAXFunc")
def _handleSaxPIEvent(ctxt, target, data):
    # can only be called when collecting pi events
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    context._origSaxPI(ctxt, target, data)
    c_node = _findLastEventNode(c_ctxt)
    if not c_node:
        return
    try:
        context.pushEvent('pi', c_node)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("commentSAXFunc")
def _handleSaxTargetComment(ctxt, c_data):
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    try:
        comment = context._target._handleSaxComment(funicodeOrEmpty(c_data))
        if context._event_filter & PARSE_EVENT_FILTER_COMMENT:
            context.events_iterator._events.append(('comment', comment))
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


@ffi.callback("commentSAXFunc")
def _handleSaxComment(ctxt, text):
    # can only be called when collecting comment events
    c_ctxt = ffi.cast("xmlParserCtxtPtr", ctxt)
    if not c_ctxt._private or c_ctxt.disableSAX:
        return
    context = ffi.from_handle(c_ctxt._private)
    context._origSaxComment(ctxt, text)
    c_node = _findLastEventNode(c_ctxt)
    if not c_node:
        return
    try:
        context.pushEvent('comment', c_node)
    except:
        context._handleSaxException(c_ctxt)
    finally:
        return  # swallow any further exceptions


def _findLastEventNode(c_ctxt):
    # this mimics what libxml2 creates for comments/PIs
    if c_ctxt.inSubset == 1:
        return c_ctxt.myDoc.intSubset.last
    elif c_ctxt.inSubset == 2:
        return c_ctxt.myDoc.extSubset.last
    elif not c_ctxt.node:
        return c_ctxt.myDoc.last
    elif c_ctxt.node.type == tree.XML_ELEMENT_NODE:
        return c_ctxt.node.last
    else:
        return c_ctxt.node.next


############################################################
## ET compatible XML tree builder
############################################################

class TreeBuilder(_SaxParserTarget):
    u"""TreeBuilder(self, element_factory=None, parser=None)
    Parser target that builds a tree.

    The final tree is returned by the ``close()`` method.
    """
    def __init__(self, element_factory=None, parser=None):
        self._sax_event_filter = \
            SAX_EVENT_START | SAX_EVENT_END | SAX_EVENT_DATA | \
            SAX_EVENT_PI | SAX_EVENT_COMMENT
        self._data = [] # data collector
        self._element_stack = [] # element stack
        self._element_stack_pop = self._element_stack.pop
        self._last = None # last element
        self._in_tail = 0 # true if we're after an end tag
        self._factory = element_factory
        self._parser = parser

    def _flush(self):
        if self._data:
            if self._last is not None:
                text = u"".join(self._data)
                if self._in_tail:
                    assert self._last.tail is None, u"internal error (tail)"
                    self._last.tail = text
                else:
                    assert self._last.text is None, u"internal error (text)"
                    self._last.text = text
            del self._data[:]
        return 0

    # internal SAX event handlers

    def _handleSaxStart(self, tag, attrib, nsmap):
        self._flush()
        if self._factory is not None:
            self._last = self._factory(tag, attrib)
            if self._element_stack:
                _appendChild(self._element_stack[-1], self._last)
        elif self._element_stack:
            self._last = _makeSubElement(
                self._element_stack[-1], tag, None, None, attrib, nsmap, None)
        else:
            self._last = _makeElement(
                tag, ffi.NULL, None, self._parser, None, None, attrib, nsmap, None)
        self._element_stack.append(self._last)
        self._in_tail = 0
        return self._last

    def _handleSaxEnd(self, tag):
        self._flush()
        self._last = self._element_stack_pop()
        self._in_tail = 1
        return self._last

    def _handleSaxData(self, data):
        self._data.append(data)

    def _handleSaxPi(self, target, data):
        self._flush()
        from .etree import ProcessingInstruction
        self._last = ProcessingInstruction(target, data)
        if self._element_stack:
            _appendChild(self._element_stack[-1], self._last)
        self._in_tail = 1
        return self._last

    def _handleSaxComment(self, comment):
        self._flush()
        from .etree import Comment
        self._last = Comment(comment)
        if self._element_stack:
            _appendChild(self._element_stack[-1], self._last)
        self._in_tail = 1
        return self._last

    # Python level event handlers

    def close(self):
        u"""close(self)

        Flushes the builder buffers, and returns the toplevel document
        element.
        """
        assert not self._element_stack, u"missing end tags"
        assert self._last is not None, u"missing toplevel element"
        return self._last

    def data(self, data):
        u"""data(self, data)

        Adds text to the current element.  The value should be either an
        8-bit string containing ASCII text, or a Unicode string.
        """
        self._handleSaxData(data)

    def start(self, tag, attrs, nsmap=None):
        u"""start(self, tag, attrs, nsmap=None)

        Opens a new element.
        """
        if nsmap is None:
            nsmap = IMMUTABLE_EMPTY_MAPPING
        return self._handleSaxStart(tag, attrs, nsmap)

    def end(self, tag):
        u"""end(self, tag)

        Closes the current element.
        """
        element = self._handleSaxEnd(tag)
        assert self._last.tag == tag,\
               u"end tag mismatch (expected %s, got %s)" % (
                   self._last.tag, tag)
        return element

    def pi(self, target, data):
        u"""pi(self, target, data)
        """
        return self._handleSaxPi(target, data)

    def comment(self, comment):
        u"""comment(self, comment)
        """
        return self._handleSaxComment(comment)
