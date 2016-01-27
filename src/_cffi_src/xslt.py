DEFS = """
    const int xsltLibxsltVersion;

    void xsltSetGenericErrorFunc(void *ctx,
                                 xmlGenericErrorFunc handler);

    typedef struct _xsltStylesheet xsltStylesheet;
    typedef xsltStylesheet *xsltStylesheetPtr;

    struct _xsltStylesheet {
        xmlDocPtr doc;          /* the parsed XML stylesheet */
        int errors;                     /* number of errors found at compilation */
        xmlChar *encoding;              /* encoding string */
        ...;
    };

    xsltStylesheetPtr   xsltParseStylesheetDoc  (xmlDocPtr doc);
    void                xsltFreeStylesheet      (xsltStylesheetPtr style);

    typedef enum {
        XSLT_SECPREF_READ_FILE = 1,
        XSLT_SECPREF_WRITE_FILE,
        XSLT_SECPREF_CREATE_DIRECTORY,
        XSLT_SECPREF_READ_NETWORK,
        XSLT_SECPREF_WRITE_NETWORK
    } xsltSecurityOption;


    typedef struct _xsltTransformContext xsltTransformContext;
    typedef xsltTransformContext *xsltTransformContextPtr;

    typedef enum {
        XSLT_STATE_OK = 0,
        XSLT_STATE_ERROR,
        XSLT_STATE_STOPPED
    } xsltTransformState;

    struct _xsltTransformContext {
        /* dictionary: shared between stylesheet, context and documents. */
        xmlDictPtr dict;
        xmlXPathContextPtr xpathCtxt;   /* the XPath context */
        xsltTransformState state;               /* the current state */
        xmlNodePtr inst;                        /* the instruction in the stylesheet */
        int profile;                        /* is this run profiled */

        xmlNodePtr node;                        /* the current node being processed */

        xmlDocPtr output;                       /* the resulting document */
        xmlNodePtr insert;                      /* the insertion node */
        void            *_private;              /* user defined data */
        ...;
    };

    typedef struct _xsltElemPreComp xsltElemPreComp;
    typedef xsltElemPreComp *xsltElemPreCompPtr;
    typedef struct _xsltTemplate xsltTemplate;
    typedef xsltTemplate *xsltTemplatePtr;
    typedef struct _xsltStackElem xsltStackElem;
    typedef xsltStackElem *xsltStackElemPtr;

    typedef void (*xsltTransformFunction) (xsltTransformContextPtr ctxt,
                                       xmlNodePtr node,
                                       xmlNodePtr inst,
                                       xsltElemPreCompPtr comp);

    xsltTransformContextPtr xsltNewTransformContext(xsltStylesheetPtr style,
                                         xmlDocPtr doc);
    void        xsltFreeTransformContext(xsltTransformContextPtr ctxt);

    int         xsltSetCtxtParseOptions         (xsltTransformContextPtr ctxt,
                                                 int options);
    void        xsltSetTransformErrorFunc       (xsltTransformContextPtr ctxt,
                                                 void *ctx,
                                                 xmlGenericErrorFunc handler);
    int         xsltRegisterExtFunction (xsltTransformContextPtr ctxt,
                                         const xmlChar *name,
                                         const xmlChar *URI,
                                         xmlXPathFunction function);
    int         xsltRegisterExtElement  (xsltTransformContextPtr ctxt,
                                         const xmlChar *name,
                                         const xmlChar *URI,
                                         xsltTransformFunction function);

    int         xsltQuoteOneUserParam           (xsltTransformContextPtr ctxt,
                                                 const xmlChar * name,
                                                 const xmlChar * value);
    void        xsltTransformError              (xsltTransformContextPtr ctxt,
                                                 xsltStylesheetPtr style,
                                                 xmlNodePtr node,
                                                 const char *msg,
                                                 ...);

    xmlDocPtr   xsltApplyStylesheetUser (xsltStylesheetPtr style,
                                         xmlDocPtr doc,
                                         const char **params,
                                         const char *output,
                                         FILE * profile,
                                         xsltTransformContextPtr userCtxt);
    void        xsltProcessOneNode      (xsltTransformContextPtr ctxt,
                                         xmlNodePtr node,
                                         xsltStackElemPtr params);
    void        xsltApplyOneTemplate    (xsltTransformContextPtr ctxt,
                                         xmlNodePtr node,
                                         xmlNodePtr list,
                                         xsltTemplatePtr templ,
                                         xsltStackElemPtr params);

    int         xsltSaveResultToString          (xmlChar **doc_txt_ptr,
                                                 int * doc_txt_len,
                                                 xmlDocPtr result,
                                                 xsltStylesheetPtr style);


    /* Hooks for document loading */
    typedef enum {
        XSLT_LOAD_START = 0,    /* loading for a top stylesheet */
        XSLT_LOAD_STYLESHEET = 1,/* loading for a stylesheet include/import */
        XSLT_LOAD_DOCUMENT = 2  /* loading document at transformation time */
    } xsltLoadType;

    typedef xmlDocPtr (*xsltDocLoaderFunc)              (const xmlChar *URI,
                                                     xmlDictPtr dict,
                                                     int options,
                                                     void *ctxt,
                                                     xsltLoadType type);
    void        xsltSetLoaderFunc               (xsltDocLoaderFunc f);
    xsltDocLoaderFunc xsltDocDefaultLoader;

    /* Security */

    typedef struct _xsltSecurityPrefs xsltSecurityPrefs;
    typedef xsltSecurityPrefs *xsltSecurityPrefsPtr;

    typedef int (*xsltSecurityCheck)    (xsltSecurityPrefsPtr sec,
                                             xsltTransformContextPtr ctxt,
                                             const char *value);

    xsltSecurityPrefsPtr xsltNewSecurityPrefs   (void);
    void            xsltFreeSecurityPrefs       (xsltSecurityPrefsPtr sec);
    int             xsltSetSecurityPrefs        (xsltSecurityPrefsPtr sec,
                                                 xsltSecurityOption option,
                                                 xsltSecurityCheck func);
    xsltSecurityCheck   xsltGetSecurityPrefs    (xsltSecurityPrefsPtr sec, 
                                                 xsltSecurityOption option);
    int             xsltSetCtxtSecurityPrefs    (xsltSecurityPrefsPtr sec,
                                                 xsltTransformContextPtr ctxt);

    int                 xsltSecurityAllow               (xsltSecurityPrefsPtr sec,
                                                     xsltTransformContextPtr ctxt,
                                                     const char *value);
    int                 xsltSecurityForbid              (xsltSecurityPrefsPtr sec,
                                                     xsltTransformContextPtr ctxt,
                                                     const char *value);

    /* Profiling */
    xmlDocPtr   xsltGetProfileInformation       (xsltTransformContextPtr ctxt);

    /* extras */
    void        xsltRegisterAllExtras   (void);

    const xmlChar* const EXSLT_DATE_NAMESPACE;
    const xmlChar* const EXSLT_SETS_NAMESPACE;
    const xmlChar* const EXSLT_MATH_NAMESPACE;
    const xmlChar* const EXSLT_STRINGS_NAMESPACE;

    void exsltRegisterAll (void);
    int exsltDateXpathCtxtRegister (xmlXPathContextPtr ctxt,
                                                      const xmlChar *prefix);
    int exsltMathXpathCtxtRegister (xmlXPathContextPtr ctxt,
                                                      const xmlChar *prefix);
    int exsltSetsXpathCtxtRegister (xmlXPathContextPtr ctxt,
                                                      const xmlChar *prefix);
    int exsltStrXpathCtxtRegister (xmlXPathContextPtr ctxt,
                                                     const xmlChar *prefix);
"""
