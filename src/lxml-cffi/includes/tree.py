from .cffi_base import ffi

ffi.cdef("""
    typedef unsigned char xmlChar;
    xmlChar * xmlStrdup(const xmlChar *cur);
    int         xmlStrcmp                (const xmlChar *str1,
                                         const xmlChar *str2);
    const xmlChar * xmlStrstr            (const xmlChar *str,
                                         const xmlChar *val);
    const char * xmlParserVersion;
    static const int LIBXML_VERSION;

    void *xmlMalloc(size_t size);
    void xmlFree(void *mem);
    int xmlIsChar_ch(xmlChar ch);

    int xmlThrDefIndentTreeOutput(int v);
    int xmlThrDefLineNumbersDefaultValue(int v);

    /* Dict */

    typedef struct _xmlDict xmlDict;
    typedef xmlDict *xmlDictPtr;
    int 		xmlDictOwns	(xmlDictPtr dict,
 					 const xmlChar *str);
    const xmlChar * 	xmlDictLookup	(xmlDictPtr dict,
		                         const xmlChar *name,
		                         int len);
    const xmlChar * 	xmlDictExists	(xmlDictPtr dict,
		                         const xmlChar *name,
		                         int len);

    const char * const XML_XML_NAMESPACE;

    typedef enum {
        XML_ELEMENT_NODE=		1,
        XML_ATTRIBUTE_NODE=		2,
        XML_TEXT_NODE=		3,
        XML_CDATA_SECTION_NODE=	4,
        XML_ENTITY_REF_NODE=	5,
        XML_ENTITY_NODE=		6,
        XML_PI_NODE=		7,
        XML_COMMENT_NODE=		8,
        XML_DOCUMENT_NODE=		9,
        XML_DOCUMENT_TYPE_NODE=	10,
        XML_DOCUMENT_FRAG_NODE=	11,
        XML_NOTATION_NODE=		12,
        XML_HTML_DOCUMENT_NODE=	13,
        XML_DTD_NODE=		14,
        XML_ELEMENT_DECL=		15,
        XML_ATTRIBUTE_DECL=		16,
        XML_ENTITY_DECL=		17,
        XML_NAMESPACE_DECL=		18,
        XML_XINCLUDE_START=		19,
        XML_XINCLUDE_END=		20
       ,XML_DOCB_DOCUMENT_NODE=	21
    } xmlElementType;

    /* xmlDoc */

    typedef struct _xmlDoc xmlDoc;
    typedef xmlDoc *xmlDocPtr;
    struct _xmlDoc {
        void           *_private;	/* application data */
        xmlElementType  type;       /* XML_DOCUMENT_NODE, must be second ! */
        struct _xmlNode *children;	/* the document tree */
        struct _xmlNode *last;	/* last child link */

        int             standalone; /* standalone document (no external refs) */
        struct _xmlDtd  *intSubset;	/* the document internal subset */
        struct _xmlDtd  *extSubset;	/* the document external subset */
        const xmlChar  *version;	/* the XML version string */
        const xmlChar  *encoding;   /* external initial encoding, if any */
        void           *ids;        /* Hash table for ID attributes if any */
        const xmlChar  *URL;	/* The URI for that document */
        struct _xmlDict *dict;      /* dict used to allocate names or NULL */
        ...;
    };

    /* XML namespace */

    typedef struct _xmlNs xmlNs;
    typedef xmlNs *xmlNsPtr;
    struct _xmlNs {
        struct _xmlNs  *next;	/* next Ns link for this node  */
        const xmlChar *href;	/* URL for the namespace */
        const xmlChar *prefix;	/* prefix for the namespace */
        ...;
    };


    /* xmlAttr */

    typedef struct _xmlAttr xmlAttr;
    typedef xmlAttr *xmlAttrPtr;

    struct _xmlAttr {
        xmlElementType   type;      /* XML_ATTRIBUTE_NODE, must be second ! */
        const xmlChar   *name;      /* the name of the property */
        struct _xmlNode *children;	/* the value of the property */
        struct _xmlNode *parent;	/* child->parent link */
        struct _xmlAttr *next;	/* next sibling link  */
        struct _xmlDoc  *doc;	/* the containing document */
        xmlNs           *ns;        /* pointer to the associated namespace */
        ...;
    };

    /* xmlID */

    typedef struct _xmlID xmlID;
    typedef xmlID *xmlIDPtr;
    struct _xmlID {
        xmlAttrPtr        attr;	/* The attribute holding it */
        ...;
    };

    /* xmlNode */

    typedef struct _xmlNode xmlNode;
    typedef xmlNode *xmlNodePtr;

    struct _xmlNode {
        void           *_private;	/* application data */
        xmlElementType   type;	/* type number, must be second ! */
        const xmlChar   *name;      /* the name of the node, or the entity */
        struct _xmlNode *children;	/* parent->childs link */
        struct _xmlNode *last;	/* last child link */
        struct _xmlNode *parent;	/* child->parent link */
        struct _xmlNode *next;	/* next sibling link  */
        struct _xmlNode *prev;	/* previous sibling link  */
        struct _xmlDoc  *doc;	/* the containing document */

        /* End of common part */
        xmlNs           *ns;        /* pointer to the associated namespace */
        xmlChar         *content;   /* the content */
        struct _xmlAttr *properties;/* properties list */
        xmlNs           *nsDef;     /* namespace definitions on this node */
        unsigned short   line;	/* line number */
        ...;
    };

    xmlNodePtr xmlNewDocNode		(xmlDocPtr doc,
					 xmlNsPtr ns,
					 const xmlChar *name,
					 const xmlChar *content);
    xmlNodePtr 	xmlNewDocText		(xmlDocPtr doc,
					 const xmlChar *content);
    xmlNodePtr 	xmlNewDocComment	(xmlDocPtr doc,
					 const xmlChar *content);
    xmlNodePtr 	xmlNewCDataBlock	(xmlDocPtr doc,
					 const xmlChar *content,
					 int len);
    xmlNodePtr 	xmlNewReference		(xmlDocPtr doc,
					 const xmlChar *name);
    xmlNodePtr 	xmlNewDocPI		(xmlDocPtr doc,
					 const xmlChar *name,
					 const xmlChar *content);
    xmlNodePtr xmlDocCopyNode		(const xmlNodePtr node,
					 xmlDocPtr doc,
					 int recursive);
    xmlNodePtr 	xmlCopyNode		(const xmlNodePtr node,
					 int recursive);
    void xmlFreeNode		(xmlNodePtr cur);

    xmlDocPtr xmlNewDoc		(const xmlChar *version);
    xmlDocPtr xmlCopyDoc		(xmlDocPtr doc,
					 int recursive);
    void xmlFreeDoc		(xmlDocPtr cur);
    xmlNodePtr xmlDocGetRootElement	(xmlDocPtr doc);
    xmlNodePtr xmlDocSetRootElement	(xmlDocPtr doc,
					 xmlNodePtr root);

    xmlNodePtr xmlAddChild		(xmlNodePtr parent,
					 xmlNodePtr cur);
    xmlNodePtr 	xmlAddPrevSibling	(xmlNodePtr cur,
					 xmlNodePtr elem);
    xmlNodePtr	xmlAddNextSibling	(xmlNodePtr cur,
					 xmlNodePtr elem);
    void 	xmlUnlinkNode		(xmlNodePtr cur);
    xmlNodePtr      xmlReplaceNode	(xmlNodePtr old,
                                         xmlNodePtr cur);
    void 	xmlNodeSetName		(xmlNodePtr cur,
					 const xmlChar *name);
    xmlChar * 	xmlNodeGetContent	(xmlNodePtr cur);
    void 	xmlNodeSetContent	(xmlNodePtr cur,
					 const xmlChar *content);
    xmlChar * 	xmlNodeGetBase		(xmlDocPtr doc,
					 xmlNodePtr cur);
    void 	xmlNodeSetBase		(xmlNodePtr cur,
					 const xmlChar *uri);
    xmlAttrPtr xmlGetID	       (xmlDocPtr doc,
					const xmlChar *ID);

    xmlAttrPtr 	xmlNewNsProp		(xmlNodePtr node,
					 xmlNsPtr ns,
					 const xmlChar *name,
					 const xmlChar *value);
    xmlChar * xmlGetNsProp		(xmlNodePtr node,
					 const xmlChar *name,
					 const xmlChar *nameSpace);
    xmlAttrPtr 	xmlSetNsProp		(xmlNodePtr node,
					 xmlNsPtr ns,
					 const xmlChar *name,
					 const xmlChar *value);
    xmlAttrPtr 	xmlHasNsProp		(xmlNodePtr node,
					 const xmlChar *name,
					 const xmlChar *nameSpace);
    xmlNsPtr xmlNewNs		(xmlNodePtr node,
					 const xmlChar *href,
					 const xmlChar *prefix);
    void 	xmlFreeNs		(xmlNsPtr cur);
    xmlNsPtr 	xmlSearchNs		(xmlDocPtr doc,
					 xmlNodePtr node,
					 const xmlChar *nameSpace);
    xmlNsPtr 	xmlSearchNsByHref	(xmlDocPtr doc,
					 xmlNodePtr node,
					 const xmlChar *href);
    void 	xmlSetNs		(xmlNodePtr node,
					 xmlNsPtr ns);
    void 	xmlFreeNsList		(xmlNsPtr cur);

    xmlAttrPtr 	xmlNewProp		(xmlNodePtr node,
					 const xmlChar *name,
					 const xmlChar *value);
    int 	xmlRemoveProp		(xmlAttrPtr cur);
    xmlChar * 	xmlGetNodePath		(xmlNodePtr node);
    long 	xmlGetLineNo		(xmlNodePtr node);

    /* DTD */

    /* xmlElementContent */
    typedef enum {
        XML_ELEMENT_CONTENT_PCDATA = 1,
        XML_ELEMENT_CONTENT_ELEMENT,
        XML_ELEMENT_CONTENT_SEQ,
        XML_ELEMENT_CONTENT_OR
    } xmlElementContentType;

    typedef enum {
        XML_ELEMENT_CONTENT_ONCE = 1,
        XML_ELEMENT_CONTENT_OPT,
        XML_ELEMENT_CONTENT_MULT,
        XML_ELEMENT_CONTENT_PLUS
    } xmlElementContentOccur;

    typedef enum {
        XML_ELEMENT_TYPE_UNDEFINED = 0,
        XML_ELEMENT_TYPE_EMPTY = 1,
        XML_ELEMENT_TYPE_ANY,
        XML_ELEMENT_TYPE_MIXED,
        XML_ELEMENT_TYPE_ELEMENT
    } xmlElementTypeVal;

    typedef enum {
        XML_ATTRIBUTE_CDATA = 1,
        XML_ATTRIBUTE_ID,
        XML_ATTRIBUTE_IDREF	,
        XML_ATTRIBUTE_IDREFS,
        XML_ATTRIBUTE_ENTITY,
        XML_ATTRIBUTE_ENTITIES,
        XML_ATTRIBUTE_NMTOKEN,
        XML_ATTRIBUTE_NMTOKENS,
        XML_ATTRIBUTE_ENUMERATION,
        XML_ATTRIBUTE_NOTATION
    } xmlAttributeType;

    typedef enum {
        XML_ATTRIBUTE_NONE = 1,
        XML_ATTRIBUTE_REQUIRED,
        XML_ATTRIBUTE_IMPLIED,
        XML_ATTRIBUTE_FIXED
    } xmlAttributeDefault;

    typedef struct _xmlEnumeration xmlEnumeration;
    typedef xmlEnumeration *xmlEnumerationPtr;

    struct _xmlEnumeration {
        struct _xmlEnumeration    *next;	/* next one */
        const xmlChar            *name;	/* Enumeration name */
    };

    typedef struct _xmlAttribute xmlAttribute;
    typedef xmlAttribute *xmlAttributePtr;

    struct _xmlAttribute {
        const xmlChar          *name;	/* Attribute name */
        struct _xmlAttribute  *nexth;	/* next in hash table */
        xmlAttributeType       atype;	/* The attribute type */
        xmlAttributeDefault      def;	/* the default */
        const xmlChar  *defaultValue;	/* or the default value */
        xmlEnumerationPtr       tree;       /* or the enumeration tree if any */
        const xmlChar        *prefix;	/* the namespace prefix if any */
        const xmlChar          *elem;	/* Element holding the attribute */
        ...;
    };

    typedef struct _xmlElementContent xmlElementContent;
    typedef xmlElementContent *xmlElementContentPtr;

    struct _xmlElementContent {
        xmlElementContentType     type;	/* PCDATA, ELEMENT, SEQ or OR */
        xmlElementContentOccur    ocur;	/* ONCE, OPT, MULT or PLUS */
        const xmlChar             *name;	/* Element name */
        struct _xmlElementContent *c1;	/* first child */
        struct _xmlElementContent *c2;	/* second child */
        ...;
    };

    /* xmlElement */
    typedef struct _xmlElement xmlElement;
    typedef xmlElement *xmlElementPtr;

    struct _xmlElement {
        const xmlChar          *name;	/* Element name */
        xmlElementTypeVal      etype;	/* The type */
        xmlElementContentPtr content;	/* the allowed element content */
        xmlAttributePtr   attributes;	/* List of the declared attributes */
        ...;
    };

    /* xmlEntity */
    typedef struct _xmlEntity xmlEntity;
    typedef xmlEntity *xmlEntityPtr;

    struct _xmlEntity {
        const xmlChar          *name;	/* Entity name */
        xmlChar                *orig;	/* content without ref substitution */
        xmlChar             *content;	/* content or ndata if unparsed */
        ...;
    };

    /* xmlEncoding */
    typedef struct _xmlCharEncodingHandler xmlCharEncodingHandler;
    typedef xmlCharEncodingHandler *xmlCharEncodingHandlerPtr;

    xmlCharEncodingHandlerPtr xmlFindCharEncodingHandler(const char *name);
    int xmlCharEncCloseFunc		(xmlCharEncodingHandler *handler);

    typedef enum {
        XML_CHAR_ENCODING_ERROR=   -1, /* No char encoding detected */
        XML_CHAR_ENCODING_NONE=	0, /* No char encoding detected */
        XML_CHAR_ENCODING_UTF8=	1, /* UTF-8 */
        XML_CHAR_ENCODING_UTF16LE=	2, /* UTF-16 little endian */
        XML_CHAR_ENCODING_UTF16BE=	3, /* UTF-16 big endian */
        XML_CHAR_ENCODING_UCS4LE=	4, /* UCS-4 little endian */
        XML_CHAR_ENCODING_UCS4BE=	5, /* UCS-4 big endian */
        XML_CHAR_ENCODING_EBCDIC=	6, /* EBCDIC uh! */
        XML_CHAR_ENCODING_UCS4_2143=7, /* UCS-4 unusual ordering */
        XML_CHAR_ENCODING_UCS4_3412=8, /* UCS-4 unusual ordering */
        XML_CHAR_ENCODING_UCS2=	9, /* UCS-2 */
        XML_CHAR_ENCODING_8859_1=	10,/* ISO-8859-1 ISO Latin 1 */
        XML_CHAR_ENCODING_8859_2=	11,/* ISO-8859-2 ISO Latin 2 */
        XML_CHAR_ENCODING_8859_3=	12,/* ISO-8859-3 */
        XML_CHAR_ENCODING_8859_4=	13,/* ISO-8859-4 */
        XML_CHAR_ENCODING_8859_5=	14,/* ISO-8859-5 */
        XML_CHAR_ENCODING_8859_6=	15,/* ISO-8859-6 */
        XML_CHAR_ENCODING_8859_7=	16,/* ISO-8859-7 */
        XML_CHAR_ENCODING_8859_8=	17,/* ISO-8859-8 */
        XML_CHAR_ENCODING_8859_9=	18,/* ISO-8859-9 */
        XML_CHAR_ENCODING_2022_JP=  19,/* ISO-2022-JP */
        XML_CHAR_ENCODING_SHIFT_JIS=20,/* Shift_JIS */
        XML_CHAR_ENCODING_EUC_JP=   21,/* EUC-JP */
        XML_CHAR_ENCODING_ASCII=    22 /* pure ASCII */
    } xmlCharEncoding;

    typedef int (* xmlCharEncodingOutputFunc)(unsigned char *out, int *outlen,
                                          const unsigned char *in, int *inlen);
    xmlCharEncoding xmlDetectCharEncoding(const unsigned char *in,
					 int len);
    const char *	xmlGetCharEncodingName	(xmlCharEncoding enc);

    int xmlValidateNCName	(const xmlChar *value,
					 int space);
    typedef struct _xmlBuffer xmlBuffer;
    typedef xmlBuffer *xmlBufferPtr;

    const xmlChar* xmlBufferContent	(const xmlBufferPtr buf);
    int 	xmlBufferLength		(const xmlBufferPtr buf);
    xmlBufferPtr xmlBufferCreate		(void);
    void 	xmlBufferFree		(xmlBufferPtr buf);
    int 	xmlNodeBufGetContent	(xmlBufferPtr buffer,
					 xmlNodePtr cur);
    void 	xmlBufferWriteChar	(xmlBufferPtr buf,
					 const char *string);

    /* xmlIO */
    typedef struct _xmlParserInputBuffer xmlParserInputBuffer;
    typedef xmlParserInputBuffer *xmlParserInputBufferPtr;
    typedef int (*xmlInputReadCallback) (void * context, char * buffer, int len);
    typedef int (*xmlInputCloseCallback) (void * context);

    struct _xmlParserInputBuffer {
        void*                  context;
        xmlInputReadCallback   readcallback;
        ...;
    };

    typedef struct _xmlOutputBuffer xmlOutputBuffer;
    typedef xmlOutputBuffer *xmlOutputBufferPtr;
    struct _xmlOutputBuffer {
        xmlBufferPtr buffer;    /* Local buffer encoded in UTF-8 or ISOLatin */
        xmlBufferPtr conv;      /* if encoder != NULL buffer for output */
        int error;
        ...;
    };
    typedef int (*xmlOutputWriteCallback) (
        void * context, const char * buffer, int len);
    typedef int (*xmlOutputCloseCallback) (void * context);

    xmlOutputBufferPtr xmlOutputBufferCreateIO(xmlOutputWriteCallback   iowrite,
					 xmlOutputCloseCallback  ioclose,
					 void *ioctx,
					 xmlCharEncodingHandlerPtr encoder);
    xmlOutputBufferPtr xmlOutputBufferCreateFilename	(const char *URI,
					 xmlCharEncodingHandlerPtr encoder,
					 int compression);
    xmlOutputBufferPtr xmlAllocOutputBuffer(xmlCharEncodingHandlerPtr encoder);
    int xmlOutputBufferFlush		(xmlOutputBufferPtr out);
    int xmlOutputBufferClose		(xmlOutputBufferPtr out);
    int xmlOutputBufferWrite		(xmlOutputBufferPtr out,
					 int len,
					 const char *buf);
    int xmlOutputBufferWriteString	(xmlOutputBufferPtr out,
					 const char *str);
    int xmlOutputBufferWriteEscape	(xmlOutputBufferPtr out,
					 const xmlChar *str,
					 xmlCharEncodingOutputFunc escaping);
    void 	xmlNodeDumpOutput	(xmlOutputBufferPtr buf,
					 xmlDocPtr doc,
					 xmlNodePtr cur,
					 int level,
					 int format,
					 const char *encoding);

    /* HTML nodes */
    void 	htmlNodeDumpFormatOutput(xmlOutputBufferPtr buf,
					 xmlDocPtr doc,
					 xmlNodePtr cur,
					 const char *encoding,
					 int format);

    /* DTD */

    typedef struct _xmlDtd xmlDtd;
    typedef xmlDtd *xmlDtdPtr;
    struct _xmlDtd {
        const xmlChar *name;	/* Name of the DTD */
        struct _xmlNode *children;	/* the value of the property link */

        void          *notations;   /* Hash table for notations if any */
        void          *elements;    /* Hash table for elements if any */
        void          *attributes;  /* Hash table for attributes if any */
        void          *entities;    /* Hash table for entities if any */
        const xmlChar *ExternalID;	/* External identifier for PUBLIC DTD */
        const xmlChar *SystemID;	/* URI for a SYSTEM or PUBLIC DTD */
        void          *pentities;   /* Hash table for param entities if any */
        ...;
    };

    xmlDtdPtr 	xmlCopyDtd		(xmlDtdPtr dtd);
    void 	xmlFreeDtd		(xmlDtdPtr cur);

    /*
     * The hash table.
     */
    typedef struct _xmlHashTable xmlHashTable;
    typedef xmlHashTable *xmlHashTablePtr;
    typedef void (*xmlHashScanner)(void *payload, void *data, xmlChar *name);
    void xmlHashScan	(xmlHashTablePtr table,
					 xmlHashScanner f,
					 void *data);
    void * 		xmlHashLookup	(xmlHashTablePtr table,
					 const xmlChar *name);
    typedef void (*xmlHashDeallocator)(void *payload, xmlChar *name);
    xmlHashTablePtr xmlHashCreate(int size);
    xmlHashTablePtr xmlHashCreateDict(int size,
				      xmlDictPtr dict);
    int xmlHashSize(xmlHashTablePtr table);
    void xmlHashFree(xmlHashTablePtr table,
		     xmlHashDeallocator f);

    /* URI */
    xmlChar * 	xmlBuildURI		(const xmlChar *URI,
					 const xmlChar *base);

""")
