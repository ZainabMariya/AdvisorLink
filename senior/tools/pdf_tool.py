from typing import List
from langchain_community.document_loaders import PDFMinerLoader
import pdfplumber
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.tools import Tool

class PDFSearchTool:
    def __init__(self, pdf_path: str):
        # Load and process the PDF with PDFMiner for text and PDFPlumber for tables
        loader = PDFMinerLoader(pdf_path)
        documents = loader.load()
        
        # Extract tables separately using PDFPlumber
        tables_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    # Convert table to formatted string
                    table_text = 'Table:\n'
                    for row in table:
                        # Clean and join row cells
                        row_text = ' | '.join(str(cell).strip() if cell else '' for cell in row)
                        table_text += f'{row_text}\n'
                    tables_text.append(table_text)
        
        # Add extracted tables as additional documents
        if tables_text:
            from langchain.schema import Document
            table_docs = [Document(page_content=text, metadata={'source': pdf_path, 'content_type': 'table'}) 
                         for text in tables_text]
            documents.extend(table_docs)
        
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        chunks = text_splitter.split_documents(documents)
        
        # Create vector store
        self.vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=OpenAIEmbeddings()
        )
        
        # Create retriever
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3}
        )
    
    def search(self, query: str) -> str:
        """Search the PDF content for relevant information."""
        docs = self.retriever.get_relevant_documents(query)
        if not docs:
            return "No relevant information found in the advising manual."
        
        # Combine the content from retrieved documents
        results = []
        for doc in docs:
            results.append(doc.page_content)
        
        return "\n\n".join(results)

    def get_tool(self) -> Tool:
        return Tool(
            name="pdf_search",
            func=self.search,
            description="Search the PSU advising manual PDF for academic policies and procedures."
        )
