import os 
import time 
import pandas as pd 
from sqlalchemy import create_engine,text
from typing import Dict,Any
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from logger import get_logger

load_dotenv()
logger=get_logger(__name__)
# Here we use the READONLY database URL not the admin URL
READONLY_DATABASE_URL=os.getenv("READONLY_DATABASE_URL","postgresql://readonly_user:password@localhost/ecommerce_db")

class QueryExecutor:
    
    def __init__(self):
        '''Creates a database engine using the read-only user credentials'''
        self.engine=create_engine(READONLY_DATABASE_URL)
    
    def execute(self,sql:str)-> Dict[str,Any]:
        '''Executes the SQL query inside a read-only transaction.
        parameter : sql -> Guardrail-checked SQL Query'''

        # Records the starttime so we can measure the execution duration
        logger.info(f"Executing SQL: {sql[:80]}...")
        start_time=time.time()
        
        try:
            # Open a connection to the database using readonly_user
            with self.engine.connect() as conn:
                # Begin a read only transaction
                conn.execute(text('SET TRANSACTION READ ONLY'))

                # Execute the actual query 
                result=conn.execute(text(sql))

                # Loading the result into dataframe
                df=pd.DataFrame(result.fetchall(),columns=list(result.keys()))

                conn.rollback()

                # Calculate the execution time in mili sec
                execution_time_ms=round((time.time()-start_time)*1000,2)

                #converting the df to list of dicts
                data=df.to_dict(orient='records')
                
                logger.info(f"Query successful — {len(df)} rows in {execution_time_ms}ms")

                return {
                    'success':True,
                    'data': data,
                    'columns':list(df.columns),
                    'row_count':len(df),
                    'execution_time_ms':execution_time_ms,
                    'error':None
                }


        except Exception as e:
            # Calculating the execution time even for the failed queries
            execution_time_ms=round((time.time()-start_time)*1000,2)
            logger.error(f"Query execution failed: {str(e)}")

            # Returning a structed error response
            return{
                'success':False,
                "data": [],
                'columns':[],
                'row_count':0,
                'execution_time_ms':execution_time_ms,
                'error':str(e)
            }
    
    def test_connection(self)->bool:
        '''Test if the readonly connection works'''
        logger.info("Testing database connection...")
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return True

        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            return False