'''Inspect every SQL query before it reaches the database and either:
- Aprroves it (passes thorugh unchanged)
- Modifies it (Adds LIMIT if missing)
- Blocks it (return reason without executing)
'''

import sqlparse
import re
import sqlparse
from sqlparse.sql import Statement 
from typing import Dict, Any
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)

# Blocked Keywords

# Data Definition Keywords (DDL)
DDL_KEYWORDS={'CREATE','DROP','ALTER','TRUNCATE'}

# Data Manipulation Keywords (DML - Write Operations)
DML_WRITE_KEYWORDS={'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'REPLACE'}

# Combined both the keywords
BLOCKED_KEYWORDS= DDL_KEYWORDS | DML_WRITE_KEYWORDS

class GuardrailMiddleware:
    def __init__(self, max_rows: int=100, max_subquery_depth:int=2):
        self.max_rows=max_rows
        self.max_subquery_depth=max_subquery_depth
    
    def get_query_type(self,sql:str)->str:
        '''Extracts the first keyword from SQL to detemine its query type'''

        parsed=sqlparse.parse(sql)
        if not parsed:
            return 'UNKNOWN'

        statement=parsed[0]

        for token in statement.tokens:
            #Skip the whitespaces and new lines
            if token.is_whitespace:
                continue
                
            return token.value.upper()
        
        return 'UNKNOWN'
    
    def check_blocked_keyword(self,sql:str)->Dict[str,Any]:
        '''Checks if SQL contains any block DDL or DML write keywords'''
        query_type=self.get_query_type(sql)

        if query_type in BLOCKED_KEYWORDS:
            return {
                'approved':False,
                'final_query':sql,
                'blocked_reason': (
                    f'Query Type {query_type} is not allowed. ' 
                    f'Only SELECT queries are allowed '
                    f'blocked keywords are:{', '.join(sorted(BLOCKED_KEYWORDS))}'
                )
            }

        # If query is safe then return approval signal to continue checking
        return {
            'approved':True,
            'final_query':sql,
            'blocked_reasons': None
        }
    
    def check_subquery_depth(self,sql:str)->Dict[str,Any]:
        """"Checks for nested subqueries and limits depth to max_depth that is
             if the SQL has too many subqueries"""
        
        current_depth=0
        max_depth=0

        for char in sql:
            if char=='(':
                current_depth+=1
                # Update the max depth if current dept is bigger
                max_depth=max(max_depth,current_depth)
            elif char==')':
                current_depth-=1
            
        if max_depth > self.max_subquery_depth:
            return {
                "approved": False,
                "final_query": sql,
                "blocked_reason": (
                    f"Query has subquery depth of {max_depth}, "
                    f"which exceeds the maximum allowed depth of "
                    f"{self.max_subquery_depth}. "
                    f"Please simplify the query."
                )
            }
        return {
            'approved':True,
            'final_query':sql,
            'blocked_reason':None
        }

    def enforce_row_limit(self,sql:str)->str:
        '''Here we add a limit clause if subquery doesnt have that'''
        
        if not re.search(r'\bLIMIT\b',sql,re.IGNORECASE):
            sql=sql.rstrip(';').rstrip()
            sql=f'{sql} LIMIT {self.max_rows}'
        
        return sql
    
    def check(self,sql:str)->Dict[str,Any]:
        '''Here we run the sql through all the guardrials in order'''

        sql=sql.strip()

        # Checking Blocked Keyowords
        result=self.check_blocked_keyword(sql)
        if not result['approved']:
            logger.warning(f"Query blocked — {result['blocked_reason']}")
            return result

        # Checking the depth
        result=self.check_subquery_depth(sql)
        if not result['approved']:
            logger.warning(f"Query blocked — {result['blocked_reason']}")
            return result
        
        # Checking the row Limit
        final_query=self.enforce_row_limit(sql)

        # All passed returns
        logger.info("Query approved — passed all guardrail checks")
        return {
            "approved": True,
            "final_query": final_query,
            "blocked_reason": None
        }

if __name__ == "__main__":
    guardrail = GuardrailMiddleware()

    test_queries = [
        # Should pass
        "SELECT * FROM orders WHERE status = 'pending'",

        # Should pass + get LIMIT added
        "SELECT c.name, SUM(o.total_amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name",

        # Should be blocked - DELETE
        "DELETE FROM orders WHERE order_id = 1",

        # Should be blocked - DROP
        "DROP TABLE customers",

        # Should be blocked - UPDATE
        "UPDATE orders SET status = 'completed' WHERE order_id = 1",

        # Should be blocked - too deep
        "SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT * FROM orders)))",
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query[:60]}...")
        print("-" * 50)
        result = guardrail.check(query)
        print(f"Approved: {result['approved']}")
        if result['approved']:
            print(f"Final query: {result['final_query']}")
        else:
            print(f"Blocked reason: {result['blocked_reason']}")


        
        
            



        
