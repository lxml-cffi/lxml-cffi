import sys

PY_VERSION_HEX = sys.hexversion
IS_PYTHON3 = sys.version >= '3'
LXML_UNICODE_STRINGS = IS_PYTHON3

def _isString(obj):
    return isinstance(obj, basestring)

def _fqtypename(obj):
    return type(obj).__name__

def PyUnicode_AsUTF8String(obj):
    return obj.encode('utf8')
def PyUnicode_DecodeUTF8(obj):
    return obj.decode('utf8')
def PyUnicode_AsASCIIString(obj):
    return obj.encode('ascii')

def PyBytes_GET_SIZE(obj):
    return len(obj)
def PyBytes_FromFormat(fmt, *args):
    return fmt % args

def PySequence_Check(obj):
    return isinstance(obj, (list, tuple))
def PyDict_GetItem(obj, item):
    return obj[item]

def PyNumber_Check(obj):
    return isinstance(obj, (int, long, float))
def PyType_Check(obj):
    return isinstance(obj, type)

def PyErr_SetFromErrno(exc):
    from ._libxml2 import ffi
    raise exc(ffi.errno, "Error")

