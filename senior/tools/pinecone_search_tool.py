import os
import json
import asyncio
from typing import Optional, Type, Union, Any, Dict, List

from pydantic import BaseModel, Field, PrivateAttr
from crewai.tools import BaseTool 

from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore


# Embedding model configuration - must match the crawler's settings
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMENSION = 3072


class QueryInput(BaseModel):
    query: str = Field(..., description="User query to retrieve documents for.")
    k: int = Field(3, ge=1, le=20, description="Top-k results to return.")


class PineconeSearchTool(BaseTool):
    name: str = "PineconeSearchTool"
    description: str = "Retrieves relevant chunks from Pinecone (psu-web-auto) and returns them with source metadata."
    args_schema: Type[BaseModel] = QueryInput

    # Configurable fields (safe for pydantic)
    index_name: str = "psu-web-auto"
    namespace: Optional[str] = None
    text_key: str = "text"

    # ✅ Private cached objects (NOT part of pydantic validation)
    _pc: Optional[Pinecone] = PrivateAttr(default=None)
    _index: Any = PrivateAttr(default=None)
    _embeddings: Optional[OpenAIEmbeddings] = PrivateAttr(default=None)
    _vectorstore: Optional[PineconeVectorStore] = PrivateAttr(default=None)

    def _ensure_ready(self) -> None:
        """Initialize and validate Pinecone, embedding, and vectorstore connections."""
        openai_key = os.getenv("OPENAI_API_KEY")
        pinecone_key = os.getenv("PINECONE_API_KEY")

        if not openai_key:
            raise ValueError("OPENAI_API_KEY is missing.")
        if not pinecone_key:
            raise ValueError("PINECONE_API_KEY is missing.")

        if self._pc is None:
            self._pc = Pinecone(api_key=pinecone_key)

            existing = self._pc.list_indexes().names()
            if self.index_name not in existing:
                raise ValueError(
                    f"Pinecone index '{self.index_name}' does not exist. "
                    f"Create it first using your crawler script."
                )

        if self._index is None:
            self._index = self._pc.Index(self.index_name)

        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                api_key=openai_key,
                model=EMBED_MODEL,
                dimensions=EMBED_DIMENSION,
            )

        if self._vectorstore is None:
            self._vectorstore = PineconeVectorStore(
                index=self._index,
                embedding=self._embeddings,
                namespace=self.namespace,
                text_key=self.text_key,
            )

    @staticmethod
    def _normalize_input(inp: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize inputs into {query, k}."""
        if isinstance(inp, dict):
            return inp

        if isinstance(inp, str):
            s = inp.strip()
            if not s:
                return {"query": "", "k": 3}
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return parsed
                return {"query": str(parsed), "k": 3}
            except json.JSONDecodeError:
                return {"query": s, "k": 3}

        return {"query": str(inp), "k": 3}

    @staticmethod
    def _format_docs(docs: List[Any]) -> str:
        out = []
        for i, d in enumerate(docs, start=1):
            md = d.metadata or {}
            url = md.get("url") or md.get("canonical_url") or "unknown_url"
            title = md.get("page_title") or md.get("h1") or "untitled"
            section = md.get("section_heading") or "unknown_section"
            chunk_index = md.get("chunk_index", "NA")

            out.append(
                f"[{i}] {title} | {section} | chunk={chunk_index}\n"
                f"Source: {url}\n"
                f"{d.page_content}"
            )
        return "\n\n---\n\n".join(out)

    # ✅ CrewAI calls _run with structured args (query, k)
    def _run(self, query: Union[str, Dict[str, Any]] = None, k: int = 3) -> str:
        """
        CrewAI will pass args as:
          _run(query="...", k=3)
        But we also support dict/string for flexibility.
        """
        if isinstance(query, dict):
            payload = query
        else:
            payload = {"query": query, "k": k}

        payload = self._normalize_input(payload)
        q = payload.get("query", "")
        k = int(payload.get("k", 3))

        if not isinstance(q, str) or not q.strip():
            return "Invalid query: please provide a non-empty 'query' string."

        try:
            self._ensure_ready()
            retriever = self._vectorstore.as_retriever(search_kwargs={"k": k})

            try:
                docs = retriever.invoke(q)
            except Exception:
                docs = retriever.get_relevant_documents(q)

            if not docs:
                return "No relevant documents found."

            return self._format_docs(docs)

        except Exception as e:
            return f"Tool failed with error: {str(e)}"

    async def _arun(self, query: Union[str, Dict[str, Any]] = None, k: int = 3) -> str:
        return await asyncio.to_thread(self._run, query, k)
