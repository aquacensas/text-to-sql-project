'''
Here we convert the structured schema dict (from the schema_extractor.py) into a formated prompt string
that uses LLM to generate SQL queries i.e
- It takes the schema dictionary from schema_extractor.pyand arranges it into a neatly formatted prompt that 
OpenAI can read and understand to write SQL.

The Pormpt has 3 sections:
1. Schema Section - table, columns, primary keys, secondary keys, sample values
2. Few-Shot Section - example question -> SQL pairs fro this specific schema 
3. Question Section - the actual user question that the LLM must answer 

Reason for this structure:
LLM perform significantly when they have:
1. Explicit schema context (they dont guesss column name)
2. Examples of explicit output format (few shot learning)
3. A clear, unambiguious instructions at the end
'''

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------
# These are hardcoded question→SQL pairs specific to the e-commerce schema.
# They teach the LLM:
#   - The expected output format (just the SQL, no explanation)
#   - How to write JOINs across our specific tables
#   - How to handle aggregations, filters, and date ranges
#   - The exact column and table names to use
#
# Reason for 5 examples?
# Research on few-shot prompting shows diminishing returns after 5-8 examples.
# We pick 5 that cover the most common query patterns in this schema:
# simple lookup, aggregation, JOIN, filtered aggregation, multi-table JOIN.

from typing import Dict, Any
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)

FEW_SHOT_EXAMPLES = [
    {
        "question": "How many customers do we have?",
        "sql": "SELECT COUNT(*) AS total_customers FROM customers;"
    },
    {
        "question": "What are the top 5 most expensive products?",
        "sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 5;"
    },
    {
        "question": "Show me all completed orders with customer names",
        "sql": (
            "SELECT c.name AS customer_name, o.order_id, o.total_amount, o.order_date "
            "FROM orders o "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "WHERE o.status = 'completed' "
            "ORDER BY o.order_date DESC;"
        )
    },
    {
        "question": "What is the total revenue by product category?",
        "sql": (
            "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS total_revenue "
            "FROM order_items oi "
            "JOIN products p ON oi.product_id = p.product_id "
            "JOIN orders o ON oi.order_id = o.order_id "
            "WHERE o.status = 'completed' "
            "GROUP BY p.category "
            "ORDER BY total_revenue DESC;"
        )
    },
    {
        "question": "Which customers have placed more than one order?",
        "sql": (
            "SELECT c.name, COUNT(o.order_id) AS order_count "
            "FROM customers c "
            "JOIN orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.customer_id, c.name "
            "HAVING COUNT(o.order_id) > 1 "
            "ORDER BY order_count DESC;"
        )
    }
]

class PromptBuilder:
    
    def __init__(self, schema:Dict[str,Any]):
        self.schema=schema
    
    def format_schema_section(self):
        '''Converts the raw shcema dict into human redable text.'''
        lines=[]
        lines.append("=== DATABASE SCHEMA ===\n")
        
        for table_name, table_info in self.schema['tables'].items():
            lines.append(f'table:{table_name}')

            lines.append(' COLUMNS:')
            for col in table_info['columns']:
                col_line=f'   - {col['name']} ({col['type']})'

                if col['name'] in table_info.get('primary_keys',[]):
                    col_line+=' [PRIMARY KEY]'
                if not col['nullable']:
                    col_line+=" NOT NULL"
                
                lines.append(col_line)
            
            foreign_keys = table_info.get('foreign_keys', [])
            if foreign_keys:
                lines.append(" FOREIGN KEYS:")
                for fk in foreign_keys:
                    local_cols=fk['constrained_columns'][0]
                    ref_table=fk['referred_table']
                    ref_col=fk['referred_columns'][0]
                    lines.append(f'   {local_cols} -> {ref_table}.{ref_col}')
            
            sample_values=table_info.get('sample_values',{})
            if sample_values:
                lines.append(" SAMPLE VALUES:")
                for col_name,values in sample_values.items():
                    values_str = ", ".join(str(v) for v in values)
                    lines.append(f"    - {col_name}: {values_str}")
                lines.append("")

        return "\n".join(lines)
    
    def format_few_shot_section(self)->str:
        '''Formats FEW SHOT EXAMPLES into a readable text block'''
        lines=[]
        lines.append("=== EXAMPLES ===\n")

        for i, example in enumerate(FEW_SHOT_EXAMPLES,1):
            lines.append(f"Example {i}:")
            lines.append(f"Question: {example['question']}")
            lines.append(f"SQL:\n{example['sql']}")
            lines.append("")
        
        return "\n".join(lines)

    def build_prompt(self, user_question:str)->str:
        '''This assembles all the 3 sections, this is the method the app calls'''
        logger.info(f"Building prompt for: {user_question[:50]}...")
        logger.info("Prompt built successfully")
        schema_section=self.format_schema_section()
        few_shot_section=self.format_few_shot_section()

        prompt=f"""{schema_section}

        {few_shot_section}
        === YOUR TASK ===

        You are a SQL expert. Using ONLY the tables and columns defined in the schema above,
        write a PostgreSQL query that answers the following question.

        Rules:
        - Use ONLY table and column names that exist in the schema above
        - Always use table aliases for clarity when joining multiple tables
        - Add LIMIT 100 if the query could return many rows
        - Return ONLY the SQL query, no explanation, no markdown, no backticks

        Question: {user_question}

        SQL:    
        """
        return prompt


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    from schema_extractor import SchemaExtractor

    extractor=SchemaExtractor()
    schema=extractor.extract_full_schema()

    builder=PromptBuilder(schema)
    prompt=builder.build_prompt("Which customer spent most money in total?")

    print(prompt)
    
    

        
        

                


                
