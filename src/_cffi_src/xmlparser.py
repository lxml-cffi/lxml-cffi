DEFS = """
    #define XML_PARSE_RECOVER ...  // recover on errors
    #define XML_PARSE_NOENT ...  // substitute entities
    #define XML_PARSE_DTDLOAD ...  // load the external subset
    #define XML_PARSE_DTDATTR ...  // default DTD attributes
    #define XML_PARSE_DTDVALID ...  // validate with the DTD
    #define XML_PARSE_NOERROR ...  // suppress error reports
    #define XML_PARSE_NOWARNING ...  // suppress warning reports
    #define XML_PARSE_PEDANTIC ...  // pedantic error reporting
    #define XML_PARSE_NOBLANKS ...  // remove blank nodes
    #define XML_PARSE_SAX1 ...  // use the SAX1 interface internally
    #define XML_PARSE_XINCLUDE ...  // Implement XInclude substitition
    #define XML_PARSE_NONET ...  // Forbid network access
    #define XML_PARSE_NODICT ...  // Do not reuse the context dictionnary
    #define XML_PARSE_NSCLEAN ...  // remove redundant namespaces declarations
    #define XML_PARSE_NOCDATA ...  // merge CDATA as text nodes
    #define XML_PARSE_NOXINCNODE ...  // do not generate XINCLUDE START/END nodes
    // libxml2 2.6.21+ only:
    #define XML_PARSE_COMPACT ...  // compact small text nodes
    // libxml2 2.7.0+ only:
    #define XML_PARSE_OLD10 ...  // parse using XML-1.0 before update 5
    #define XML_PARSE_NOBASEFIX ...  // do not fixup XINCLUDE xml:base uris
    #define XML_PARSE_HUGE ...  // relax any hardcoded limit from the parser

    // libxml2 2.9.0+ only:
    #define XML_PARSE_BIG_LINES ... //store big lines numbers in text PSVI field

    // Init / Cleanup

    void            xmlInitParser               (void);
    void            xmlCleanupParser    (void);

    // Dict

    xmlDictPtr xmlDictCreate    (void);
    xmlDictPtr          xmlDictCreateSub(xmlDictPtr sub);
    void xmlDictFree(xmlDictPtr dict);
    int xmlDictReference(xmlDictPtr dict);

    #define XML_COMPLETE_ATTRS ...  // SAX option for adding DTD default attributes
    #define XML_SKIP_IDS ...        // SAX option for not building an XML ID dict

    // Parser Input

    typedef struct _xmlParserInput xmlParserInput;
    typedef xmlParserInput *xmlParserInputPtr;
    struct _xmlParserInput {
        const xmlChar *base;              /* Base of the array to parse */
        const xmlChar *cur;               /* Current char being parsed */
        const xmlChar *end;               /* end of the array to parse */
        int length;                       /* length if known */
        int line;                         /* Current line */
        ...;
    };

    void xmlSAX2StartDocument(void* ctxt);
    xmlParserInputBufferPtr xmlAllocParserInputBuffer           (xmlCharEncoding enc);

    // Parser Context

    typedef struct _xmlParserCtxt xmlParserCtxt;
    typedef xmlParserCtxt *xmlParserCtxtPtr;

    xmlParserCtxtPtr xmlNewParserCtxt();
    void        xmlFreeParserCtxt       (xmlParserCtxtPtr ctxt);
    void xmlClearParserCtxt(xmlParserCtxtPtr ctxt);
    int         xmlCtxtUseOptions       (xmlParserCtxtPtr ctxt,
                                         int options);
    int         xmlCtxtResetPush        (xmlParserCtxtPtr ctxt,
                                         const char *chunk,
                                         int size,
                                         const char *filename,
                                         const char *encoding);
    xmlDocPtr   xmlCtxtReadFile         (xmlParserCtxtPtr ctxt,
                                         const char *filename,
                                         const char *encoding,
                                         int options);
    xmlDocPtr xmlCtxtReadMemory(xmlParserCtxtPtr ctxt,
                                const char *buffer,
                                int size,
                                const char *URL,
                                const char *encoding,
                                int options);

    struct _xmlParserCtxt {
        struct _xmlSAXHandler *sax;       /* The SAX handler */
        void            *userData;        /* For SAX interface only, used by DOM build */
        xmlDocPtr           myDoc;        /* the document being built */
        int            wellFormed;        /* is the document well formed */
        int              recovery;
        int       replaceEntities;        /* shall we replace entities ? */
        int                  html;        /* an HTML(1)/Docbook(2) document
                                           * 3 is HTML after <head>
                                           * 10 is HTML after <body>
                                           */

        /* Input stream stack */
        xmlParserInputPtr  input;         /* Current input stream */

        /* Node analysis stack only used for DOM building */
        xmlNodePtr         node;          /* Current parsed Node */

        int errNo;                        /* error code */

        int              validate;        /* shall we try to validate ? */

        int             disableSAX;       /* SAX callbacks are disabled */
        int               inSubset;       /* Parsing is in int 1/ext 2 subset */

        int                spaceMax;      /* Max depth of the parsing stack */
        int *              spaceTab;      /* array of space infos */
        int                progressive;   /* is this a progressive parsing */
        xmlDictPtr         dict;          /* dictionnary for the parser */
        int                charset;       /* encoding of the in-memory content */
        void              *_private;      /* For user data, libxml won't touch it */
        int                loadsubset;    /* should the external subset be loaded */

        int                options;       /* Extra options */

        /* Those fields are needed only for treaming parsing so far */
        int               dictNames;    /* Use dictionary names for the tree */
        /* the complete error informations for the last error. */
        xmlError          lastError;
        ...;
    };

    typedef struct _xmlSAXHandler xmlSAXHandler;
    typedef xmlSAXHandler *xmlSAXHandlerPtr;

    xmlParserCtxtPtr xmlCreatePushParserCtxt(xmlSAXHandlerPtr sax,
                                         void *user_data,
                                         const char *chunk,
                                         int size,
                                         const char *filename);
    int         xmlParseChunk           (xmlParserCtxtPtr ctxt,
                                         const char *chunk,
                                         int size,
                                         int terminate);
    xmlDocPtr   xmlCtxtReadIO           (xmlParserCtxtPtr ctxt,
                                         xmlInputReadCallback ioread,
                                         xmlInputCloseCallback ioclose,
                                         void *ioctx,
                                         const char *URL,
                                         const char *encoding,
                                         int options);


    #define XML_SAX2_MAGIC ...

    typedef void (*internalSubsetSAXFunc) (void *ctx,
                                    const xmlChar *name,
                                    const xmlChar *ExternalID,
                                    const xmlChar *SystemID);
    typedef void (*startDocumentSAXFunc) (void *ctx);
    typedef void (*endDocumentSAXFunc) (void *ctx);
    typedef void (*startElementSAXFunc) (void *ctx,
                                    const xmlChar *name,
                                    const xmlChar **atts);
    typedef void (*endElementSAXFunc) (void *ctx,
                                    const xmlChar *name);
    typedef void (*referenceSAXFunc) (void *ctx,
                                    const xmlChar *name);
    typedef void (*charactersSAXFunc) (void *ctx,
                                    const xmlChar *ch,
                                    int len);
    typedef void (*processingInstructionSAXFunc) (void *ctx,
                                    const xmlChar *target,
                                    const xmlChar *data);
    typedef void (*commentSAXFunc) (void *ctx,
                                    const xmlChar *value);
    typedef void (*cdataBlockSAXFunc) (
                                    void *ctx,
                                    const xmlChar *value,
                                    int len);

    typedef void (*endElementNsSAX2Func)   (void *ctx,
                                            const xmlChar *localname,
                                            const xmlChar *prefix,
                                            const xmlChar *URI);
    typedef void (*startElementNsSAX2Func) (void *ctx,
                                            const xmlChar *localname,
                                            const xmlChar *prefix,
                                            const xmlChar *URI,
                                            int nb_namespaces,
                                            const xmlChar **namespaces,
                                            int nb_attributes,
                                            int nb_defaulted,
                                            const xmlChar **attributes);

    typedef struct _xmlSAXHandlerV1 xmlSAXHandlerV1;
    typedef xmlSAXHandlerV1 *xmlSAXHandlerV1Ptr;
    struct _xmlSAXHandlerV1 {
        ...;
    };

    struct _xmlSAXHandler {
        internalSubsetSAXFunc internalSubset;
        startDocumentSAXFunc startDocument;
        endDocumentSAXFunc endDocument;
        startElementSAXFunc startElement;
        endElementSAXFunc endElement;
        referenceSAXFunc reference;
        charactersSAXFunc characters;
        processingInstructionSAXFunc processingInstruction;
        commentSAXFunc comment;
        cdataBlockSAXFunc cdataBlock;
        unsigned int initialized;
        /* The following fields are extensions available only on version 2 */
        void *_private;
        startElementNsSAX2Func startElementNs;
        endElementNsSAX2Func endElementNs;
        xmlStructuredErrorFunc serror;
        ...;
    };

    typedef xmlParserInputPtr (*xmlExternalEntityLoader) (const char *URL,
                                             const char *ID,
                                             xmlParserCtxtPtr context);
    void        xmlSetExternalEntityLoader(xmlExternalEntityLoader f);
    xmlExternalEntityLoader xmlGetExternalEntityLoader(void);

    xmlParserInputPtr   xmlNewInputStream       (xmlParserCtxtPtr ctxt);
    xmlParserInputPtr xmlNewIOInputStream       (xmlParserCtxtPtr ctxt,
                                         xmlParserInputBufferPtr input,
                                         xmlCharEncoding enc);
    xmlParserInputPtr   xmlNewInputFromFile     (xmlParserCtxtPtr ctxt,
                                                 const char *filename);

    xmlDtdPtr   xmlParseDTD             (const xmlChar *ExternalID,
                                         const xmlChar *SystemID);
    xmlDtdPtr   xmlIOParseDTD           (xmlSAXHandlerPtr sax,
                                         xmlParserInputBufferPtr input,
                                         xmlCharEncoding enc);
"""
