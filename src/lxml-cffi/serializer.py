# XML serialization and output functions

import gzip
from io import BytesIO

from .proxy import _fakeRootDoc, _destroyFakeDoc, _plainFakeRootDoc, _copyParentNamespaces
from .includes.etree_defs import _isElement, _isString
from .etree import _ExceptionContext, LxmlError, LxmlSyntaxError
from .xmlerror import _ErrorLog, ErrorTypes
from .includes import xmlerror
from .apihelpers import _assertValidNode, _assertValidDoc, _textNodeOrSkip
from .apihelpers import _encodeFilename, _documentOrRaise, _getNsTag
from .apihelpers import _prefixValidOrRaise
from .apihelpers import _utf8, isutf8, _utf8orNone
from .includes import tree
from .includes import c14n
from . import python

class SerialisationError(LxmlError):
    u"""A libxml2 error that occurred during serialisation.
    """

OUTPUT_METHOD_XML, OUTPUT_METHOD_HTML, OUTPUT_METHOD_TEXT = range(3)

def _findOutputMethod(method):
    if method is None:
        return OUTPUT_METHOD_XML
    method = method.lower()
    if method == "xml":
        return OUTPUT_METHOD_XML
    if method == "html":
        return OUTPUT_METHOD_HTML
    if method == "text":
        return OUTPUT_METHOD_TEXT
    raise ValueError(u"unknown output method %r" % method)

def _textToString(c_node, encoding, with_tail):
    c_buffer = tree.xmlBufferCreate()
    if not c_buffer:
        return python.PyErr_NoMemory()

    if 1:
        error_result = tree.xmlNodeBufGetContent(c_buffer, c_node)
        if with_tail:
            c_text_node = _textNodeOrSkip(c_node.next)
            while c_text_node:
                tree.xmlBufferWriteChar(c_buffer, c_text_node.content)
                c_text_node = _textNodeOrSkip(c_text_node.next)
        c_text = tree.xmlBufferContent(c_buffer)

    if error_result < 0 or not c_text:
        tree.xmlBufferFree(c_buffer)
        raise SerialisationError, u"Error during serialisation (out of memory?)"

    try:
        needs_conversion = 0
        if encoding is unicode:
            needs_conversion = 1
        elif encoding is not None:
            # Python prefers lower case encoding names
            encoding = encoding.lower()
            if encoding not in (u'utf8', u'utf-8'):
                if encoding == u'ascii':
                    if isutf8(c_text):
                        # will raise a decode error below
                        needs_conversion = 1
                else:
                    needs_conversion = 1

        if needs_conversion:
            text = tree.ffi.buffer(
                c_text, tree.xmlBufferLength(c_buffer))[:].decode('utf8')
            if encoding is not unicode:
                encoding = _utf8(encoding)
                text = text.encode(encoding)
        else:
            text = tree.ffi.buffer(
                c_text, tree.xmlBufferLength(c_buffer))[:]
    finally:
        tree.xmlBufferFree(c_buffer)
    return text


def _tostring(element, encoding, doctype, method,
              write_xml_declaration, write_complete_document,
              pretty_print, with_tail, standalone):
    u"""Serialize an element to an encoded string representation of its XML
    tree.
    """
    if element is None:
        return None
    _assertValidNode(element)
    c_method = _findOutputMethod(method)
    if c_method == OUTPUT_METHOD_TEXT:
        return _textToString(element._c_node, encoding, with_tail)
    if encoding is None or encoding is unicode:
        c_enc = tree.ffi.NULL
    else:
        encoding = _utf8(encoding)
        c_enc = encoding
    if doctype is None:
        c_doctype = tree.ffi.NULL
    else:
        doctype = _utf8(doctype)
        c_doctype = doctype
    # it is necessary to *and* find the encoding handler *and* use
    # encoding during output
    enchandler = tree.xmlFindCharEncodingHandler(c_enc)
    if not enchandler and c_enc:
        if encoding is not None:
            encoding = encoding.decode('UTF-8')
        raise LookupError, u"unknown encoding: '%s'" % encoding
    c_buffer = tree.xmlAllocOutputBuffer(enchandler)
    if not c_buffer:
        tree.xmlCharEncCloseFunc(enchandler)
        return python.PyErr_NoMemory()

    if 1:
        _writeNodeToBuffer(c_buffer, element._c_node, c_enc, c_doctype, c_method,
                           write_xml_declaration, write_complete_document,
                           pretty_print, with_tail, standalone)
        tree.xmlOutputBufferFlush(c_buffer)
        if c_buffer.conv:
            c_result_buffer = c_buffer.conv
        else:
            c_result_buffer = c_buffer.buffer

    error_result = c_buffer.error
    if error_result != xmlerror.XML_ERR_OK:
        tree.xmlOutputBufferClose(c_buffer)
        _raiseSerialisationError(error_result)

    try:
        if encoding is unicode:
            result = tree.ffi.buffer(
                tree.xmlBufferContent(c_result_buffer),
                tree.xmlBufferLength(c_result_buffer))[:].decode('UTF-8')
        else:
            result = tree.ffi.buffer(
                tree.xmlBufferContent(c_result_buffer),
                tree.xmlBufferLength(c_result_buffer))[:]
    finally:
        error_result = tree.xmlOutputBufferClose(c_buffer)
    if error_result < 0:
        _raiseSerialisationError(error_result)
    return result

