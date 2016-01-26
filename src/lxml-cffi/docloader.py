from .etree import _ExceptionContext
from . import python
from .apihelpers import _getFilenameForFile, _encodeFilename

(PARSER_DATA_INVALID,
 PARSER_DATA_EMPTY,
 PARSER_DATA_STRING,
 PARSER_DATA_FILENAME,
 PARSER_DATA_FILE,
 ) = range(5)

class _InputDocument(object):
    _type = PARSER_DATA_INVALID
    _filename = None

class Resolver(object):
    u"This is the base class of all resolvers."

    def resolve_empty(self, context):
        u"""resolve_empty(self, context)

        Return an empty input document.

        Pass context as parameter.
        """
        doc_ref = _InputDocument()
        doc_ref._type = PARSER_DATA_EMPTY
        return doc_ref

    def resolve_string(self, string, context, base_url=None):
        u"""resolve_string(self, string, context, base_url=None)

        Return a parsable string as input document.

        Pass data string and context as parameters.  You can pass the
        source URL or filename through the ``base_url`` keyword
        argument.
        """
        if isinstance(string, unicode):
            string = string.encode('utf8')
        elif not isinstance(string, bytes):
            raise TypeError, "argument must be a byte string or unicode string"
        doc_ref = _InputDocument()
        doc_ref._type = PARSER_DATA_STRING
        doc_ref._data_bytes = string
        if base_url is not None:
            doc_ref._filename = _encodeFilename(base_url)
        return doc_ref

    def resolve_filename(self, filename, context):
        u"""resolve_filename(self, filename, context)

        Return the name of a parsable file as input document.

        Pass filename and context as parameters.  You can also pass a
        URL with an HTTP, FTP or file target.
        """
        doc_ref = _InputDocument()
        doc_ref._type = PARSER_DATA_FILENAME
        doc_ref._filename = _encodeFilename(filename)
        return doc_ref

    def resolve_file(self, f, context, base_url=None, close=True):
        u"""resolve_file(self, f, context, base_url=None, close=True)

        Return an open file-like object as input document.

        Pass open file and context as parameters.  You can pass the
        base URL or filename of the file through the ``base_url``
        keyword argument.  If the ``close`` flag is True (the
        default), the file will be closed after reading.

        Note that using ``.resolve_filename()`` is more efficient,
        especially in threaded environments.
        """
        try:
            f.read
        except AttributeError:
            raise TypeError, u"Argument is not a file-like object"
        doc_ref = _InputDocument()
        doc_ref._type = PARSER_DATA_FILE
        if base_url is not None:
            doc_ref._filename = _encodeFilename(base_url)
        else:
            doc_ref._filename = _getFilenameForFile(f)
        doc_ref._close_file = close
        doc_ref._file = f
        return doc_ref

class _ResolverRegistry(object):
    def __init__(self, default_resolver=None):
        self._resolvers = set()
        self._default_resolver = default_resolver

    def add(self, resolver):
        u"""add(self, resolver)

        Register a resolver.

        For each requested entity, the 'resolve' method of the resolver will
        be called and the result will be passed to the parser.  If this method
        returns None, the request will be delegated to other resolvers or the
        default resolver.  The resolvers will be tested in an arbitrary order
        until the first match is found.
        """
        self._resolvers.add(resolver)

    def remove(self, resolver):
        u"remove(self, resolver)"
        self._resolvers.discard(resolver)

    def _copy(self):
        registry = _ResolverRegistry(self._default_resolver)
        registry._resolvers = self._resolvers.copy()
        return registry

    def copy(self):
        u"copy(self)"
        return self._copy()

    def resolve(self, system_url, public_id, context):
        u"resolve(self, system_url, public_id, context)"
        for resolver in self._resolvers:
            result = resolver.resolve(system_url, public_id, context)
            if result is not None:
                return result
        if self._default_resolver is None:
            return None
        return self._default_resolver.resolve(system_url, public_id, context)

    def __repr__(self):
        return repr(self._resolvers)

class _ResolverContext(_ExceptionContext):
    def clear(self):
        _ExceptionContext.clear(self)

def _initResolverContext(context, resolvers):
    if resolvers is None:
        context._resolvers = _ResolverRegistry()
    else:
        context._resolvers = resolvers
