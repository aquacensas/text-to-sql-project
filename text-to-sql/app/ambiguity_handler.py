"""Detects when a user question is ambiguos that means it could map to multiple
valid SQL queries and returns a structured clarification request instead of guesing

Why does this exist?
Silently returning the wrong answer is worse than asking for clarification.
In a business context, a user might make a real decision based on wrong
data. This module catches ambiguous questions BEFORE they reach the LLM
and asks the user to specify exactly what they mean.
"""

from typing import Dict, Any, List, Optional
# pyrefly: ignore [missing-import]
from logger import get_logger
logger = get_logger(__name__)

AMBIGUOUS_TERMS: Dict[str, Any] = {
    "revenue": {
        "description": "Revenue can mean different things depending on context",
        "interpretations": [
            {
                "label": "Total Revenue",
                "description": "Single total revenue number across all completed orders",
                "example_sql": "SELECT SUM(total_amount) AS total_revenue FROM orders WHERE status = 'completed'",
                "refined_question": "What is the total revenue from all completed orders?"
            },
            {
                "label": "Revenue by Category",
                "description": "Revenue broken down by product category",
                "example_sql": "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.category",
                "refined_question": "What is the total revenue broken down by product category?"
            },
            {
                "label": "Revenue by Customer",
                "description": "Revenue broken down by individual customer",
                "example_sql": "SELECT c.name, SUM(o.total_amount) AS revenue FROM orders o JOIN customers c ON o.customer_id = c.customer_id GROUP BY c.customer_id, c.name",
                "refined_question": "What is the total revenue broken down by each customer?"
            }
        ]
    },
    "sales": {
        "description": "Sales can refer to order count or revenue amount",
        "interpretations": [
            {
                "label": "Sales Count",
                "description": "Number of orders placed",
                "example_sql": "SELECT COUNT(*) AS total_sales FROM orders WHERE status = 'completed'",
                "refined_question": "How many orders have been completed?"
            },
            {
                "label": "Sales Revenue",
                "description": "Total money earned from sales",
                "example_sql": "SELECT SUM(total_amount) AS total_sales_revenue FROM orders WHERE status = 'completed'",
                "refined_question": "What is the total revenue earned from completed orders?"
            },
            {
                "label": "Sales by Product",
                "description": "Number of units sold per product",
                "example_sql": "SELECT p.name, SUM(oi.quantity) AS units_sold FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_id, p.name",
                "refined_question": "How many units of each product have been sold?"
            }
        ]
    },
    "best": {
        "description": "Best can mean highest revenue, most orders, or highest rated",
        "interpretations": [
            {
                "label": "Best by Revenue",
                "description": "Highest revenue generated",
                "example_sql": "SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_id, p.name ORDER BY revenue DESC LIMIT 5",
                "refined_question": "Which products have generated the highest total revenue?"
            },
            {
                "label": "Best by Units Sold",
                "description": "Most units sold",
                "example_sql": "SELECT p.name, SUM(oi.quantity) AS units_sold FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_id, p.name ORDER BY units_sold DESC LIMIT 5",
                "refined_question": "Which products have sold the most units?"
            },
            {
                "label": "Best by Order Count",
                "description": "Appeared in the most orders",
                "example_sql": "SELECT p.name, COUNT(oi.order_id) AS order_count FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_id, p.name ORDER BY order_count DESC LIMIT 5",
                "refined_question": "Which products have appeared in the most orders?"
            }
        ]
    },
    "popular": {
        "description": "Popular can mean most ordered or most revenue",
        "interpretations": [
            {
                "label": "Popular by Order Frequency",
                "description": "Products ordered most frequently",
                "example_sql": "SELECT p.name, COUNT(oi.item_id) AS times_ordered FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_id, p.name ORDER BY times_ordered DESC LIMIT 5",
                "refined_question": "Which products have been ordered most frequently?"
            },
            {
                "label": "Popular by Revenue",
                "description": "Products generating most revenue",
                "example_sql": "SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_id, p.name ORDER BY revenue DESC LIMIT 5",
                "refined_question": "Which products have generated the most revenue?"
            }
        ]
    },
    "recent": {
        "description": "Recent could mean last 7 days, last 30 days, or last 3 months",
        "interpretations": [
            {
                "label": "Last 7 Days",
                "description": "Orders from the past week",
                "example_sql": "SELECT * FROM orders WHERE order_date >= NOW() - INTERVAL '7 days'",
                "refined_question": "Show me all orders from the last 7 days?"
            },
            {
                "label": "Last 30 Days",
                "description": "Orders from the past month",
                "example_sql": "SELECT * FROM orders WHERE order_date >= NOW() - INTERVAL '30 days'",
                "refined_question": "Show me all orders from the last 30 days?"
            },
            {
                "label": "Last 3 Months",
                "description": "Orders from the past quarter",
                "example_sql": "SELECT * FROM orders WHERE order_date >= NOW() - INTERVAL '3 months'",
                "refined_question": "Show me all orders from the last 3 months?"
            }
        ]
    }
}

