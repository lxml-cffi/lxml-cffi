DEFS = """
    typedef struct _xmlURI xmlURI;
    typedef xmlURI *xmlURIPtr;
    xmlURIPtr   xmlParseURI             (const char *str);
    void        xmlFreeURI              (xmlURIPtr uri);
"""
