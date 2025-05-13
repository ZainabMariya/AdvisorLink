import os
import warnings
import asyncio
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_community.utilities.sql_database import SQLDatabase
from langchain.agents import create_sql_agent
from langchain.agents.agent_types import AgentType
from langchain_openai import ChatOpenAI
from langchain.tools.tavily_search import TavilySearchResults
from crewai import Agent, Crew, Task
from senior.tools.pinecone_tool import PineconeSearchTool
from senior.tools.pdf_tool import PDFSearchTool
from flask import Flask, request, jsonify
from flask_cors import CORS
import re

# --- Setup ---
warnings.filterwarnings('ignore')
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
db_uri = os.getenv("DB_URI")

# --- App Config ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SESSION_SECRET')

# Configure CORS
cors_origin = os.getenv('FRONTEND_URL', '*')
CORS(app, resources={r"/*": {"origins": cors_origin}})

if not openai_api_key or not db_uri:
    raise ValueError("Missing OPENAI_API_KEY or DB_URI")

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "expose_headers": ["Content-Type", "Authorization"]
    }
})

# DB Connection
engine = create_engine(db_uri)
with engine.connect() as conn:
    print("✅ Connected to DB. Tables:")
    for row in conn.execute(text("SHOW TABLES")):
        print("-", row[0])

# LangChain SQL
db = SQLDatabase.from_uri(db_uri)
llm = ChatOpenAI(api_key=openai_api_key, model="gpt-4o-mini", temperature=0)
sql_agent_executor = create_sql_agent(llm=llm, db=db, agent_type=AgentType.OPENAI_FUNCTIONS, verbose=False)

# --- Tools ---
pinecone_tool = PineconeSearchTool(index_name="psu-website")
tavily_tool = TavilySearchResults(k=3, search_kwargs={"site": "psu.edu.sa"})
advisor_manual_tool = PDFSearchTool(pdf_path="senior/AdvisingManualIndexing/Advising Manual.pdf").get_tool()
# --- Agents ---
db_schema = (
    "Tables: Student, Course, GPA_History, Absence, Advisor, Enrollment, Department, Major.\n"
)

sql_agent = Agent(
    role="SQL Agent",
    goal="Answer student-specific academic questions using SQL.",
    backstory=db_schema,
    tools=[],
    llm=llm,
    allow_delegation=False,
    verbose=True
)

psu_web_agent = Agent(
    role="PSU Info Agent",
    goal="Answer general PSU queries using Pinecone and filtered Tavily search.",
    backstory=(
        "Use PineconeSearchTool to check PSU internal content. If that fails, use TavilySearchResults to search psu.edu.sa."
    ),
    tools=[pinecone_tool, tavily_tool],
    llm=llm,
    allow_delegation=False,
    verbose=True
)

quality_agent = Agent(
    role="Quality Assurance Agent",
    goal="Compare SQL and Web Agent answers and pick the most helpful one.",
    backstory=(
        "You're a QA agent. Given two answers to the same academic prompt—one from SQL, one from Web—select the most accurate and relevant. "
        "Combine if needed. If both are irrelevant, explain that."
    ),
    tools=[],
    llm=llm,
    allow_delegation=False,
    verbose=False
)

advisor_agent = Agent(
    role="Academic Advisor",
    goal="Answer academic planning questions using the PSU advising manual index.",
    backstory="You're a knowledgeable advisor who understands study plans, prerequisites, and credit policies.",
    tools=[advisor_manual_tool],
    llm=llm,
    allow_delegation=False,
    verbose=False
)

crew = Crew(
    agents=[sql_agent, psu_web_agent, quality_agent, advisor_agent],
    tasks=[],
    llm=llm,
    verbose=True
)

def is_useful(text: str) -> bool:
    if not text:
        return False
    bad = ["no result", "not found", "no data", "not available", "empty"]
    return not any(b in text.lower() for b in bad)