class AmbiguityHandler:
    def __init__(self):
        '''Initializes the hadnler with the AMBIGUOS_TERMS dictionary'''
        self.ambiguous_terms = AMBIGUOUS_TERMS

    def detect_ambiguity(self,question: str)->Optional[str]:

        """Scans the user question for ambiguous terms
        Here we are handling one ambihuous term at a time to keep the UI simple. 
        If we flag every ambiguous term then the user would face confusion of choices
        One clarification at a time is more cleaner.
       """
       
        # How it works step by step:
        #1. Convert the question to lowercase for case-insensitive matching
        #2. Loop through every known ambiguous term
        #3. Check if that term appears as a word in the question
        #4. If found, return it immediately
        #5. If nothing found after all terms checked, return None"""

        question_lower=question.lower()

        revenue_context = {
            "completed", "category", "february", "january", "march",
            "april", "total", "monthly", "weekly", "daily", "q1", "q2",
            "q3", "q4", "2024", "2025", "per", "each", "by"
        }

        for term in self.ambiguous_terms:
            if f" {term} " in f" {question_lower} ":

                # Special handling for revenue — check if context makes it clear
                if term == "revenue":
                    question_words = set(question_lower.split())
                    if question_words & revenue_context:
                        # Context makes revenue specific enough
                        continue

                return term

        return None

    def generate_clarification(self,question:str,ambiguous_term:str)->Dict[str,Any]:
        """ Generates a structred clarification response for an ambiguous term
        How it works step by step:
        1. Look up the ambiguous term in our dictionary
        2. Pull out its interpretations list
        3. Build a numbered message string showing each option
        4. Return everything packaged as a clean dict """
        
        term_data = self.ambiguous_terms[ambiguous_term]
        interpretations=term_data['interpretations']

        # Build a numbered list of the interpretation options that is human readable
        options_text = "\n".join([
            f"{i+1}. {interp['label']}: {interp['description']}"
            for i, interp in enumerate(interpretations)
        ])

        # Assemble the full clarification message
        message=(
            f"Your question contains the ambiguous term '{ambiguous_term}'."
            f"{term_data['description']}.\n\n"
            f"Please choose one of the following interpretation options:\n{options_text}"
        )

        # Full Strucutred response
        return{
            'needs_clarification':True,
            'orignal_question':question,
            'ambiguous_term':ambiguous_term,
            'description':term_data['description'],
            'interpretation':interpretations,
            'message':message
        }

    def resolve_ambiguity(self,clarification_response:Dict[str,Any],chosen_index:int)->str:
        """Takes the interpretation from the user and gives a clarified question"""
        interpretations=clarification_response['interpretations']

        index=chosen_index-1
        if index<0 or index>=len(interpretations):
            index=0
        return interpretations[index]['refined_question']

    def check_and_handle(self,question:str)->Dict[str,Any]:
        logger.info(f"Checking ambiguity for: {question[:50]}...")
        ambiguous_term=self.detect_ambiguity(question)
        if ambiguous_term:
            logger.warning(f"Ambiguous term detected: '{ambiguous_term}'")
            return self.generate_clarification(question,ambiguous_term)
        
        logger.info("No ambiguity detected — proceeding to SQL generation")
            
        return {
            'needs_clarification':False,
            'question':question
            }

if __name__ == "__main__":
    handler = AmbiguityHandler()

    test_questions = [
        "show me revenue for this month",
        "what are the best products?",
        "how many customers do we have?",
        "show me recent orders",
        "what are the most popular products?"
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        print("-" * 50)
        result = handler.check_and_handle(question)

        if result["needs_clarification"]:
            print(result["message"])
        else:
            print("No ambiguity detected. Proceeding to SQL generation.")







        

        



        



        
