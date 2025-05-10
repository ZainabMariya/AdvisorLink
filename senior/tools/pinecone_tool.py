from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, Type, Union
import json
import os

from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore  

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

class QueryInput(BaseModel):
    query: str = Field(..., description="The user query to retrieve documents for.")

class PineconeSearchTool(BaseTool):
    name: str = "PineconeSearchTool"
    description: str = "Tool for querying the Pinecone vector DB using LangChain."

    index_name: str
    namespace: Optional[str] = None
    args_schema: Type[BaseModel] = QueryInput

    def _run(self, query: Union[str, dict]) -> str:
        # Handle stringified JSON or dict
        if isinstance(query, str):
            try:
                query = json.loads(query)
            except json.JSONDecodeError:
                query = {"query": query}

        query = query.get("query") or query.get("description")
        if not isinstance(query, str):
            return "Invalid query format."

        try:
            # Initialize Pinecone client
            pc = Pinecone(api_key=PINECONE_API_KEY)
            index = pc.Index(self.index_name)

            # Initialize LangChain-compatible Pinecone vector store
            embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
            vectorstore = PineconeVectorStore(
                index=index,
                embedding=embeddings,
                namespace=self.namespace,
                text_key="text"
            )

            retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
            docs = retriever.get_relevant_documents(query)

            if not docs:
                return "No relevant documents found."

            return "\n\n".join([doc.page_content for doc in docs if doc.page_content])

        except Exception as e:
            return f"Tool failed with error: {str(e)}"
