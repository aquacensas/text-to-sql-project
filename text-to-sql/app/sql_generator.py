"""Sends the constructed prompt to OpenAI and returns a structured response containing 
the SQL query, explanation, confidence score, tables used, and query type."""

import sqlparse
import os
import json
import sqlparse
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, Any
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)

# pyrefly: ignore [missing-import]
from schema_extractor import SchemaExtractor
# pyrefly: ignore [missing-import]
from schema_filter import SchemaFilter
# pyrefly: ignore [missing-import]
from prompt_builder import PromptBuilder
# pyrefly: ignore [missing-import]
from ambiguity_handler import AmbiguityHandler

load_dotenv()

class SQLGenerator:

    def __init__(self):
        """Initializes all the componenets of the phase 1 process"""
        self.extractor=SchemaExtractor()
        self.schema=self.extractor.extract_full_schema()
        self.filter=SchemaFilter(self.schema)
        self.builder=PromptBuilder(self.schema)
        self.ambiguity=AmbiguityHandler()

        self.client=OpenAI()

    def validate_sql(self,sql:str)->bool:
        """This checks if the generated SQL Query is syntactically correct or not"""
        try:
            #sqlparse.parse() returns tuple of statement objects
            parsed=sqlparse.parse(sql)
            # If parsing returns nothing then the SQL is completly invalid
            if not parsed:
                return False
            if not parsed[0].tokens:
                return False

            return True
        except:
            # any unexpected error duting parsing = invalid SQL
            return False
    
    def build_structured_prompt(self,user_question:str,filtered_schema:Dict[str,Any])->str:
        '''Builds a prompt that instructs OpenAI to return Json instead of a plain SQL
        
        Why a separate method for this?
        The PromptBuilder from Phase 1 builds a prompt for plain SQL output.
        For structured output we need a different ending one that tells
        the LLM to return JSON with specific fields. Rather than modifying
        PromptBuilder, we build on top of it here.

        Why JSON output instead of just SQL?
        We need 5 pieces of information from the LLM that are:
        1. The SQL query itself
        2. A plain English explanation
        3. A confidence score
        4. Which tables were used
        5. The query type (SELECT, INSERT, etc.)
        JSON lets us get all 5 in one API call instead of making
        5 separate calls.'''

        filter_builder=PromptBuilder(filtered_schema)
        base_prompt=filter_builder.build_prompt(user_question)
        json_instruction="""
        === OUTPUT FORMAT ===

        You must respond with ONLY a valid JSON object in exactly this format,
        with no text before or after it:

        {
            "sql": "your SQL query here",
            "explanation": "plain English explanation of what this query does",
            "confidence_score": 0.95,
            "tables_used": ["table1", "table2"],
            "query_type": "SELECT"
        }

        Rules for the JSON:
        - sql: must be a valid PostgreSQL SELECT query
        - explanation: one or two sentences in plain English
        - confidence_score: float between 0.0 and 1.0
        - (1.0 = very confident, 0.0 = very uncertain)
        - tables_used: list of table names your query references
        - query_type: must be one of SELECT, INSERT, UPDATE, DELETE, DDL

        Question to answer: """ + user_question

        return base_prompt + json_instruction

    def call_openai(self,prompt:str)->str:
        
        response=self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                'role':'system',
                'content':('You are a SQL Expert that generates PostgreSQL queries'
                            'You always respond to valid json only.'
                            'no code fences and no explanation outside the json')
                },
                {
                    'role':'user',
                    'content': prompt
                }
            ],
            temperature=0,
            max_tokens=500,
            stream=False
            )
        return response.choices[0].message.content  # type: ignore
            
            
    def parse_llm_response(self,raw_response:str)-> Dict[str,Any]:
        """Converts the raw JSON string from OpenAI into a Python dictionary.
        
        Why do we need this?
        Even though we instructed the LLM to return only JSON, it
        sometimes wraps the response in markdown code fences like:
        
        ```json
                { ... }
        ```
        
        """

        try:
            cleaned=raw_response.strip() # Stripes both the end 
            # Removes mardown code fences if present
            if cleaned.startswith('```'):
                cleaned=cleaned[cleaned.find('\n'):]
                cleaned=cleaned.strip()
            
            parsed=json.loads(cleaned)
            return parsed
        
        except json.JSONDecodeError as e:
            # if we cant parse the json then return the structured error
            return{
                "sql": "",
                "explanation": f"Failed to parse LLM response: {str(e)}",
                "confidence_score": 0.0,
                "tables_used": [],
                "query_type": "UNKNOWN",
                "error": True
            }

    def generate(self,user_question:str)->Dict[str,Any]:
        '''Generate SQL Query for a user question
            with structured dict, user question,sql,explanation,confidence score
            table_used, query_type and additional met data
        '''
        logger.info(f"Generating SQL for: {user_question[:50]}...")

        # Check for ambiguity before doing anything else
        ambiguity_result=self.ambiguity.check_and_handle(user_question)
        if ambiguity_result['needs_clarification']:
            logger.warning("Question flagged as ambiguous — returning clarification")
            return ambiguity_result

        # Filter schema to only relevant tables
        # This keeps the prompt focused and saves tokens
        filtered_schema=self.filter.filter_schema(user_question)

        # Build the structured prompt with JSON output instructions
        prompt=self.build_structured_prompt(user_question,filtered_schema)

        # Call OpenAI and get raw response
        raw_response=self.call_openai(prompt)

        # Parse the JSON response into a Python dict
        result=self.parse_llm_response(raw_response)

        # Validate SQL syntax
        # If invalid, retry once with the error message added to the prompt
        if not result.get('error') and not self.validate_sql(result.get('sql','')):
            retry_prompt=prompt+f"""
            The previous attempt generated invalid SQL. Please try again.
            Previous invalid SQL: {result.get('sql', '')}
            Error: SQL syntax validation failed.
            Generate a corrected version in the same JSON format.
            """
            logger.warning("SQL validation failed — retrying with error context")
            # Retry API call
            raw_response=self.call_openai(retry_prompt)
            result=self.parse_llm_response(raw_response)

        result['orignal_question']=user_question
        result['needs_clarifiaction']=False
        
        logger.info(f"SQL generated. Type: {result.get('query_type')}, Confidence: {result.get('confidence_score')}")

        return result

if __name__ == "__main__":
    generator = SQLGenerator()

    test_questions = [
        "Which customers have spent the most money?",
        "How many orders are pending?",
        "show me revenue"   # ambiguous 
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        print("-" * 50)
        result = generator.generate(question)

        if result.get("needs_clarification"):
            print(result["message"])
        else:
            print(f"SQL: {result.get('sql')}")
            print(f"Explanation: {result.get('explanation')}")
            print(f"Confidence: {result.get('confidence_score')}")
            print(f"Tables used: {result.get('tables_used')}")
            print(f"Query type: {result.get('query_type')}")

        
