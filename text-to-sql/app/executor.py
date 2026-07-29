""" Here we execute the SQL Query safely using two independant sandboxing layers:

Layer 1: Read Only database user
        The read-only user has SELECT permission in PostgreSQL
        Even if a write wuery reaches this layer, PostgreSQL rehects it at the permission level

Layer 2: Read only Transaction
        Every query runs inside BEGIN TRANSACTION READ ONLY 
        PostgreSQL rejects any write operation at the transaction level.
        The transaction always rolls back never commit.

Reason for 2 layers:
Defense in depth. Each layer is independent. You would need BOTH to
fail simultaneously for any damage to occur. In practice this means
even a bug in the guardrail middleware cannot cause database damage.

"""
from sqlalchemy import schema
import os
import time
import pandas as pd
from sqlalchemy import create_engine,text
from typing import Dict,Any
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)
# pyrefly: ignore [missing-import]
from hallucination import BackTranslationVerifier,ResultSanityChecker,MultiQueryValidator,ConfidenceScorer

# pyrefly: ignore [missing-import]
from sql_generator import SQLGenerator
# pyrefly: ignore [missing-import]
from guardrails import GuardrailMiddleware
# pyrefly: ignore [missing-import]
from query_executor import QueryExecutor

load_dotenv()



class ExecutionPipeline:
    def __init__(self):
        '''Initializes all three components once when the pipeline starts'''
        self.generator=SQLGenerator()
        self.guardrail=GuardrailMiddleware()
        self.executor=QueryExecutor()

        # Hallucination Components
        self.schema=self.generator.schema
        self.backtranslation_verifier=BackTranslationVerifier()
        self.result_sanity_checker=ResultSanityChecker()
        self.multi_query_validator=MultiQueryValidator()
        self.confidence_scorer=ConfidenceScorer()

    
    def run(self,user_question:str)->Dict[str,Any]:
        '''Runs the full end to end pipeline for user question'''
        generation_result=self.generator.generate(user_question)

        # if the question is ambiguous sql_generator returns clarification request
        # instead of the SQL Query
        if generation_result.get('needs_clarification'):
            return{
                "success": False,
                "needs_clarification": True,
                "message": generation_result.get("message"),
                "interpretations": generation_result.get("interpretations"),
                "sql": None,
                "explanation": None,
                "confidence_score": None,
                "approved": None,
                "blocked_reason": None,
                "data": [],
                "columns": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "error": "Question requires clarification"
            }
        
        # Checking if the sql generation failed i.e if the LLM couldnt generate SQL
        # or return an invalid JSON
        if generation_result.get('error'):
            return{
                "success": False,
                "needs_clarification": False,
                "sql": None,
                "explanation": generation_result.get("explanation"),
                "confidence_score": 0.0,
                "approved": None,
                "blocked_reason": None,
                "data": [],
                "columns": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "error": "SQL generation failed"
            }

        #Extract the generated SQL from the generation result 
        generated_sql=generation_result.get('sql','')

        # Run the sql thorugh guardrail middleware
        guardrail_result=self.guardrail.check(generated_sql)
        if not guardrail_result['approved']:
            return {
                "success": False,
                "needs_clarification": False,
                "sql": generated_sql,
                "explanation": generation_result.get("explanation"),
                "confidence_score": generation_result.get("confidence_score"),
                "approved": False,
                "blocked_reason": guardrail_result["blocked_reason"],
                "data": [],
                "columns": [],
                "row_count": 0,
                "execution_time_ms": 0,
                "error": f"Query blocked: {guardrail_result['blocked_reason']}"
            }

        # Get the final query from the guardrail result
        final_sql=guardrail_result['final_query']
        
        # Execute the approve SQL safely 
        execution_result=self.executor.execute(final_sql)

        # Apply hallucination verifiers to the execution result
        # 1- backtranslation verification
        logger.info('Running back-translation verification')
        back_translation_result=self.backtranslation_verifier.verify(user_question,final_sql)

        # 2- Result Sanity Checking
        logger.info('Running result sanity checks')
        sanity_result=self.result_sanity_checker.check(execution_result['data'],execution_result['columns'])

        # 3- Multi-query validation
        logger.info('Running Multi Query Validation')
        multi_query_result=self.multi_query_validator.validate(user_question,final_sql,self.schema)

        # 4- Confidence scoring
        logger.info('computing confidence score')
        confidence_result=self.confidence_scorer.compute(llm_confidence=generation_result.get('confidence_score',0.5),
        back_translation_result=back_translation_result, sanity_result=sanity_result,multi_query_result=multi_query_result)







        # Combining responses
        return{
            'success':execution_result['success'],
            'needs_clarification':False,

            #SQL Generation
            'sql': final_sql,
            'explanation': generation_result.get('explanation'),
            'query_type':generation_result.get('query_type'),
            'tables_used':generation_result.get('tables_used',[]),

            # Guardrails
            'approved':True,
            'blocked_reason': None,

            #Execution results
            'data':execution_result['data'],
            'columns':execution_result['columns'],
            'row_count':execution_result['row_count'],
            'execution_time_ms':execution_result['execution_time_ms'],

            # Halucination detection
            'hallucination':{
                'back_translation':back_translation_result,
                'sanity_check':sanity_result,
                'multi_query':{
                    'agree':multi_query_result['agree'],
                    'agreement_score':multi_query_result['agreement_score'],
                    'explanation':multi_query_result['explanation']
                }
            },
            'confidence':confidence_result,
            'error':execution_result.get('error')

        }




if __name__ == "__main__":

    # Test QueryExecutor directly
    executor = QueryExecutor()

    print("Testing database connection...")
    if executor.test_connection():
        print("Connection successful\n")
    else:
        print("Connection failed — check your READONLY_DATABASE_URL in .env")
        exit(1)

    test_queries = [
        "SELECT * FROM customers LIMIT 5",
        "SELECT status, COUNT(*) as count FROM orders GROUP BY status",
        "DELETE FROM orders WHERE order_id = 999",
    ]

    for query in test_queries:
        print(f"Query: {query[:60]}...")
        print("-" * 50)
        result = executor.execute(query)

        if result["success"]:
            print(f"Success — {result['row_count']} rows in {result['execution_time_ms']}ms")
            print(f"Columns: {result['columns']}")
            for row in result["data"]:
                print(f"  {row}")
        else:
            print(f"Failed — {result['error']}")
        print()

    # Test full pipeline
    print("\n" + "=" * 60)
    print("TESTING FULL EXECUTION PIPELINE")
    print("=" * 60)

    pipeline = ExecutionPipeline()

    test_questions = [
        "How many orders are pending?",
        "Which customers have spent the most money?",
        "show me revenue",
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        print("-" * 50)
        result = pipeline.run(question)

        if result.get("needs_clarification"):
            print(f"Needs clarification: {result['message'][:100]}...")
        elif result["success"]:
            print(f"SQL: {result['sql']}")
            print(f"Explanation: {result['explanation']}")
            print(f"Confidence score: {result['confidence']['final_score']}")
            print(f"Confidence label: {result['confidence']['confidence_label']}")
            print(f"Recommendation: {result['confidence']['recommendation']}")
            print(f"Rows returned: {result['row_count']}")
            print(f"Execution time: {result['execution_time_ms']}")
            print(f"Data: {result['data']}")
        else:
            print(f"Failed: {result['error']}")


            
                    





        