def _tostringC14N(element_or_tree, exclusive, with_comments, inclusive_ns_prefixes):
    from .etree import _Element
    c_buffer = tree.ffi.NULL
    byte_count = -1
    if isinstance(element_or_tree, _Element):
        _assertValidNode(element_or_tree)
        doc = element_or_tree._doc
        c_doc = _plainFakeRootDoc(doc._c_doc, element_or_tree._c_node, 0)
    else:
        doc = _documentOrRaise(element_or_tree)
        _assertValidDoc(doc)
        c_doc = doc._c_doc

    c_inclusive_ns_prefixes = _convert_ns_prefixes(c_doc.dict, inclusive_ns_prefixes) if inclusive_ns_prefixes else c14n.ffi.NULL
    try:
         if 1:
             c_buffer_ptr = c14n.ffi.new("xmlChar*[]", [c_buffer])
             byte_count = c14n.xmlC14NDocDumpMemory(
                 c_doc, tree.ffi.NULL, exclusive, c_inclusive_ns_prefixes, with_comments, c_buffer_ptr)
             c_buffer = c_buffer_ptr[0]

    finally:
         _destroyFakeDoc(doc._c_doc, c_doc)

    if byte_count < 0 or not c_buffer:
        if c_buffer:
            tree.xmlFree(c_buffer)
        raise C14NError, u"C14N failed"
    try:
        result = c14n.ffi.buffer(c_buffer, byte_count)[:]
    finally:
        tree.xmlFree(c_buffer)
    return result

def _raiseSerialisationError(error_result):
    if error_result == xmlerror.XML_ERR_NO_MEMORY:
        return python.PyErr_NoMemory()
    else:
        message = ErrorTypes._getName(error_result)
        if message is None:
            message = u"unknown error %d" % error_result
        raise SerialisationError, message

############################################################
# low-level serialisation functions

def _writeDoctype(c_buffer, c_doctype):
    tree.xmlOutputBufferWrite(c_buffer, len(c_doctype), c_doctype)
    tree.xmlOutputBufferWriteString(c_buffer, "\n")

