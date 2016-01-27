import threading
import re

from .etree import __MAX_LOG_SIZE
from .apihelpers import _decodeFilename, _isFilePath
from ._libxml2 import ffi, lib
xmlerror = tree = helpers = xslt = lib

# module level API functions

def clear_error_log():
    u"""clear_error_log()

    Clear the global error log.  Note that this log is already bound to a
    fixed size.

    Note: since lxml 2.2, the global error log is local to a thread
    and this function will only clear the global error log of the
    current thread.
    """
    _getGlobalErrorLog().clear()


pyXsltGenericErrorFunc = helpers.pyXsltGenericErrorFunc

# setup for global log:

def _initThreadLogging():
    # disable generic error lines from libxml2
    xmlerror.xmlSetGenericErrorFunc(
        ffi.NULL, helpers.nullGenericErrorFunc)

    # divert error messages to the global error log
    connectErrorLog(None)

def connectErrorLog(log):
    helpers.setPyXsltErrorFunc(_receiveError)
    if log is None:
        handle = ffi.NULL
    else:
        handle = log.get_handle()
    xslt.xsltSetGenericErrorFunc(handle, pyXsltGenericErrorFunc)

# Logging classes

class _LogEntry(object):
    """A log message entry from an error log.

    Attributes:

    - message: the message text
    - domain: the domain ID (see lxml.etree.ErrorDomains)
    - type: the message type ID (see lxml.etree.ErrorTypes)
    - level: the log level ID (see lxml.etree.ErrorLevels)
    - line: the line at which the message originated (if applicable)
    - column: the character column at which the message originated (if applicable)
    - filename: the name of the file in which the message originated (if applicable)
    """

    def __del__(self):
        tree.xmlFree(self._c_message)
        tree.xmlFree(self._c_filename)

    def _setError(self, error):
        self.domain   = error.domain
        self.type     = error.code
        self.level    = error.level
        self.line     = error.line
        self.column   = error.int2
        self._c_message = ffi.NULL
        self._c_filename = ffi.NULL
        if not error.message or error.message[0] in b'\n\0':
            self._message = u"unknown error"
        else:
            self._message = None
            self._c_message = tree.xmlStrdup(error.message)
            if not self._c_message:
                raise MemoryError
        if not error.file:
            self._filename = u'<string>'
        else:
            self._filename = None
            self._c_filename = tree.xmlStrdup(error.file)
            if not self._c_filename:
                raise MemoryError

    def _setGeneric(self, domain, type, level, line, message, filename):
        self.domain  = domain
        self.type    = type
        self.level   = level
        self.line    = line
        self.column  = 0
        self._message = message
        self._filename = filename
        self._c_message = ffi.NULL
        self._c_filename = ffi.NULL

    def __repr__(self):
        return u"%s:%d:%d:%s:%s:%s: %s" % (
            self.filename, self.line, self.column, self.level_name,
            self.domain_name, self.type_name, self.message)

    @property
    def domain_name(self):
        """The name of the error domain.  See lxml.etree.ErrorDomains
        """
        return ErrorDomains._getName(self.domain, u"unknown")

    @property
    def type_name(self):
        """The name of the error type.  See lxml.etree.ErrorTypes
        """
        if self.domain == ErrorDomains.RELAXNGV:
            getName = RelaxNGErrorTypes._getName
        else:
            getName = ErrorTypes._getName
        return getName(self.type, u"unknown")

    @property
    def level_name(self):
        """The name of the error level.  See lxml.etree.ErrorLevels
        """
        return ErrorLevels._getName(self.level, u"unknown")

    @property
    def message(self):
        if self._message is not None:
            return self._message
        if not self._c_message:
            return None
        message = ffi.string(self._c_message)
        message = message.rstrip('\n')
        # cannot use funicode() here because the message may contain
        # byte encoded file paths etc.
        try:
            self._message = message.decode('utf8')
        except UnicodeDecodeError:
            try:
                self._message = message.decode(
                    'ascii', 'backslashreplace')
            except UnicodeDecodeError:
                self._message = u'<undecodable error message>'
            except TypeError:
                raise TypeError("AFA", message)
        if self._c_message:
            # clean up early
            tree.xmlFree(self._c_message)
            self._c_message = ffi.NULL
        return self._message

    @property
    def filename(self):
        if self._filename is None:
            if self._c_filename:
                self._filename = _decodeFilename(self._c_filename)
                # clean up early
                tree.xmlFree(self._c_filename)
                self._c_filename = ffi.NULL
        return self._filename        


