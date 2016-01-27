from .cffi_base import ffi
from . import tree, dtdvalid, xmlerror, xmlparser, htmlparser, relaxng
from . import schematron, xinclude, xmlschema, xpath, xslt, uri, c14n

# The ffi has been initialized by cdefs at import-time.
# Here, we call verify() once on this single ffi.
# Then we hack horribly to replace the module names ".includes.tree",
# ".includes.xmlerror", etc. with the library obtained by verify()
# (always the same one).

libxml = ffi.verify("""
    #include "libxml/HTMLparser.h"
    #include "libxml/HTMLtree.h"
    #include "libxml/c14n.h"
    #include "libxml/chvalid.h"
    #include "libxml/parser.h"
    #include "libxml/parserInternals.h"
    #include "libxml/relaxng.h"
    #include "libxml/schematron.h"
    #include "libxml/tree.h"
    #include "libxml/uri.h"
    #include "libxml/valid.h"
    #include "libxml/xinclude.h"
    #include "libxml/xmlerror.h"
    #include "libxml/xmlschemas.h"
    #include "libxml/xmlversion.h"
    #include "libxml/xpath.h"
    #include "libxml/xpathInternals.h"
    #include "libxslt/xsltutils.h"
    #include "libxslt/security.h"
    #include "libxslt/transform.h"
    #include "libxslt/extensions.h"
    #include "libxslt/documents.h"
    #include "libxslt/variables.h"
    #include "libxslt/extra.h"
    #include "libexslt/exslt.h"

    xmlStructuredErrorFunc get_xmlStructuredError(void) {
        return xmlStructuredError;
    }
    void *get_xmlStructuredErrorContext(void) {
        return xmlStructuredErrorContext;
    }

    #ifndef XML_PARSE_BIG_LINES
    #  define XML_PARSE_BIG_LINES  4194304
    #endif
"""
+ xmlerror._XMLERROR_VAR_CALLBACKS,
    #
    include_dirs=['/usr/include/libxml2'],
    libraries=['xml2', 'xslt', 'exslt'],
    # XXX use /usr/bin/xslt-config
    library_dirs=['/usr/lib/x86_64-linux-gnu'])

libxml.ffi = ffi

libxml.LXML_VERSION_STRING = "3.4.0.0"  # XXX AFA read it from $ROOT/version.txt

# This overrides the modules!
tree = dtdvalid = xmlerror = xmlparser = htmlparser = relaxng = libxml
schematron = xinclude = xmlschema = xpath = xslt = uri = c14n = libxml