def _writeNodeToBuffer(c_buffer, c_node, encoding, c_doctype,
                       c_method, write_xml_declaration,
                       write_complete_document,
                       pretty_print, with_tail,
                       standalone):
    c_doc = c_node.doc
    if write_xml_declaration and c_method == OUTPUT_METHOD_XML:
        _writeDeclarationToBuffer(c_buffer, c_doc.version, encoding, standalone)
    if c_doctype:
        _writeDoctype(c_buffer, c_doctype)

    # write internal DTD subset, preceding PIs/comments, etc.
    if write_complete_document and not c_buffer.error:
        if not c_doctype:
            _writeDtdToBuffer(c_buffer, c_doc, c_node.name, encoding)
        _writePrevSiblings(c_buffer, c_node, encoding, pretty_print)

    c_nsdecl_node = c_node
    if not c_node.parent or c_node.parent.type != tree.XML_DOCUMENT_NODE:
        # copy the node and add namespaces from parents
        # this is required to make libxml write them
        c_nsdecl_node = tree.xmlCopyNode(c_node, 2)
        if not c_nsdecl_node:
            c_buffer.error = xmlerror.XML_ERR_NO_MEMORY
            return
        _copyParentNamespaces(c_node, c_nsdecl_node)

        c_nsdecl_node.parent = c_node.parent
        c_nsdecl_node.children = c_node.children
        c_nsdecl_node.last = c_node.last

    # write node
    if c_method == OUTPUT_METHOD_HTML:
        tree.htmlNodeDumpFormatOutput(
            c_buffer, c_doc, c_nsdecl_node, encoding, pretty_print)
    else:
        tree.xmlNodeDumpOutput(
            c_buffer, c_doc, c_nsdecl_node, 0, pretty_print, encoding)

    if c_nsdecl_node != c_node:
        # clean up
        c_nsdecl_node.children = c_nsdecl_node.last = tree.ffi.NULL
        tree.xmlFreeNode(c_nsdecl_node)

    if c_buffer.error:
        return

    # write tail, trailing comments, etc.
    if with_tail:
        _writeTail(c_buffer, c_node, encoding, c_method, pretty_print)
    if write_complete_document:
        _writeNextSiblings(c_buffer, c_node, encoding, pretty_print)
    if pretty_print:
        tree.xmlOutputBufferWrite(c_buffer, 1, "\n")

def _writeDeclarationToBuffer(c_buffer,
                              version, encoding,
                              standalone):
    if not version:
        version = "1.0"
    tree.xmlOutputBufferWrite(c_buffer, 15, "<?xml version='")
    tree.xmlOutputBufferWriteString(c_buffer, version)
    tree.xmlOutputBufferWrite(c_buffer, 12, "' encoding='")
    tree.xmlOutputBufferWriteString(c_buffer, encoding)
    if standalone == 0:
        tree.xmlOutputBufferWrite(c_buffer, 20, "' standalone='no'?>\n")
    elif standalone == 1:
        tree.xmlOutputBufferWrite(c_buffer, 21, "' standalone='yes'?>\n")
    else:
        tree.xmlOutputBufferWrite(c_buffer, 4, "'?>\n")

def _writeDtdToBuffer(c_buffer,
                      c_doc, c_root_name,
                      encoding):
    c_dtd = c_doc.intSubset
    if not c_dtd or not c_dtd.name:
        return
    if tree.ffi.string(c_root_name) != tree.ffi.string(c_dtd.name):
        return
    tree.xmlOutputBufferWrite(c_buffer, 10, "<!DOCTYPE ")
    tree.xmlOutputBufferWriteString(c_buffer, c_dtd.name)
    if c_dtd.SystemID and c_dtd.SystemID[0] != '\0':
        if c_dtd.ExternalID and c_dtd.ExternalID[0] != '\0':
            tree.xmlOutputBufferWrite(c_buffer, 9, ' PUBLIC "')
            tree.xmlOutputBufferWriteString(c_buffer, c_dtd.ExternalID)
            tree.xmlOutputBufferWrite(c_buffer, 3, '" "')
        else:
            tree.xmlOutputBufferWrite(c_buffer, 9, ' SYSTEM "')
        tree.xmlOutputBufferWriteString(c_buffer, c_dtd.SystemID)
        tree.xmlOutputBufferWrite(c_buffer, 1, '"')
    if (not c_dtd.entities and not c_dtd.elements and
        not c_dtd.attributes and not c_dtd.notations and
        not c_dtd.pentities):
        tree.xmlOutputBufferWrite(c_buffer, 2, '>\n')
        return
    tree.xmlOutputBufferWrite(c_buffer, 3, ' [\n')
    if c_dtd.notations:
        tree.xmlDumpNotationTable(c_buffer.buffer,
                                  c_dtd.notations)
    c_node = c_dtd.children
    while c_node:
        tree.xmlNodeDumpOutput(c_buffer, c_node.doc, c_node, 0, 0, encoding)
        c_node = c_node.next
    tree.xmlOutputBufferWrite(c_buffer, 3, "]>\n")

def _writeTail(c_buffer, c_node, encoding, c_method, pretty_print):
    u"Write the element tail."
    c_node = c_node.next
    while c_node and c_node.type == tree.XML_TEXT_NODE and not c_buffer.error:
        if c_method == OUTPUT_METHOD_HTML:
            tree.htmlNodeDumpFormatOutput(
                c_buffer, c_node.doc, c_node, encoding, pretty_print)
        else:
            tree.xmlNodeDumpOutput(
                c_buffer, c_node.doc, c_node, 0, pretty_print, encoding)
        c_node = c_node.next

