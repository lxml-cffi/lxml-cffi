from .saxparser import _SaxParserContext, _SaxParserTarget
from .saxparser import *
from . import python
from .parser import _raiseParseError
import sys
from ._libxml2 import ffi, lib as tree

class _TargetParserResult(Exception):
    # Admittedly, this is somewhat ugly, but it's the easiest way
    # to push the Python level parser result through the parser
    # machinery towards the API level functions
    def __init__(self, result):
        self.result = result

class _PythonSaxParserTarget(_SaxParserTarget):
    def __init__(self, target):
        _SaxParserTarget.__init__(self)
        event_filter = 0
        self._start_takes_nsmap = 0
        try:
            self._target_start = target.start
            if self._target_start is not None:
                event_filter |= SAX_EVENT_START
        except AttributeError:
            pass
        else:
            try:
                arguments = inspect_getargspec(self._target_start)
                if len(arguments[0]) > 3 or arguments[1] is not None:
                    self._start_takes_nsmap = 1
            except TypeError:
                pass
        try:
            self._target_end = target.end
            if self._target_end is not None:
                event_filter |= SAX_EVENT_END
        except AttributeError:
            pass
        try:
            self._target_data = target.data
            if self._target_data is not None:
                event_filter |= SAX_EVENT_DATA
        except AttributeError:
            pass
        try:
            self._target_doctype = target.doctype
            if self._target_doctype is not None:
                event_filter |= SAX_EVENT_DOCTYPE
        except AttributeError:
            pass
        try:
            self._target_pi = target.pi
            if self._target_pi is not None:
                event_filter |= SAX_EVENT_PI
        except AttributeError:
            pass
        try:
            self._target_comment = target.comment
            if self._target_comment is not None:
                event_filter |= SAX_EVENT_COMMENT
        except AttributeError:
            pass
        self._sax_event_filter = event_filter

    def _handleSaxStart(self, tag, attrib, nsmap):
        if self._start_takes_nsmap:
            return self._target_start(tag, attrib, nsmap)
        else:
            return self._target_start(tag, attrib)

    def _handleSaxEnd(self, tag):
        return self._target_end(tag)

    def _handleSaxData(self, data):
        self._target_data(data)

    def _handleSaxDoctype(self, root_tag, public_id, system_id):
        self._target_doctype(root_tag, public_id, system_id)

    def _handleSaxPi(self, target, data):
        return self._target_pi(target, data)

    def _handleSaxComment(self, comment):
        return self._target_comment(comment)



class _TargetParserContext(_SaxParserContext):
    u"""This class maps SAX2 events to the ET parser target interface.
    """
    def _setTarget(self, target):
        self._python_target = target
        if not isinstance(target, _SaxParserTarget) or \
                hasattr(target, u'__dict__'):
            target = _PythonSaxParserTarget(target)
        self._setSaxParserTarget(target)
        return 0

    def _cleanupTargetParserContext(self, result):
        if self._c_ctxt.myDoc:
            if self._c_ctxt.myDoc != result and \
                    not self._c_ctxt.myDoc._private:
                # no _Document proxy => orphen
                tree.xmlFreeDoc(self._c_ctxt.myDoc)
            self._c_ctxt.myDoc = ffi.NULL

    def _handleParseResult(self, parser, result, filename):
        recover = parser._parse_options & xmlparser.XML_PARSE_RECOVER
        try:
            if self._has_raised():
                self._cleanupTargetParserContext(result)
                self._raise_if_stored()
            if not self._c_ctxt.wellFormed and not recover:
                _raiseParseError(self._c_ctxt, filename, self._error_log)
        except:
            if python.IS_PYTHON3:
                self._python_target.close()
                raise
            else:
                exc = sys.exc_info()
                # Python 2 can't chain exceptions
                try: self._python_target.close()
                except: pass
                raise exc[0], exc[1], exc[2]
        return self._python_target.close()

    def _handleParseResultDoc(self, parser, result, filename):
        recover = parser._parse_options & xmlparser.XML_PARSE_RECOVER
        if result and not result._private:
            # no _Document proxy => orphen
            tree.xmlFreeDoc(result)
        try:
            self._cleanupTargetParserContext(result)
            self._raise_if_stored()
            if not self._c_ctxt.wellFormed and not recover:
                _raiseParseError(self._c_ctxt, filename, self._error_log)
        except:
            if python.IS_PYTHON3:
                self._python_target.close()
                raise
            else:
                exc = sys.exc_info()
                # Python 2 can't chain exceptions
                try: self._python_target.close()
                except: pass
                raise exc[0], exc[1], exc[2]
        parse_result = self._python_target.close()
        raise _TargetParserResult(parse_result)
