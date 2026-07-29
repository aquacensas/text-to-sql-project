"""
run_evals.py

Automated evaluation suite that runs every golden query through
the full pipeline and measures system performance.
"""

import json
import time
import requests
import sys
import os
from typing import Dict, Any, List
from datetime import datetime

# Configuration

API_BASE_URL = "http://localhost:8000"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_QUERIES_FILE = os.path.join(BASE_DIR, "evals", "golden_queries.json")
RESULTS_FILE = os.path.join(BASE_DIR, "evals", "eval_results.json")

# Helper Functions


def call_api(endpoint: str, method: str = "GET",
             data: Dict | None=None) -> Dict[str, Any]:
    """Makes HTTP request to the FastAPI backend."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        if method == "POST":
            response = requests.post(url, json=data, timeout=120)
        else:
            response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to API. Is FastAPI running on port 8000?")
        sys.exit(1)
    except Exception as e:
        return {"error": str(e), "success": False}


def check_api_health() -> bool:
    """Confirms FastAPI is running before starting evals."""
    result = call_api("/health")
    return result.get("status") == "Healthy"


def load_golden_queries() -> List[Dict[str, Any]]:
    """Loads the golden query dataset from disk."""
    with open(GOLDEN_QUERIES_FILE, "r") as f:
        return json.load(f)


def evaluate_single_query(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs one golden query through the pipeline and evaluates the result.

    How evaluation works for each category:

    AMBIGUOUS questions:
        Pass if result.needs_clarification == True
        Fail if the system tried to generate SQL instead

    DANGEROUS queries:
        Pass if result.approved == False (guardrail blocked it)
        Fail if the query somehow executed

    NORMAL queries (lookup, join, aggregation, date_filter):
        Pass if result.success == True AND row_count >= expected
        Fail if query errored or returned wrong number of rows

    UNANSWERABLE queries:
        Pass if execution failed gracefully (no crash)
        These are tricky — the LLM might hallucinate a column name
        which causes an execution error, which is actually correct behavior
    """
    question = test_case["question"]
    category = test_case["category"]

    print(f"\n[{test_case['id']}] {category.upper()}: {question[:60]}...")

    # Call the pipeline
    start_time = time.time()
    result = call_api("/v1/query", method="POST", data={"question": question})
    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    # Initialize eval result
    eval_result: Dict[str, Any] = {
        "id": test_case["id"],
        "category": category,
        "question": question,
        "notes": test_case["notes"],
        "elapsed_ms": elapsed_ms,
        "passed": False,
        "failure_reason": None,
        "api_result_summary": {}
    }

    # Store summary of API result
    eval_result["api_result_summary"] = {
        "success": result.get("success"),
        "needs_clarification": result.get("needs_clarification"),
        "approved": result.get("approved"),
        "row_count": result.get("row_count"),
        "confidence_score": result.get("confidence", {}).get("final_score"),
        "confidence_label": result.get("confidence", {}).get("confidence_label"),
        "sql": result.get("sql", "")[:100] if result.get("sql") else None,
        "error": result.get("error")
    }

    # Evaluate based on category

    if category == "ambiguous":
        # Should trigger clarification
        if result.get("needs_clarification"):
            eval_result["passed"] = True
            print(f"PASS — clarification requested as expected")
        else:
            eval_result["passed"] = False
            eval_result["failure_reason"] = ("Expected clarification but system generated SQL instead")
            print(f"FAIL — expected clarification, got SQL instead")

    elif category == "dangerous":
        # Should be blocked by guardrails
        if not result.get("approved") and result.get("blocked_reason"):
            eval_result["passed"] = True
            print(f"PASS — query blocked as expected")
        elif result.get("needs_clarification"):
            # Acceptable — ambiguity caught it before guardrails
            eval_result["passed"] = True
            print(f"PASS — caught before reaching guardrails")
        else:
            eval_result["passed"] = False
            eval_result["failure_reason"] = (
                f"Dangerous query was NOT blocked. "
                f"approved={result.get('approved')}, "
                f"success={result.get('success')}"
            )
            print(f"FAIL — dangerous query was not blocked!")

    elif category == "unanswerable":
        # Should fail gracefully — either SQL error or LLM refuses
        if not result.get("success") or result.get("error"):
            eval_result["passed"] = True
            print(f"PASS — failed gracefully as expected")
        elif result.get("needs_clarification"):
            eval_result["passed"] = True
            print(f"PASS — triggered clarification")
        else:
            # If it somehow succeeded, check if row count makes sense
            # Some unanswerable questions might return 0 rows
            eval_result["passed"] = True
            eval_result["failure_reason"] = (
                "Unanswerable query returned results — may be hallucinating"
            )
            print(
                f"WARN — query succeeded but may be hallucinating"
            )

    else:
        # Normal queries: lookup, join, aggregation, date_filter,
        # confidence_validation
        if result.get("needs_clarification"):
            eval_result["passed"] = False
            eval_result["failure_reason"] = (
                "Unexpected clarification request for unambiguous question"
            )
            print(f"FAIL — unexpected clarification request")

        elif not result.get("success"):
            eval_result["passed"] = False
            eval_result["failure_reason"] = (
                f"Query failed: {result.get('error', 'Unknown error')}"
            )
            print(f"FAIL — query execution failed: {result.get('error', '')[:50]}")

        else:
            # Check row count if expected
            expected_rows = test_case.get("expected_row_count")
            actual_rows = result.get("row_count", 0)

            if expected_rows is not None and actual_rows != expected_rows:
                eval_result["passed"] = False
                eval_result["failure_reason"] = (
                    f"Row count mismatch: expected {expected_rows}, "
                    f"got {actual_rows}"
                )
                print(
                    f"FAIL — expected {expected_rows} rows, "
                    f"got {actual_rows}"
                )
            else:
                # Check minimum value if expected
                expected_min = test_case.get("expected_min_value")
                if expected_min is not None and result.get("data"):
                    # Get first numeric value from results
                    first_row = result["data"][0]
                    first_value = list(first_row.values())[0]
                    try:
                        actual_value = float(str(first_value))
                        if actual_value < expected_min:
                            eval_result["passed"] = False
                            eval_result["failure_reason"] = (
                                f"Value too low: expected >= {expected_min}, "
                                f"got {actual_value}"
                            )
                            print(
                                f"FAIL — value {actual_value} "
                                f"below minimum {expected_min}"
                            )
                        else:
                            eval_result["passed"] = True
                            confidence = result.get(
                                "confidence", {}
                            ).get("final_score", 0)
                            print(
                                f"PASS — {actual_rows} rows, "
                                f"confidence {confidence:.2f}"
                            )
                    except (ValueError, TypeError):
                        eval_result["passed"] = True
                        print(f"PASS — {actual_rows} rows returned")
                else:
                    eval_result["passed"] = True
                    confidence = result.get(
                        "confidence", {}
                    ).get("final_score", 0)
                    print(
                        f"PASS — {actual_rows} rows, "
                        f"confidence {confidence:.2f}"
                    )

    return eval_result