def _writePrevSiblings(c_buffer, c_node,
                       encoding, pretty_print):
    if c_node.parent and _isElement(c_node.parent):
        return
    # we are at a root node, so add PI and comment siblings
    c_sibling = c_node
    while c_sibling.prev and \
            (c_sibling.prev.type == tree.XML_PI_NODE or
             c_sibling.prev.type == tree.XML_COMMENT_NODE):
        c_sibling = c_sibling.prev
    while c_sibling != c_node and not c_buffer.error:
        tree.xmlNodeDumpOutput(c_buffer, c_node.doc, c_sibling, 0,
                               pretty_print, encoding)
        if pretty_print:
            tree.xmlOutputBufferWriteString(c_buffer, "\n")
        c_sibling = c_sibling.next

def _writeNextSiblings(c_buffer, c_node,
                       encoding, pretty_print):
    if c_node.parent and _isElement(c_node.parent):
        return
    # we are at a root node, so add PI and comment siblings
    c_sibling = c_node.next
    while not c_buffer.error and c_sibling and \
            (c_sibling.type == tree.XML_PI_NODE or
             c_sibling.type == tree.XML_COMMENT_NODE):
        if pretty_print:
            tree.xmlOutputBufferWriteString(c_buffer, "\n")
        tree.xmlNodeDumpOutput(c_buffer, c_node.doc, c_sibling, 0,
                               pretty_print, encoding)
        c_sibling = c_sibling.next

############################################################
# output to file-like objects

class _FilelikeWriter(object):
    _close_filelike = None

    def __init__(self, filelike, exc_context=None, compression=None, close=False):
        if compression is not None and compression > 0:
            filelike = gzip.GzipFile(
                fileobj=filelike, mode='wb', compresslevel=compression)
            self._close_filelike = filelike.close
        elif close:
            self._close_filelike = filelike.close
        self._filelike = filelike
        if exc_context is None:
            self._exc_context = _ExceptionContext()
        else:
            self._exc_context = exc_context
        self.error_log = _ErrorLog()

    def _createOutputBuffer(self, enchandler):
        handle = tree.ffi.new_handle(self)
        self._handle = handle
        c_buffer = tree.xmlOutputBufferCreateIO(
            _writeFilelikeWriter,
            _closeFilelikeWriter,
            handle, enchandler)
        if not c_buffer:
            raise IOError, u"Could not create I/O writer context."
        return c_buffer

    def write(self, c_buffer, size):
        try:
            if self._filelike is None:
                raise IOError, u"File is already closed"
            py_buffer = tree.ffi.buffer(c_buffer, size)[:]
            self._filelike.write(py_buffer)
        except:
            size = -1
            self._exc_context._store_raised()
        finally:
            return size  # and swallow any further exceptions

    def close(self):
        retval = 0
        try:
            if self._close_filelike is not None:
                self._close_filelike()
            # we should not close the file here as we didn't open it
            self._filelike = None
        except:
            retval = -1
            self._exc_context._store_raised()
        finally:
            return retval  # and swallow any further exceptions

@tree.ffi.callback("xmlOutputWriteCallback")
def _writeFilelikeWriter(ctxt, c_buffer, length):
    return tree.ffi.from_handle(ctxt).write(c_buffer, length)

@tree.ffi.callback("xmlOutputCloseCallback")
def _closeFilelikeWriter(ctxt):
    return tree.ffi.from_handle(ctxt).close()

