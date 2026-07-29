'''FastAPI application that exposes the text to sql to REST endpoints'''

import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict,Any,List,Optional

import time
import uuid
import json
import os

# pyrefly: ignore [missing-import]
from logger import get_logger
# pyrefly: ignore [missing-import]
from executor import ExecutionPipeline
# pyrefly: ignore [missing-import]
from schema_extractor import SchemaExtractor

logger=get_logger(__name__)

app= FastAPI(
    title='Text-to-SQL App',
    description=('Natural Language to SQL Pipeline guardrails and hallucination detection'),
    version='1.0.0'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question:str
    session_id:Optional[str] = None # For tracking the conversation history

class FeedbackRequest(BaseModel):
    '''Defines a feedback payload when user marks a result correct incorrect i.e feedback loop'''
    query_id:str
    question:str
    sql:str
    is_correct:bool
    feedback_note:Optional[str]=None

# In momery query history
query_history:List[Dict[str,Any]] =[]

# Pipeline Initialization
logger.info('Initializing execution pipeline')
pipeline=ExecutionPipeline()
schema_extractor=SchemaExtractor()
logger.info('Pipiline initalized successfully')

# Endpoints
@app.get('/health')
def health_checkup()->Dict[str,Any]:
    '''Simple health checkup'''
    logger.info('Health checkup requested')
    # Test Database Connection
    db_healthy=pipeline.executor.test_connection()

    return{
        'status':'Healthy' if db_healthy else 'Degraded',
        'database': 'Connected' if db_healthy else 'Disconnected',
        'pipeline':'ready',
        'version':'1.0.0'
    }

@app.get('/v1/schema')
def get_schema()->Dict[str,Any]:
    'This return the database schema'

    logger.info('Database Schema Requested')
    try:
        schema=schema_extractor.extract_full_schema()
        return{
            'success':True,
            'schema':schema
        }
    except Exception as e:
        logger.error('Schema extraction failed',{str(e)})
        raise HTTPException(status_code=500,detail=f'Failed to extract schema: {str(e)}')
    
@app.get('/v1/history')
def get_history(Limit: int=10)->Dict[str,Any]:
    '''Return past queries for the session'''
    logger.info('History requested for last {Limit} queries')
    # Return the most recent first
    recent=list(reversed(query_history[-Limit:]))
    return{
        'success':True,
        'count':len(recent),
        'history':recent,
    }

@app.post('/v1/query')
def process_query(request:QueryRequest)->Dict[str,Any]:
    '''Processes the natural language question
    Thiss return the complete pipeline including SQL,data,confidence score, 
     hallucination detection,result and any warnings'''

    logger.info(f'Query revceived: {request.question[:30]}...')

    # Record start time for API response call
    start_time=time.time()

    try:
        # Run the complete pipeline
        result=pipeline.run(request.question)

        #Calcualte total response time 
        total_time_ms=round((time.time()-start_time)*1000,2)

        # generate a unique ID for this query
        query_id=str(uuid.uuid4())

        # Store in history if not a clarification request
        if not result.get('needs_clarification'):
            history_entry={
                'query_id':query_id,
                'question':request.question,
                'sql':result.get('sql'),
                'success': result.get('success'),
                'row_count':result.get('row_count'),
                'confidence_score':result.get('confidence',{}).get('final_score'),
                'confidence_label':result.get('confidence',{}).get('confidence_label'),
                'total_time_ms':total_time_ms,
                'timestamp':time.strftime("%Y-%m-%d %H:%M:%S")

            }
            query_history.append(history_entry)
            logger.info(f'Query Completed - confidence: {history_entry['confidence_score']}, time:{total_time_ms}ms')

            # Adding query id and total time to the result
        result['query_id']=query_id
        result['total_time_ms']=total_time_ms

        return result
    except Exception as e:
        logger.error(f'Pipeline error: {str(e)}')
        raise HTTPException(status_code=500,detail=f'Pipeline error: {str(e)}')

def append_to_json_file(filepath:str,entry:Dict[str,Any])->None:
    '''Appends a new entry to JSON file that stores a list of records'''
    # Temporary debug - remove after fixing
    print(f"DEBUG: Trying to write to: {filepath}")
    print(f"DEBUG: Directory exists: {os.path.exists(os.path.dirname(filepath))}")
    os.makedirs(os.path.dirname(filepath),exist_ok=True)
    # Reading existing data
    existing=[]
    if os.path.exists(filepath):
        try:
            with open(filepath,'r') as f:
                existing=json.load(f)
        except (json.JSONDecodeError,IOError):
            existing=[]
        
    # append the new entry and write back
    existing.append(entry)
    with open(filepath,'w') as f:
        json.dump(existing,f,indent=True,default=str)

    logger.info(f'Entry saved to {filepath} ({len(existing)}) total entries')


@app.post('/v1/feedback')
def submit_feedback(request: FeedbackRequest)-> Dict[str,Any]:
    '''Accepts user feedback on query results'''
    logger.info(f'Feedback received for query {request.query_id}: {'correct' if request.is_correct else 'incorrect'}')

    # Feedback Entry
    feedback_entry={
        'query_id':request.query_id,
        'question':request.question,
        'sql':request.sql,
        'is_correct': request.is_correct,
        'feedback_note':request.feedback_note,
        'timestamp':time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # update in memory history:
    for entry in query_history:
        if entry['query_id']==request.query_id:
            entry['feedback']={
                'is_correct':request.is_correct,
                'feedback_note':request.feedback_note
            }
            break
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    feedback_file = os.path.join(BASE_DIR, "evals", "feedback.json")
    correct_file = os.path.join(BASE_DIR, "evals", "correct_examples.json")

    # Save to feedback.json(all feedback)
    append_to_json_file(feedback_file, feedback_entry)

    if request.is_correct:
        correct_entry={
            'question':request.question,
            'sql': request.sql,
            'timestamp': feedback_entry['timestamp']
        }

        append_to_json_file(correct_file,correct_entry)
        logger.info(f'Correct example saved with all future correct SQL generation')
    else:
        logger.warning(f'Incorrect result flaged, added to test cases for eval suite')
    
    return{
        'success':True,
        'message':'Feedback recorded and saved',
        'query_id':request.query_id,
        'is_correct':request.is_correct,
        'saved_to_disk':True
    }

    
        

    



        