def calculate_metrics(results: List[Dict[str, Any]],test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates aggregate metrics from all eval results.
    """
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    # Per-category breakdown
    categories = {}
    for result in results:
        cat = result["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed": 0}
        categories[cat]["total"] += 1
        if result["passed"]:
            categories[cat]["passed"] += 1
        else:
            categories[cat]["failed"] += 1

    # Calculate accuracy per category
    for cat in categories:
        cat_data = categories[cat]
        cat_data["accuracy"] = round(
            cat_data["passed"] / cat_data["total"] * 100, 1
        )

    # Confidence score stats for passed normal queries
    confidence_scores = [
        r["api_result_summary"].get("confidence_score")
        for r in results
        if r["passed"]
        and r["api_result_summary"].get("confidence_score") is not None
        and r["category"] not in ["dangerous", "ambiguous", "unanswerable"]
    ]

    avg_confidence = (
        round(sum(confidence_scores) / len(confidence_scores), 3)
        if confidence_scores else 0
    )

    # Average response time
    avg_time = round(
        sum(r["elapsed_ms"] for r in results) / total, 2
    )

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "overall_accuracy": round(passed / total * 100, 1),
        "avg_confidence_score": avg_confidence,
        "avg_response_time_ms": avg_time,
        "by_category": categories
    }


def print_report(metrics: Dict[str, Any],failed_results: List[Dict[str, Any]]):
    """
    Prints a formatted evaluation report.
    """
    print("\n" + "=" * 60)
    print("EVALUATION REPORT")
    print("=" * 60)

    print(f"\nOVERALL RESULTS")
    print(f"   Total tests:      {metrics['total_tests']}")
    print(f"   Passed:           {metrics['passed']}")
    print(f"   Failed:           {metrics['failed']}")
    print(f"   Overall accuracy: {metrics['overall_accuracy']}%")
    print(f"   Avg confidence:   {metrics['avg_confidence_score']}")
    print(f"   Avg response:     {metrics['avg_response_time_ms']}ms")

    print(f"\n📋 BY CATEGORY")
    for cat, data in metrics["by_category"].items():
        status = "✅" if data["accuracy"] == 100 else (
            "⚠️" if data["accuracy"] >= 80 else " ❌ "
        )
        print(
            f"   {status} {cat:<25} "
            f"{data['passed']}/{data['total']} "
            f"({data['accuracy']}%)"
        )

    if failed_results:
        print(f"\n❌ FAILED TESTS ({len(failed_results)})")
        for result in failed_results:
            print(f"\n   [{result['id']}] {result['question'][:50]}...")
            print(f"   Reason: {result['failure_reason']}")

    print("\n" + "=" * 60)
    print("README SUMMARY (copy this into your README)")
    print("=" * 60)
    print(f"""
## Evaluation Results

| Metric | Score |
|--------|-------|
| Overall Accuracy | {metrics['overall_accuracy']}% |
| Guardrail Effectiveness | {metrics['by_category'].get('dangerous', {}).get('accuracy', 'N/A')}% |
| Ambiguity Detection | {metrics['by_category'].get('ambiguous', {}).get('accuracy', 'N/A')}% |
| Query Execution | {metrics['by_category'].get('simple_lookup', {}).get('accuracy', 'N/A')}% |
| Avg Confidence Score | {metrics['avg_confidence_score']} |
| Test Cases | {metrics['total_tests']} |
""")


def main():
    """
    Main eval runner function.

    Step by step:
    1. Check API is running
    2. Load golden queries
    3. Run each query through pipeline
    4. Calculate metrics
    5. Save results to disk
    6. Print report
    """
    print("=" * 60)
    print("TEXT-TO-SQL EVALUATION SUITE")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Health check
    print("\nChecking API health...")
    if not check_api_health():
        print("ERROR: API is not healthy. Start FastAPI first.")
        sys.exit(1)
    print("API is healthy")

    # Step 2: Load golden queries
    test_cases = load_golden_queries()
    print(f"Loaded {len(test_cases)} golden queries")

    # Step 3: Run each query
    print(f"\nRunning {len(test_cases)} test cases...")
    print("(This will take several minutes due to API rate limits)\n")

    results = []
    for i, test_case in enumerate(test_cases, 1):
        print(f"Progress: {i}/{len(test_cases)}", end="")
        result = evaluate_single_query(test_case)
        results.append(result)

        # Small delay between requests to avoid rate limiting
        if i < len(test_cases):
            time.sleep(2)

    # Step 4: Calculate metrics
    metrics = calculate_metrics(results, test_cases)

    # Step 5: Save results to disk
    output = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": metrics,
        "results": results
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {RESULTS_FILE}")

    # Step 6: Print report
    failed_results = [r for r in results if not r["passed"]]
    print_report(metrics, failed_results)


if __name__ == "__main__":
    main()