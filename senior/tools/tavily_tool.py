from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr
from typing import Optional, Type, Union
from langchain_community.tools.tavily_search.tool import TavilySearchResults

class TavilyInput(BaseModel):
    query: str = Field(..., description="The user query to search Tavily for.")

class TavilyCrewTool(BaseTool):
    name: str = "TavilyCrewTool"
    description: str = "Tool for searching the web via TavilySearchResults"
    args_schema: Type[BaseModel] = TavilyInput

    _tavily = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tavily = TavilySearchResults(k=3, search_kwargs={"site": "psu.edu.sa"})

    def _run(self, query: Union[str, dict]) -> str:
        if isinstance(query, str):
            search_query = query
        else:
            search_query = query.get("query") or query.get("description")
        if not isinstance(search_query, str):
            return "Invalid query format."
        try:
            return self._tavily.run(search_query)
        except Exception as e:
            return f"Tavily search failed: {e}"