def _tofilelike(f, element, encoding, doctype, method,
                write_xml_declaration, write_doctype,
                pretty_print, with_tail, standalone,
                compression):
    writer = None

    c_method = _findOutputMethod(method)
    if c_method == OUTPUT_METHOD_TEXT:
        data = _textToString(element._c_node, encoding, with_tail)
        if compression:
            bytes_out = BytesIO()
            gzip_file = gzip.GzipFile(
                fileobj=bytes_out, mode='wb', compresslevel=compression)
            try:
                gzip_file.write(data)
            finally:
                gzip_file.close()
            data = bytes_out.getvalue()
        if _isString(f):
            filename8 = _encodeFilename(f)
            f = open(filename8, 'wb')
            try:
                f.write(data)
            finally:
                f.close()
        else:
            f.write(data)
        return

    if encoding is None:
        c_enc = tree.ffi.NULL
    else:
        encoding = _utf8(encoding)
        c_enc = encoding
    if doctype is None:
        c_doctype = tree.ffi.NULL
    else:
        doctype = _utf8(doctype)
        c_doctype = doctype

    writer, c_buffer = _create_output_buffer(f, c_enc, compression, close=False)

    _writeNodeToBuffer(c_buffer, element._c_node, c_enc, c_doctype, c_method,
                       write_xml_declaration, write_doctype,
                       pretty_print, with_tail, standalone)
    error_result = c_buffer.error
    if error_result == xmlerror.XML_ERR_OK:
        error_result = tree.xmlOutputBufferClose(c_buffer)
        if error_result > 0:
            error_result = xmlerror.XML_ERR_OK
    else:
        tree.xmlOutputBufferClose(c_buffer)
    if writer is not None:
        writer._exc_context._raise_if_stored()
    if error_result != xmlerror.XML_ERR_OK:
        _raiseSerialisationError(error_result)

def _create_output_buffer(f, c_enc, compression, close):
    enchandler = tree.xmlFindCharEncodingHandler(c_enc)
    if not enchandler:
        raise LookupError(u"unknown encoding: '%s'" %
                          c_enc.decode(u'UTF-8') if c_enc else u'')
    try:
        if _isString(f):
            filename8 = _encodeFilename(f)
            c_buffer = tree.xmlOutputBufferCreateFilename(
                filename8, enchandler, compression)
            if not c_buffer:
                return python.PyErr_SetFromErrno(IOError) # raises IOError
            writer = None
        elif hasattr(f, 'write'):
            writer = _FilelikeWriter(f, compression=compression, close=close)
            c_buffer = writer._createOutputBuffer(enchandler)
        else:
            raise TypeError(
                u"File or filename expected, got '%s'" %
                python._fqtypename(f).decode('UTF-8'))
    except:
        tree.xmlCharEncCloseFunc(enchandler)
        raise
    return writer, c_buffer

def _convert_ns_prefixes(c_dict, ns_prefixes):
    num_ns_prefixes = len(ns_prefixes)
    # Need to allocate one extra memory block to handle last NULL entry
    c_ns_prefixes = []
    for prefix in ns_prefixes:
         prefix_utf = _utf8(prefix)
         c_prefix = tree.xmlDictExists(c_dict, prefix_utf, len(prefix_utf))
         if c_prefix:
             # unknown prefixes do not need to get serialised
             c_ns_prefixes.append(c_prefix)

    c_ns_prefixes.append(tree.ffi.NULL)  # append end marker
    return c_ns_prefixes

def _tofilelikeC14N(f, element, exclusive, with_comments, compression,
                    inclusive_ns_prefixes):
    writer = None
    error = 0

    c_base_doc = element._c_node.doc
    c_doc = _fakeRootDoc(c_base_doc, element._c_node)
    try:
        c_inclusive_ns_prefixes = (
            _convert_ns_prefixes(c_doc.dict, inclusive_ns_prefixes)
            if inclusive_ns_prefixes else c14n.ffi.NULL)

        if _isString(f):
            filename8 = _encodeFilename(f)
            c_filename = filename8
            if 1:
                error = c14n.xmlC14NDocSave(
                    c_doc, tree.ffi.NULL, exclusive, c_inclusive_ns_prefixes,
                    with_comments, c_filename, compression)
        elif hasattr(f, 'write'):
            writer   = _FilelikeWriter(f, compression=compression)
            c_buffer = writer._createOutputBuffer(tree.ffi.NULL)
            with writer.error_log:
                bytes_count = c14n.xmlC14NDocSaveTo(
                    c_doc, c14n.ffi.NULL, exclusive, c_inclusive_ns_prefixes,
                    with_comments, c_buffer)
                error = tree.xmlOutputBufferClose(c_buffer)
            if bytes_count < 0:
                error = bytes_count
        else:
            raise TypeError(u"File or filename expected, got '%s'" %
                            python._fqtypename(f).decode('UTF-8'))
    finally:
        _destroyFakeDoc(c_base_doc, c_doc)

    if writer is not None:
        writer._exc_context._raise_if_stored()

    if error < 0:
        message = u"C14N failed"
        if writer is not None:
            errors = writer.error_log
            if len(errors):
                message = errors[0].message
        raise C14NError(message)

