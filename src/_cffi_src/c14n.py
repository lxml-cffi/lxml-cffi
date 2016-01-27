DEFS = """
    // xmlNodeSetPtr comes from xpath

    int xmlC14NDocSaveTo        (xmlDocPtr doc,
                                         xmlNodeSetPtr nodes,
                                         int mode, /* a xmlC14NMode */
                                         xmlChar **inclusive_ns_prefixes,
                                         int with_comments,
                                         xmlOutputBufferPtr buf);
    int         xmlC14NDocSave          (xmlDocPtr doc,
                                         xmlNodeSetPtr nodes,
                                         int mode, /* a xmlC14NMode */
                                         xmlChar **inclusive_ns_prefixes,
                                         int with_comments,
                                         const char* filename,
                                         int compression);

    int         xmlC14NDocDumpMemory    (xmlDocPtr doc,
                                         xmlNodeSetPtr nodes,
                                         int mode, /* a xmlC14NMode */
                                         xmlChar **inclusive_ns_prefixes,
                                         int with_comments,
                                         xmlChar **doc_txt_ptr);
"""
