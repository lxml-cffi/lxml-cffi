DEFS = """
     /* The set of XPath error codes. */
    typedef enum {
        XPATH_EXPRESSION_OK = 0,
        XPATH_NUMBER_ERROR,
        XPATH_UNFINISHED_LITERAL_ERROR,
        XPATH_START_LITERAL_ERROR,
        XPATH_VARIABLE_REF_ERROR,
        XPATH_UNDEF_VARIABLE_ERROR,
        XPATH_INVALID_PREDICATE_ERROR,
        XPATH_EXPR_ERROR,
        XPATH_UNCLOSED_ERROR,
        XPATH_UNKNOWN_FUNC_ERROR,
        XPATH_INVALID_OPERAND,
        XPATH_INVALID_TYPE,
        XPATH_INVALID_ARITY,
        XPATH_INVALID_CTXT_SIZE,
        XPATH_INVALID_CTXT_POSITION,
        XPATH_MEMORY_ERROR,
        XPTR_SYNTAX_ERROR,
        XPTR_RESOURCE_ERROR,
        XPTR_SUB_RESOURCE_ERROR,
        XPATH_UNDEF_PREFIX_ERROR,
        XPATH_ENCODING_ERROR,
        XPATH_INVALID_CHAR_ERROR,
        XPATH_INVALID_CTXT,
        XPATH_STACK_ERROR
    } xmlXPathError;

    typedef struct _xmlXPathContext xmlXPathContext;
    typedef xmlXPathContext *xmlXPathContextPtr;
    typedef struct _xmlXPathParserContext xmlXPathParserContext;
    typedef xmlXPathParserContext *xmlXPathParserContextPtr;
    typedef struct _xmlXPathCompExpr xmlXPathCompExpr;
    typedef xmlXPathCompExpr *xmlXPathCompExprPtr;
    typedef struct _xmlXPathObject xmlXPathObject;
    typedef xmlXPathObject *xmlXPathObjectPtr;

    xmlXPathContextPtr xmlXPathNewContext               (xmlDocPtr doc);
    void            xmlXPathFreeContext         (xmlXPathContextPtr ctxt);

    struct _xmlXPathContext {
        xmlDocPtr doc;                  /* The current document */
        xmlNodePtr node;                        /* The current node */

        /* the set of namespace declarations in scope for the expression */
        xmlHashTablePtr nsHash;         /* The namespaces hash table */

        /* The function name and URI when calling a function */
        const xmlChar *function;
        const xmlChar *functionURI;

        /* error reporting mechanism */
        void *userData;                     /* user specific data block */
        xmlStructuredErrorFunc error;       /* the callback in case of errors */

        /* dictionary */
        xmlDictPtr dict;                        /* dictionary if any */

        ...;
    };

    struct _xmlXPathParserContext {
        xmlXPathContextPtr  context;    /* the evaluation context */
        ...;
    };

    int         xmlXPathRegisterNs              (xmlXPathContextPtr ctxt,
                                                 const xmlChar *prefix,
                                                 const xmlChar *ns_uri);
    typedef void (*xmlXPathFunction) (xmlXPathParserContextPtr ctxt, int nargs);

    int         xmlXPathRegisterFunc            (xmlXPathContextPtr ctxt,
                                                 const xmlChar *name,
                                                 xmlXPathFunction f);
    int xmlXPathRegisterFuncNS          (xmlXPathContextPtr ctxt,
                                                 const xmlChar *name,
                                                 const xmlChar *ns_uri,
                                                 xmlXPathFunction f);
    int         xmlXPathRegisterVariable        (xmlXPathContextPtr ctxt,
                                                 const xmlChar *name,
                                                 xmlXPathObjectPtr value);
    void xmlXPathRegisteredVariablesCleanup(xmlXPathContextPtr ctxt);


    typedef struct _xmlNodeSet xmlNodeSet;
    typedef xmlNodeSet *xmlNodeSetPtr;

    struct _xmlNodeSet {
        int nodeNr;                     /* number of nodes in the set */
        xmlNodePtr *nodeTab;    /* array of nodes in no particular order */
        ...;
    };


    typedef enum {
        XPATH_UNDEFINED = 0,
        XPATH_NODESET = 1,
        XPATH_BOOLEAN = 2,
        XPATH_NUMBER = 3,
        XPATH_STRING = 4,
        XPATH_POINT = 5,
        XPATH_RANGE = 6,
        XPATH_LOCATIONSET = 7,
        XPATH_USERS = 8,
        XPATH_XSLT_TREE = 9  /* An XSLT value tree, non modifiable */
    } xmlXPathObjectType;

    struct _xmlXPathObject {
        xmlXPathObjectType type;
        xmlNodeSetPtr nodesetval;
        int boolval;
        double floatval;
        xmlChar *stringval;
        ...;
    };

    xmlXPathCompExprPtr xmlXPathCtxtCompile     (xmlXPathContextPtr ctxt,
                                                 const xmlChar *str);
    void            xmlXPathFreeCompExpr        (xmlXPathCompExprPtr comp);
    xmlXPathObjectPtr xmlXPathCompiledEval      (xmlXPathCompExprPtr comp,
                                                 xmlXPathContextPtr ctx);
    xmlNodeSetPtr   xmlXPathNodeSetCreate       (xmlNodePtr val);
    void            xmlXPathFreeNodeSet         (xmlNodeSetPtr obj);
    void            xmlXPathFreeObject          (xmlXPathObjectPtr obj);

    xmlXPathObjectPtr xmlXPathEvalExpression    (const xmlChar *str,
                                                 xmlXPathContextPtr ctxt);
    void        xmlXPathErr     (xmlXPathParserContextPtr ctxt,
                                 int error);

    xmlXPathObjectPtr valuePop                  (xmlXPathParserContextPtr ctxt);
    int         valuePush                       (xmlXPathParserContextPtr ctxt,
                                                 xmlXPathObjectPtr value);
    xmlXPathObjectPtr xmlXPathNewCString                (const char *val);
    xmlXPathObjectPtr xmlXPathNewFloat          (double val);
    xmlXPathObjectPtr xmlXPathNewBoolean                (int val);
    xmlXPathObjectPtr xmlXPathWrapNodeSet               (xmlNodeSetPtr val);
    void        xmlXPathNodeSetAdd              (xmlNodeSetPtr cur,
                                                 xmlNodePtr val);
"""