class _BaseErrorLog(object):
    _handle = None

    def __init__(self, first_error, last_error):
        self._first_error = first_error
        self.last_error = last_error

    def get_handle(self):
        if self._handle is None:
            self._handle = ffi.new_handle(self)
        return self._handle

    def receive(self, entry):
        pass

    def _receive(self, error):
        entry = _LogEntry.__new__(_LogEntry)
        entry._setError(error)
        is_error = (error.level in (xmlerror.XML_ERR_ERROR, xmlerror.XML_ERR_FATAL))
        global_log = _getGlobalErrorLog()
        if global_log is not self:
            global_log.receive(entry)
            if is_error:
                global_log.last_error = entry
        self.receive(entry)
        if is_error:
            self.last_error = entry

    def _receiveGeneric(self, domain, type, level, line, message, filename):
        entry = _LogEntry.__new__(_LogEntry)
        entry._setGeneric(domain, type, level, line, message, filename)
        is_error = level == xmlerror.XML_ERR_ERROR or \
                   level == xmlerror.XML_ERR_FATAL
        global_log = _getGlobalErrorLog()
        if global_log is not self:
            global_log.receive(entry)
            if is_error:
                global_log.last_error = entry
        self.receive(entry)
        if is_error:
            self.last_error = entry

    def _buildParseException(self, exctype, default_message):
        code = xmlerror.XML_ERR_INTERNAL_ERROR
        if self._first_error is None:
            return exctype(default_message, code, 0, 0)
        message = self._first_error.message
        if message:
            code = self._first_error.type
        else:
            message = default_message
        line = self._first_error.line
        column = self._first_error.column
        if line > 0:
            if column > 0:
                message = u"%s, line %d, column %d" % (message, line, column)
            else:
                message = u"%s, line %d" % (message, line)
        return exctype(message, code, line, column)

    def _buildExceptionMessage(self, default_message):
        if self._first_error is None:
            return default_message
        if self._first_error.message:
            message = self._first_error.message
        elif default_message is None:
            return None
        else:
            message = default_message
        if self._first_error.line > 0:
            if self._first_error.column > 0:
                message = u"%s, line %d, column %d" % (
                    message, self._first_error.line, self._first_error.column)
            else:
                message = u"%s, line %d" % (message, self._first_error.line)
        return message

class _ListErrorLog(_BaseErrorLog):
    u"Immutable base version of a list based error log."

    _offset = 0

    def __init__(self, entries, first_error, last_error):
        if entries:
            if first_error is None:
                first_error = entries[0]
            if last_error is None:
                last_error = entries[-1]
        _BaseErrorLog.__init__(self, first_error, last_error)
        self._entries = entries

    def copy(self):
        u"""Creates a shallow copy of this error log.  Reuses the list of
        entries.
        """
        log = _ListErrorLog(
            self._entries, self._first_error, self.last_error)
        log._offset = self._offset
        return log

    def __iter__(self):
        entries = self._entries
        if self._offset:
            entries = islice(entries, self._offset)
        return iter(entries)

    def __repr__(self):
        return u'\n'.join(repr(entry) for entry in self)

    def __getitem__(self, index):
        return self._entries[self._offset + index]

    def __len__(self):
        return len(self._entries) - self._offset

    def __contains__(self, error_type):
        for i, entry in enumerate(self._entries):
            if i < self._offset:
                continue
            if entry.type == error_type:
                return True
        return False

    def __nonzero__(self):
        return len(self._entries) > self._offset

    def filter_types(self, types):
        u"""filter_types(self, types)

        Filter the errors by the given types and return a new error
        log containing the matches.
        """
        if isinstance(types, (int, long)):
            types = (types,)
        filtered = [entry for entry in self if entry.type in types]
        return _ListErrorLog(filtered, None, None)

    def filter_from_level(self, level):
        u"""filter_from_level(self, level)

        Return a log with all messages of the requested level of worse.
        """
        filtered = [entry for entry in self if entry.level >= level]
        return _ListErrorLog(filtered, None, None)

    def filter_from_fatals(self):
        u"""filter_from_fatals(self)

        Convenience method to get all fatal error messages.
        """
        return self.filter_from_level(ErrorLevels.FATAL)

    def filter_from_errors(self):
        u"""filter_from_errors(self)

        Convenience method to get all error messages or worse.
        """
        return self.filter_from_level(ErrorLevels.ERROR)

    def filter_from_warnings(self):
        u"""filter_from_warnings(self)

        Convenience method to get all warnings or worse.
        """
        return self.filter_from_level(ErrorLevels.WARNING)