# incremental serialisation

class xmlfile(object):
    """xmlfile(self, output_file, encoding=None, compression=None, close=False, buffered=True)

    A simple mechanism for incremental XML serialisation.

    Usage example::

         with xmlfile("somefile.xml", encoding='utf-8') as xf:
             xf.write_declaration(standalone=True)
             xf.write_doctype('<!DOCTYPE root SYSTEM "some.dtd">')

             # generate an element (the root element)
             with xf.element('root'):
                  # write a complete Element into the open root element
                  xf.write(etree.Element('test'))

                  # generate and write more Elements, e.g. through iterparse
                  for element in generate_some_elements():
                      # serialise generated elements into the XML file
                      xf.write(element)

    If 'output_file' is a file(-like) object, passing ``close=True`` will
    close it when exiting the context manager.  By default, it is left
    to the owner to do that.  When a file path is used, lxml will take care
    of opening and closing the file itself.  Also, when a compression level
    is set, lxml will deliberately close the file to make sure all data gets
    compressed and written.

    Setting ``buffered=False`` will flush the output after each operation,
    such as opening or closing an ``xf.element()`` block or calling
    ``xf.write()``.  Alternatively, calling ``xf.flush()`` can be used to
    explicitly flush any pending output when buffering is enabled.
    """
    def __init__(self, output_file, encoding=None, compression=None,
                 close=False, buffered=True):
        self.output_file = output_file
        self.encoding = _utf8orNone(encoding)
        self.compresslevel = compression or 0
        self.close = close
        self.buffered = buffered
        self.method = OUTPUT_METHOD_XML

    def __enter__(self):
        assert self.output_file is not None
        self.writer = _IncrementalFileWriter(
            self.output_file, self.encoding, self.compresslevel,
            self.close, self.buffered, self.method)
        return self.writer

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.writer is not None:
            old_writer, self.writer = self.writer, None
            raise_on_error = exc_type is None
            old_writer._close(raise_on_error)
            if self.close:
                self.output_file = None


class htmlfile(xmlfile):
    """htmlfile(self, output_file, encoding=None, compression=None, close=False, buffered=True)

    A simple mechanism for incremental HTML serialisation.  Works the same as
    xmlfile.
    """
    def __init__(self, *args, **kwargs):
        super(htmlfile, self).__init__(*args, **kwargs)
        self.method = OUTPUT_METHOD_HTML


(WRITER_STARTING,
 WRITER_DECL_WRITTEN,
 WRITER_DTD_WRITTEN,
 WRITER_IN_ELEMENT,
 WRITER_FINISHED) = range(5)