# --- Main Loop ---
async def faculty_advisor_chatbot(prompt=None):
    print("\n🤖 PSU Academic Advisor Chatbot (Faculty Mode)")
    print("Type 'exit' to quit.\n")

    while True:
        user_prompt = prompt if prompt else input("Ask anything> ").strip()
        if user_prompt.lower() == "exit":
            break

        print("🔍 Running SQL Agent...")
        try:
            sql_result_dict = sql_agent_executor.invoke({"input": user_prompt})
            sql_result = sql_result_dict.get("output", "No response generated.")
        except Exception as e:
            sql_result = f"SQL Error: {e}"

        print("🔎 Running PSU Web Agent...")
        PSU_Web_rag_task = Task(
            description=f"The user asked: {user_prompt}. Respond with a clear and accurate answer based only on PSU website content.",
            expected_output="An accurate answer using only information from the PSU website documents.",
            agent=psu_web_agent
        )

        advisor_task = Task(
            description=f"The student asked: {user_prompt}. Provide a clear and accurate advising answer using the knowledge you have.",
            expected_output="A complete and helpful advising answer based on PSU's advising manual.",
            agent=advisor_agent
        )
        crew.tasks = [PSU_Web_rag_task, advisor_task]
        web_result = crew.kickoff()
        # Filter Tavily results to only include psu.edu.sa
        if isinstance(web_result, list):
            web_result = [r for r in web_result if 'psu.edu.sa' in (r.get('url') or '')]
        elif isinstance(web_result, str) and 'psu.edu' in web_result:
            # Optionally, you can do a more advanced filter for string results
            lines = web_result.split('\n')
            web_result = '\n'.join([line for line in lines if 'psu.edu.sa' in line or 'http' not in line])

        print("🧑‍💼 Running Advisor Agent...")
        advisor_task = Task(
            description=f"The user asked: {user_prompt}. Provide advising guidance based on the PSU manual.",
            expected_output="A clear and accurate advising answer based on PSU's policies.",
            agent=advisor_agent
        )
        crew.tasks = [advisor_task]
        try:
            advisor_result = crew.kickoff()
            print(f"Advisor Agent Output: {advisor_result!r}")
        except Exception as e:
            print(f"Advisor Agent Error: {e}")
            advisor_result = f"Advisor Error: {e}"

        print("✅ Evaluating best result with Quality Agent (all three)...")
        comparison_task = Task(
            description=(
                f"The user asked: '{user_prompt}'. Compare the following responses:\n\n"
                f"SQL Agent Response:\n{sql_result}\n\n"
                f"PSU Web Agent Response:\n{web_result}\n\n"
                f"Advisor Agent Response:\n{advisor_result}\n\n"
                f"Choose the most accurate, complete, and helpful answer and provide only the final output to the end user. Combine if necessary. The user should not know which agent information came from or which agent was correct or incorrect"
            ),
            expected_output="Final user-facing answer, with no mention of the agents.",
            agent=quality_agent
        )
        crew.tasks = [comparison_task]
        final_result = crew.kickoff()
        print("\n🎓 Final Answer (Faculty):\n", final_result)
        return final_result

def clean_and_format_response(text):
    # Remove all triple backtick code blocks
    text = re.sub(r"`{3,}", "", text)
    # Remove leading/trailing whitespace
    text = text.strip()
    # Replace 3+ newlines with just two
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

@app.route('/chatbot', methods=['POST'])
def chatbot():
    try:
        user_prompt = request.json.get('prompt')
        if not user_prompt:
            return jsonify({'error': 'No prompt provided'}), 400

        print(f"Received prompt: {user_prompt}")  # Debug log

        # Create new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            final_result = loop.run_until_complete(faculty_advisor_chatbot(user_prompt))
            print(f"Final result: {final_result}")  # Debug log
            # Clean and format the response before returning
            final_result = clean_and_format_response(final_result)
            return jsonify({'answer': final_result})
        except Exception as e:
            print(f"Error in async operation: {str(e)}")  # Debug log
            return jsonify({'error': str(e)}), 500
        finally:
            loop.close()
    except Exception as e:
        print(f"Error in route handler: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200

# --- Run ---
if __name__ == "__main__":
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
