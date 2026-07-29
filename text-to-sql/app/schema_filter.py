'''Filters the full database schema down to only the tables relavent to
    specific user question . 

Why does this exist?
For large databases with many tables, sending the entire schema in
every prompt wastes tokens and confuses the LLM with irrelevant
context. This filter keeps the prompt focused.

How does it work?
It uses a simple but effective keyword matching approach:
- Extract keywords from the user question
- Score each table by how many of its words match the question keywords
- Keep only tables above a relevance score threshold
- Always keep tables that are connected via foreign keys to relevant tables
'''
import re
from typing import Dict, Any, Set, List
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)

class SchemaFilter:
    def __init__(self, schema: Dict[str,Any],similarity_threshold:float=0.1):
        '''Stores the full schema and the threshold for relevance scoring.
           Storing threshold value in __init__ because that doesnt change between questions.
           storing it here means we dont have to pass it every time we call filter_schema.
        '''
        self.schema=schema
        self.similarity_threshold=similarity_threshold
    
    def extract_keywords(self,question:str)->Set[str]:
        """Extracts meaningful keywords from the user question.
        Parameters:
        Question: the raw user question string
        Return: Set of lowercased keywords with stopwords removed
        
        Why remove stop words?
        If we kept them, every table would match on words like "the" or "what"
        and the filtering would be useless. We only want domain-meaningful
        words like "customer", "product", "order", "revenue" etc."""

        stop_words = {
            "what", "which", "who", "how", "many", "much", "show",
            "me", "the", "a", "an", "is", "are", "was", "were",
            "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "can", "may", "might",
            "of", "in", "on", "at", "to", "for", "with", "by",
            "from", "and", "or", "but", "all", "most", "list",
            "get", "give", "find", "tell", "total", "number"
        }
        words=re.findall(r'[a-zA-Z]+',question.lower()) # Here we convert everthign to lowercase for case-sensitive matching
        return {word for word in words if word not in stop_words}

    def score_table(self,table_name:str,table_info:Dict[str,Any],keywords: Set[str])->float:

        '''Scores how relavent a table is to the user's questions keywords
        
        How scoring works:
        We build a set of "table words" — every word that appears in
        the table name or column names. Then we count how many of those
        words appear in the user's question keywords.'''

        table_words=set()

        # We split on underscores because table names like "order_items"
        # should contribute both "order" and "items" as separate words
        table_words.update(table_name.lower().split('_'))

        for col in table_info['columns']:
            col_words=col['name'].lower().split('_')
            table_words.update(col_words)
        
        matches= table_words & keywords  # The & operator on sets returns the intersection (words in both sets)

        # This returns count of the matching word as score
        return float(len(matches))

    def get_connected_tables(self, relavent_tables:Set[str])->Set[str]:
        '''Finds the tables that are connected via foreign key to already relavent tables
        
        How it works:
        For every table in the schema, we check its foreign keys.
        If a foreign key points TO a relevant table, we add this table too.
        If a foreign key points FROM a relevant table to another table,
        we add that other table too.
        This ensures we capture the full "neighborhood" of related tables.'''

        connected=set(relavent_tables) # we are using copy so we dont modify the exisiting set while iterating it

        for table_name, table_info in self.schema['tables'].items():
            foreign_keys=table_info.get('foreign_keys',[])

            for fk in foreign_keys:
                referred_table=fk['referred_table']

                # Case 1: this table has a FK pointing to a relevant table
                if referred_table in relavent_tables: 
                    connected.add(table_name)
                
                # Case 2: this table is already relevant and its FK
                # points to another table

                if table_name in relavent_tables:
                    connected.add(referred_table)

        return connected

    def filter_schema(self,question:str)->Dict[str,Any]:
        '''Main mehtod which filters the full schema only to the relavent tables
            Parameter: 
            question -> the users natural language question
            
            Returns -> A schema dict in the same format as the full schema but containing,
            only the tables that are relavent to the question.
            
            '''
        # 1) Extract meaninigful keywords from the question
        keywords=self.extract_keywords(question)
            
        # 2) Score every table 
        scores={}
        for table_name, table_info in self.schema['tables'].items():
            score=self.score_table(table_name, table_info, keywords)
            scores[table_name]=score

        # 3) Keep tables above the threshold
        # If NO tables score above threshold (very vague question),
        # fall back to including ALL tables — better to send too much
        # than to send nothing and get a hallucinated query

        relevant_tables={
            table_name for table_name,score in scores.items()
            if score >= self.similarity_threshold
        }

        # If nothing matched use all the tables
        if not relevant_tables:
            relevant_tables = set(self.schema['tables'].keys())
            
        # 4) Expand to include  foriegn keys connected 
        relevant_tables=self.get_connected_tables(relevant_tables)

        # 5) Returning the filter schema dictionary:
        filtered_schema={'tables':{}}
        for table_name in relevant_tables:
            filtered_schema['tables'][table_name] = self.schema['tables'][table_name]

        logger.info(f"Filtering schema for: {question[:50]}...")
        logger.info(f"Relevant tables identified: {list(relevant_tables)}")

        return filtered_schema

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    from schema_extractor import SchemaExtractor
    import json

    # Step 1: Get the full schema
    extractor = SchemaExtractor()
    schema = extractor.extract_full_schema()

    # Step 2: Create the filter
    schema_filter = SchemaFilter(schema)

    # Test with 3 different questions to see filtering in action
    test_questions = [
        "What are the top selling products by category?",
        "Which customers have placed the most orders?",
        "Show me all pending orders"
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        filtered = schema_filter.filter_schema(question)
        print(f"Tables included: {list(filtered['tables'].keys())}")


                

                
        


        
            
        

        


        
        

