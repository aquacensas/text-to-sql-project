'''
Introspects a PostgreSQL database using SQLAlchemy's inspect API.
Produces a structured representation of:
- Tables and columns with types
- Primary Key
- Foreign Key relationship
- Sample Value for low Cardinality (categorical) columns 
This structured schema becomes the grouding context for the LLM's SQL Generation
without it the model would be guessing the table/column names, which is the #1 source of 
## Halucinated ## SQL

'''

from sqlalchemy import create_engine, inspect, text
from typing import List, Dict, Any
import os 
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)

load_dotenv()

DATABASE_URL=os.getenv('DATABASE_URL', 'postgresql://localhost/ecommerce_db')

class SchemaExtractor:
    def __init__(self, database_url:str=DATABASE_URL):
        self.engine=create_engine(database_url)
        self.inspector=inspect(self.engine)

    def get_table(self)->List[str]:
        """Returns all the table name in the public schema"""
        return self.inspector.get_table_names()

    def get_columns(self, table_name:str) -> List[Dict[str,Any]]:
        """Returns columns Metadata: name, type, nullable, default."""
        columns = self.inspector.get_columns(table_name)
        return [
            {
            'name':col['name'],
            'type':str(col['type']),
            'nullable':col['nullable'],
            'default':col['default'] if col['default'] is not None else None,
            }
            for col in columns
        ]

    def get_primary_keys(self, table_name: str) -> List[str]:
        pk_constraint = self.inspector.get_pk_constraint(table_name)
        return pk_constraint.get("constrained_columns", [])
        #if a table somehow has no primary key, this returns an empty list instead of crashing with a KeyError.

    def get_foreign_keys(self, table_name:str)-> List[dict[str, Any]]:
        '''Returns foreign Key relationship'''
        fks=self.inspector.get_foreign_keys(table_name)
        return [
            {
                'constrained_columns': fk['constrained_columns'],
                'referred_table': fk['referred_table'],
                'referred_columns': fk['referred_columns']
            } 
            for fk in fks
        ]

    def get_sample_value(self, table_name:str, column_name:str, limit:int =5)->List[Any]:
        """Retuns distinct values for columns"""
        query=text(
            f'SELECT DISTINCT "{column_name}" FROM "{table_name}" '
            f'WHERE "{column_name}" IS NOT NULL LIMIT :limit'
        )

        with self.engine.connect() as conn:
            result=conn.execute(query,{'limit':limit})
            return[row[0] for row in result]

    def is_categorical(self, table_name:str, column_name:str, sample_size: int=100)-> bool:
        '''Heuristic: a column is categorical if it has <= 10 distinct columns 
            in a sample of 100 rows'''

        query=text(
            f'SELECT COUNT(DISTINCT "{column_name}") FROM '
            f'(SELECT "{column_name}" FROM "{table_name}" LIMIT :sample_size) AS sub'   
        )

        with self.engine.connect() as conn:
            distinct_count=conn.execute(query,{'sample_size':sample_size}).scalar()
        return distinct_count is not None and distinct_count<10

    def extract_full_schema(self)->Dict[str, Any]:
        """Combines all the functions above into one whole schema"""
        logger.info("Starting schema extraction")

        schema={'tables':{}}
        for table_name in self.get_table():
            columns=self.get_columns(table_name)
            primary_keys=self.get_primary_keys(table_name)
            foreign_keys=self.get_foreign_keys(table_name)

            sample_values={}

            for col in columns:
                col_name=col['name']
                skip_columns={'email','name','created_at','description'}
                if col_name in skip_columns:
                    continue
                if col['type'].upper().startswith(('VARCHAR','CHARACTER','TEXT')):
                    if self.is_categorical(table_name,col_name):
                        sample_values[col_name]=self.get_sample_value(table_name,col_name)
            
            schema['tables'][table_name] = {
                    'columns': columns,
                    'primary_keys': primary_keys,
                    'foreign_keys': foreign_keys,
                    'sample_values': sample_values
        
}
        logger.info(f"Schema extraction complete. Tables: {list(schema['tables'].keys())}")


        return schema

if __name__ == "__main__":
    extractor = SchemaExtractor()
    import json
    print(json.dumps(extractor.extract_full_schema(), indent=2))

    

    