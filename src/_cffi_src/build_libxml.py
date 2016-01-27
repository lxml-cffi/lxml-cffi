from __future__ import absolute_import
from cffi import FFI
from _cffi_src import (
    c14n, dtdvalid, htmlparser, relaxng, schematron, tree, uri, xinclude,
    xmlerror, xmlparser, xmlschema, xpath, xslt)

ffi = FFI()
ffi.cdef('\n'.join(getattr(m, 'DEFS') for m in [
    xmlerror, tree, xpath, c14n, dtdvalid, xmlparser, htmlparser, relaxng,
    schematron, uri, xinclude, xmlschema, xslt]))
ffi.set_source(
    "lxml._libxml2",
    """
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

#include <string.h>
#include <stdio.h>

void nullGenericErrorFunc(void* ctxt, char* msg, ...)
{
}
typedef void (*PyXsltErrorFunc)(void *ctxt, xmlError *error);
static PyXsltErrorFunc _pyXsltErrorFunc;
void setPyXsltErrorFunc(PyXsltErrorFunc func)
{
    _pyXsltErrorFunc = func;
}
void pyXsltGenericErrorFunc(void* ctxt, char* msg, ...)
{
    xmlError c_error;
    va_list args;
    char* c_text = NULL;
    char* c_message;
    char* c_element = NULL;
    char* c_pos;
    char* c_name_pos;
    char* c_str;
    int text_size, element_size, format_count, c_int;
    if (!msg || msg[0] == '\\n' || msg[0] == '\\0')
        return;

    c_error.file = NULL;
    c_error.line = 0;

    va_start(args, msg);
    // parse "NAME %s" chunks from the format string
    c_name_pos = c_pos = msg;
    format_count = 0;
    while (c_pos[0]) {
        if (c_pos[0] == '%') {
            c_pos += 1;
            if (c_pos[0] == 's') {  // "%s"
                format_count += 1;
                c_str = va_arg(args, char*);
                if (c_pos == msg + 1) {
                    c_text = c_str;  // msg == "%s..."
                }
                else if (c_name_pos[0] == 'e') {
                    if (strncmp(c_name_pos, "element %s", 10)) {
                        c_element = c_str;
                    }
                }
                else if (c_name_pos[0] == 'f') {
                    if (strncmp(c_name_pos, "file %s", 7)) {
                        if (strncmp("string://__STRING__XSLT", c_str, 23) == 0) {
                            c_str = "<xslt>";
                        }
                        c_error.file = c_str;
                    }
                }
            }
            else if (c_pos[0] == 'd') {  // "%d"
                format_count += 1;
                c_int = va_arg(args, int);
                if (strncmp(c_name_pos, "line %d", 7)) {
                    c_error.line = c_int;
                }
            }
            else if (c_pos[0] != '%') {  // "%%" == "%"
                format_count += 1;
                break;  // unexpected format or end of string => abort
            }
        }
        else if (c_pos[0] == ' ') {
            if (c_pos[1] != '%') {
                c_name_pos = c_pos + 1;
            }
        }
        c_pos += 1;
    }
    va_end(args);

    c_message = NULL;
    if (!c_text) {
        if (c_element && format_count == 1) {
            /* special case: a single occurrence of 'element %s' */
            text_size    = strlen(msg);
            element_size = strlen(c_element);
            c_message = malloc(
                (text_size + element_size + 1) * sizeof(char));
            sprintf(c_message, msg, c_element);
            c_error.message = c_message;
        }
        else
            c_error.message = "";
    }
    else if (!c_element) {
        c_error.message = c_text;
    }
    else {
        text_size    = strlen(c_text);
        element_size = strlen(c_element);
        c_message = malloc(
            (text_size + 12 + element_size + 1) * sizeof(char));
        sprintf(c_message, "%s, element '%s'", c_text, c_element);
        c_error.message = c_message;
    }

    c_error.domain = XML_FROM_XSLT;
    c_error.code   = XML_ERR_OK;  /* what else? */
    c_error.level  = XML_ERR_ERROR;  /* what else? */
    c_error.int2   = 0;

    _pyXsltErrorFunc(ctxt, &c_error);

    if (c_message)
        free(c_message);
}
""",
    include_dirs=['/usr/include/libxml2'],
    libraries=['xml2', 'xslt', 'exslt'],
    # XXX use /usr/bin/xslt-config
    library_dirs=['/usr/lib/x86_64-linux-gnu'])
