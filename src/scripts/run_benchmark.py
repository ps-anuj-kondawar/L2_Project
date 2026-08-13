import os
import json
import asyncio
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.agents.supervisor import run_supervisor

async def run_benchmark():
    dataset_path = "benchmark_dataset.jsonl"
    
    if not os.path.exists(dataset_path):
        print(f"Dataset not found at {dataset_path}")
        return

    # 1. Load dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    scenarios = [json.loads(line) for line in lines if line.strip()]
    
    questions = []
    answers = []
    contexts = []
    
    print(f"Running benchmark on {len(scenarios)} scenarios...")
    
    actual_statuses = []
    expected_statuses = []

    # 2. Run supervisor for each scenario
    for i, scenario in enumerate(scenarios):
        user_input = scenario["user_input"]
        expected = scenario.get("expected_status", "UNKNOWN")
        expected_statuses.append(expected)
        print(f"\nEvaluating [{i+1}/{len(scenarios)}]: {user_input}")
        
        result = await run_supervisor(user_input, intent="audit")
        actual = result.compliance_report.overall_approval_status
        actual_statuses.append(actual)
        
        # We need strings for Ragas evaluation
        questions.append(user_input)
        answers.append(result.compliance_report.summary)
        
        # Build context from the RAG citations
        scenario_contexts = []
        for flag in result.compliance_report.chemical_flags:
            if flag.source_citation:
                scenario_contexts.append(flag.source_citation)
        
        # Ragas requires context as list of strings per question
        contexts.append(scenario_contexts if scenario_contexts else ["No context retrieved"])
        
        match_str = "MATCH" if actual == expected else "MISMATCH"
        print(f"Status: {actual} (Expected: {expected}) [{match_str}]")

    correct_count = sum(1 for a, e in zip(actual_statuses, expected_statuses) if a == e)
    verdict_accuracy = correct_count / len(scenarios) if scenarios else 0.0
    print(f"\n=== Overall Verdict Accuracy: {verdict_accuracy:.1%} ({correct_count}/{len(scenarios)}) ===")

    # 3. Setup Gemini for Ragas
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    
    # 4. Create Ragas Dataset
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
    }
    dataset = Dataset.from_dict(data)

    # 5. Evaluate using Ragas
    print("\nRunning Ragas Evaluation with Gemini...")
    metrics = [faithfulness, answer_relevancy]
    
    try:
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
        )
        
        print("\n=== Ragas Benchmark Results ===")
        print(results)
        
        try:
            ragas_dict = results.to_pandas().to_dict(orient="records")
        except Exception:
            ragas_dict = str(results)

        summary_output = {
            "verdict_accuracy": verdict_accuracy,
            "correct_count": correct_count,
            "total_scenarios": len(scenarios),
            "per_scenario": [
                {"input": q, "expected": e, "actual": a, "match": a == e}
                for q, e, a in zip(questions, expected_statuses, actual_statuses)
            ],
            "ragas_metrics": ragas_dict,
        }
        
        with open("benchmark_results.json", "w", encoding="utf-8") as f:
            json.dump(summary_output, f, indent=4, default=str)
            
        print("\nBenchmark results saved to benchmark_results.json")
    except Exception as e:
        print(f"Ragas evaluation failed: {e}")
        summary_output = {
            "verdict_accuracy": verdict_accuracy,
            "correct_count": correct_count,
            "total_scenarios": len(scenarios),
            "per_scenario": [
                {"input": q, "expected": e, "actual": a, "match": a == e}
                for q, e, a in zip(questions, expected_statuses, actual_statuses)
            ],
            "ragas_metrics": None,
            "ragas_error": str(e),
        }
        with open("benchmark_results.json", "w", encoding="utf-8") as f:
            json.dump(summary_output, f, indent=4, default=str)
        print("\nPartial benchmark results saved to benchmark_results.json")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