class _IncrementalFileWriter(object):
    def __init__(self, outfile, encoding, compresslevel, close, buffered,
                 method):
        self._status = WRITER_STARTING
        self._element_stack = []
        if encoding is None:
            encoding = b'ASCII'
        self._encoding = encoding
        self._buffered = buffered
        self._target, self._c_out = _create_output_buffer(
            outfile, self._encoding, compresslevel, close)
        self._method = method

    def __del__(self):
        if self._c_out:
            tree.xmlOutputBufferClose(self._c_out)
            self._c_out = None

    def write_declaration(self, version=None, standalone=None, doctype=None):
        """write_declaration(self, version=None, standalone=None, doctype=None)

        Write an XML declaration and (optionally) a doctype into the file.
        """
        assert self._c_out
        if self._method != OUTPUT_METHOD_XML:
            raise LxmlSyntaxError("only XML documents have declarations")
        if self._status >= WRITER_DECL_WRITTEN:
            raise LxmlSyntaxError("XML declaration already written")
        version = _utf8orNone(version)
        c_version = version
        doctype = _utf8orNone(doctype)
        if standalone is None:
            c_standalone = -1
        else:
            c_standalone = 1 if standalone else 0
        _writeDeclarationToBuffer(self._c_out, c_version, self._c_encoding, c_standalone)
        if doctype is not None:
            _writeDoctype(self._c_out, doctype)
            self._status = WRITER_DTD_WRITTEN
        else:
            self._status = WRITER_DECL_WRITTEN
        if not self._buffered:
            tree.xmlOutputBufferFlush(self._c_out)
        self._handle_error(self._c_out.error)

    def write_doctype(self, doctype):
        """write_doctype(self, doctype)

        Writes the given doctype declaration verbatimly into the file.
        """
        assert self._c_out
        if doctype is None:
            return
        if self._status >= WRITER_DTD_WRITTEN:
            raise LxmlSyntaxError("DOCTYPE already written or cannot write it here")
        doctype = _utf8(doctype)
        _writeDoctype(self._c_out, doctype)
        self._status = WRITER_DTD_WRITTEN
        if not self._buffered:
            tree.xmlOutputBufferFlush(self._c_out)
        self._handle_error(self._c_out.error)

    def element(self, tag, attrib=None, nsmap=None, **_extra):
        """element(self, tag, attrib=None, nsmap=None, **_extra)

        Returns a context manager that writes an opening and closing tag.
        """
        from .etree import _Attrib
        assert self._c_out
        attributes = []
        if attrib is not None:
            if isinstance(attrib, (dict, _Attrib)):
                attrib = attrib.items()
            for name, value in attrib:
                if name not in _extra:
                    ns, name = _getNsTag(name)
                    attributes.append((ns, name, _utf8(value)))
        if _extra:
            for name, value in _extra.iteritems():
                ns, name = _getNsTag(name)
                attributes.append((ns, name, _utf8(value)))
        reversed_nsmap = {}
        if nsmap:
            for prefix, ns in nsmap.items():
                if prefix is not None:
                    prefix = _utf8(prefix)
                    _prefixValidOrRaise(prefix)
                reversed_nsmap[_utf8(ns)] = prefix
        ns, name = _getNsTag(tag)
        return _FileWriterElement(self, (ns, name, attributes, reversed_nsmap))

    def _write_qname(self, name, prefix):
        if prefix is not None:
            tree.xmlOutputBufferWrite(self._c_out, len(prefix), prefix)
            tree.xmlOutputBufferWrite(self._c_out, 1, ':')
        tree.xmlOutputBufferWrite(self._c_out, len(name), name)

    def _write_start_element(self, element_config):
        if self._status > WRITER_IN_ELEMENT:
            raise LxmlSyntaxError("cannot append trailing element to complete XML document")
        ns, name, attributes, nsmap = element_config
        flat_namespace_map, new_namespaces = self._collect_namespaces(nsmap)
        prefix = self._find_prefix(ns, flat_namespace_map, new_namespaces)
        tree.xmlOutputBufferWrite(self._c_out, 1, '<')
        self._write_qname(name, prefix)
        self._write_attributes_and_namespaces(
            attributes, flat_namespace_map, new_namespaces)
        tree.xmlOutputBufferWrite(self._c_out, 1, '>')
        if not self._buffered:
            tree.xmlOutputBufferFlush(self._c_out)
        self._handle_error(self._c_out.error)

        self._element_stack.append((ns, name, prefix, flat_namespace_map))
        self._status = WRITER_IN_ELEMENT

    def _write_attributes_and_namespaces(self, attributes,
                                          flat_namespace_map,
                                          new_namespaces):
        if attributes:
            # _find_prefix() may append to new_namespaces => build them first
            attributes = [
                (self._find_prefix(ns, flat_namespace_map, new_namespaces), name, value)
                for ns, name, value in attributes ]
        if new_namespaces:
            new_namespaces.sort()
            self._write_attributes_list(new_namespaces)
        if attributes:
            self._write_attributes_list(attributes)

    def _write_attributes_list(self, attributes):
        for prefix, name, value in attributes:
            tree.xmlOutputBufferWrite(self._c_out, 1, ' ')
            self._write_qname(name, prefix)
            tree.xmlOutputBufferWrite(self._c_out, 2, '="')
            tree.xmlOutputBufferWriteEscape(self._c_out, value, tree.ffi.NULL)
            tree.xmlOutputBufferWrite(self._c_out, 1, '"')

    def _write_end_element(self, element_config):
        if self._status != WRITER_IN_ELEMENT:
            raise LxmlSyntaxError("not in an element")
        if not self._element_stack or self._element_stack[-1][:2] != element_config[:2]:
            raise LxmlSyntaxError("inconsistent exit action in context manager")

        name, prefix = self._element_stack.pop()[1:3]
        tree.xmlOutputBufferWrite(self._c_out, 2, '</')
        self._write_qname(name, prefix)
        tree.xmlOutputBufferWrite(self._c_out, 1, '>')

        if not self._element_stack:
            self._status = WRITER_FINISHED
        if not self._buffered:
            tree.xmlOutputBufferFlush(self._c_out)
        self._handle_error(self._c_out.error)

    def _find_prefix(self, href, flat_namespaces_map, new_namespaces):
        if href is None:
            return None
        if href in flat_namespaces_map:
            return flat_namespaces_map[href]
        # need to create a new prefix
        prefixes = flat_namespaces_map.values()
        i = 0
        while True:
            prefix = _utf8('ns%d' % i)
            if prefix not in prefixes:
                new_namespaces.append((b'xmlns', prefix, href))
                flat_namespaces_map[href] = prefix
                return prefix
            i += 1

    def _collect_namespaces(self, nsmap):
        new_namespaces = []
        flat_namespaces_map = {}
        for ns, prefix in nsmap.iteritems():
            flat_namespaces_map[ns] = prefix
            if prefix is None:
                new_namespaces.append((None, b'xmlns', ns))
            else:
                new_namespaces.append((b'xmlns', prefix, ns))
        # merge in flat namespace map of parent
        if self._element_stack:
            for ns, prefix in self._element_stack[-1][-1].iteritems():
                if flat_namespaces_map.get(ns) is None:
                    # unknown or empty prefix => prefer a 'real' prefix
                    flat_namespaces_map[ns] = prefix
        return flat_namespaces_map, new_namespaces

    def write(self, *args, **kwargs):
        """write(self, *args, with_tail=True, pretty_print=False)

        Write subtrees or strings into the file.
        """
        from .etree import iselement
        with_tail = kwargs.pop('with_tail', True)
        pretty_print = kwargs.pop('pretty_print', False)
        assert not kwargs

        assert self._c_out
        for content in args:
            if _isString(content):
                if self._status != WRITER_IN_ELEMENT:
                    if self._status > WRITER_IN_ELEMENT or content.strip():
                        raise LxmlSyntaxError("not in an element")
                content = _utf8(content)
                tree.xmlOutputBufferWriteEscape(self._c_out, content, tree.ffi.NULL)
            elif iselement(content):
                if self._status > WRITER_IN_ELEMENT:
                    raise LxmlSyntaxError("cannot append trailing element to complete XML document")
                _writeNodeToBuffer(self._c_out, content._c_node,
                                   self._encoding, tree.ffi.NULL, self._method,
                                   False, False, pretty_print, with_tail, False)
                if content._c_node.type == tree.XML_ELEMENT_NODE:
                    if not self._element_stack:
                        self._status = WRITER_FINISHED
            else:
                raise TypeError("got invalid input value of type %s, expected string or Element" % type(content))
            self._handle_error(self._c_out.error)
        if not self._buffered:
            tree.xmlOutputBufferFlush(self._c_out)

    def flush(self):
        """flush(self)

        Write any pending content of the current output buffer to the stream.
        """
        assert self._c_out
        tree.xmlOutputBufferFlush(self._c_out)

    def _close(self, raise_on_error):
        if raise_on_error:
            if self._status < WRITER_IN_ELEMENT:
                raise LxmlSyntaxError("no content written")
            if self._element_stack:
                raise LxmlSyntaxError("pending open tags on close")
        error_result = self._c_out.error
        if error_result == xmlerror.XML_ERR_OK:
            error_result = tree.xmlOutputBufferClose(self._c_out)
            if error_result > 0:
                error_result = xmlerror.XML_ERR_OK
        else:
            tree.xmlOutputBufferClose(self._c_out)
        self._status = WRITER_FINISHED
        self._c_out = None
        del self._element_stack[:]
        if raise_on_error:
            self._handle_error(error_result)

    def _handle_error(self, error_result):
        if error_result != xmlerror.XML_ERR_OK:
            if self._target is not None:
                self._target._exc_context._raise_if_stored()
            _raiseSerialisationError(error_result)

class _FileWriterElement(object):
    def __init__(self, writer, element_config):
        self._writer = writer
        self._element = element_config

    def __enter__(self):
        self._writer._write_start_element(self._element)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._writer._write_end_element(self._element)
