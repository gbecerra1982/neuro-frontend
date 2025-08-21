from langchain.tools import Tool
from services.rag_retriever import retrieve_doc_fn


rag_doc_tool = Tool(
    name="rag_doc_tool",
    description="Tool encargada de recuperar información de documentos .docx para un día y pozo específicos",
    func=retrieve_doc_fn,
)

