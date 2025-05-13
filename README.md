# Student Advisor AI System

This system uses agentic AI to create an intelligent student advisor that combines:
1. SQL database access for student information
2. Web crawling of university documents
3. Multiple specialized AI agents for comprehensive advising

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your API keys:
```
OPENAI_API_KEY=your_openai_key
COMPOSIO_API_KEY=your_composio_key
PINECONE_API_KEY=your_pinecone_key
```

3. Make sure your MySQL database is running with the correct schema. The system expects a database named 'spd' at localhost:3306.

## Components

### 1. SQL Database Access
- Uses Composio and CrewAI for intelligent SQL querying
- Stores and retrieves student academic information

### 2. Web Crawler
- Crawls university documents and policies
- Stores document embeddings in Pinecone for semantic search
- Automatically updates document database

### 3. AI Agents
- SQL Agent: Handles database queries
- Progress Tracker: Analyzes student academic progress
- Course Recommender: Provides personalized course suggestions
- Advisor Support: Coordinates between agents for comprehensive advising

## Usage

Run the main application:
```bash
python main.py
```



Each function combines multiple agents to provide comprehensive academic support.