class _ErrorLogContext(object):
    """
    Error log context for the 'with' statement.
    Stores a reference to the current callbacks to allow for
    recursively stacked log contexts.
    """

class _ErrorLog(_ListErrorLog):
    def __init__(self):
        self._logContexts = []
        _ListErrorLog.__init__(self, [], None, None)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        self._first_error = None
        del self._entries[:]
        connectErrorLog(self)

        context = _ErrorLogContext.__new__(_ErrorLogContext)
        context.old_error_func = xmlerror.get_xmlStructuredError()
        context.old_error_context = xmlerror.get_xmlStructuredErrorContext()
        self._logContexts.append(context)
        xmlerror.xmlSetStructuredErrorFunc(self.get_handle(), _receiveError)

    def disconnect(self):
        context = self._logContexts.pop()
        xmlerror.xmlSetStructuredErrorFunc(
            context.old_error_context, context.old_error_func)

    def clear(self):
        self._first_error = None
        self.last_error = None
        self._offset = 0
        del self._entries[:]

    def copy(self):
        u"""Creates a shallow copy of this error log and the list of entries.
        """
        return _ListErrorLog(
            self._entries[self._offset:],
            self._first_error, self.last_error)

    def __iter__(self):
        return iter(self._entries[self._offset:])

    def receive(self, entry):
        if self._first_error is None and entry.level >= xmlerror.XML_ERR_ERROR:
            self._first_error = entry
        self._entries.append(entry)

class _RotatingErrorLog(_ErrorLog):
    def __init__(self, max_len):
        _ErrorLog.__init__(self)
        self._max_len = max_len

    def receive(self, entry):
        if self._first_error is None and entry.level >= xmlerror.XML_ERR_ERROR:
            self._first_error = entry
        self._entries.append(entry)

        if len(self._entries) > self._max_len:
            self._offset += 1
            if self._offset > self._max_len // 3:
                offset = self._offset
                self._offset = 0
                del self._entries[:offset]


# thread-local, global list log to collect error output messages from
# libxml2/libxslt

__ERROR_LOG = threading.local()

def _getGlobalErrorLog():
    u"""Retrieve the global error log of this thread."""
    try:
        return __ERROR_LOG.log
    except AttributeError:
        log = _RotatingErrorLog(__MAX_LOG_SIZE)
        __ERROR_LOG.log = log
        return log

def _copyGlobalErrorLog():
    u"Helper function for properties in exceptions."
    return _getGlobalErrorLog().copy()

# local log functions: forward error to logger object
def _forwardError(c_log_handler, error):
    log_handler = ffi.from_handle(c_log_handler)
    log_handler._receive(error)

@ffi.callback("xmlStructuredErrorFunc")
def _receiveError(c_log_handler, error):
    # no Python objects here, may be called without thread context !
    _forwardError(c_log_handler, error)

################################################################################
## CONSTANTS FROM "xmlerror.h" (or rather libxml-xmlerror.html)
################################################################################

class MetaErrorEnum(type):
    def __new__(meta, name, bases, dict):
        cls = type.__new__(meta, name, bases, dict)
        if not hasattr(cls, 'elements'):
            return cls
        for value, name in cls.elements.items():
            setattr(cls, name, value)

        return cls

class BaseErrorEnum(object):
    __metaclass__ = MetaErrorEnum
    @classmethod
    def _getName(cls, value, default=None):
        return cls.elements.get(value, default)

class ErrorLevels(BaseErrorEnum):
    u"Libxml2 error levels"
    elements = dict(
        (value, name[8:])  # Strip "XML_ERR_" prefix
        for (value, name) in ffi.typeof("xmlErrorLevel").elements.items())

class ErrorDomains(BaseErrorEnum):
    u"Libxml2 error domains"
    elements = dict(
        (value, name[9:])  # Strip "XML_FROM_" prefix
        for (value, name) in ffi.typeof("xmlErrorDomain").elements.items())

class ErrorTypes(BaseErrorEnum):
    u"Libxml2 error types"
    elements = dict(
        (value, name[4:])  # Strip "XML_" prefix
        for (value, name) in ffi.typeof("xmlParserErrors").elements.items())

class RelaxNGErrorTypes(BaseErrorEnum):
    u"Libxml2 RelaxNG error types"
    elements = dict(
        (value, name[4:])  # Strip "XML_" prefix
        for (value, name) in ffi.typeof("xmlRelaxNGValidErr").elements.items())

