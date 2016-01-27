DEFS = """
    typedef struct _xmlRelaxNG xmlRelaxNG;
    typedef xmlRelaxNG *xmlRelaxNGPtr;

    typedef struct _xmlRelaxNGParserCtxt xmlRelaxNGParserCtxt;
    typedef xmlRelaxNGParserCtxt *xmlRelaxNGParserCtxtPtr;

    typedef struct _xmlRelaxNGValidCtxt xmlRelaxNGValidCtxt;
    typedef xmlRelaxNGValidCtxt *xmlRelaxNGValidCtxtPtr;

    xmlRelaxNGParserCtxtPtr xmlRelaxNGNewDocParserCtxt  (xmlDocPtr doc);
    void            xmlRelaxNGFreeParserCtxt    (xmlRelaxNGParserCtxtPtr ctxt);
    void            xmlRelaxNGSetParserStructuredErrors(
                                         xmlRelaxNGParserCtxtPtr ctxt,
                                         xmlStructuredErrorFunc serror,
                                         void *ctx);

    xmlRelaxNGPtr   xmlRelaxNGParse             (xmlRelaxNGParserCtxtPtr ctxt);
    void            xmlRelaxNGFree              (xmlRelaxNGPtr schema);

    xmlRelaxNGValidCtxtPtr xmlRelaxNGNewValidCtxt       (xmlRelaxNGPtr schema);
    void                xmlRelaxNGSetValidStructuredErrors(xmlRelaxNGValidCtxtPtr ctxt,
                                          xmlStructuredErrorFunc serror, void *ctx);
    int             xmlRelaxNGValidateDoc       (xmlRelaxNGValidCtxtPtr ctxt,
                                                 xmlDocPtr doc);
    void            xmlRelaxNGFreeValidCtxt     (xmlRelaxNGValidCtxtPtr ctxt);

"""
