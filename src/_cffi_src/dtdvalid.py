DEFS = """
    typedef struct _xmlValidCtxt xmlValidCtxt;
    typedef xmlValidCtxt *xmlValidCtxtPtr;
    typedef void (*xmlValidityErrorFunc)(void * ctx, const char * msg, ...);
    typedef void (*xmlValidityWarningFunc)(void * ctx, const char * msg, ...);

    struct _xmlValidCtxt {
        void *userData;
        xmlValidityErrorFunc error;
        xmlValidityWarningFunc warning;
        ...;
    };

    xmlValidCtxtPtr xmlNewValidCtxt(void);
    void xmlFreeValidCtxt(xmlValidCtxtPtr);
    int         xmlValidateDtd          (xmlValidCtxtPtr ctxt,
                                         xmlDocPtr doc,
                                         xmlDtdPtr dtd);
    xmlElementPtr       xmlGetDtdElementDesc    (xmlDtdPtr dtd,
                                         const xmlChar * name);
"""
