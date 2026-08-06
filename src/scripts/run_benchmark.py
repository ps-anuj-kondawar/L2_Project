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
    
    # 2. Run supervisor for each scenario
    for i, scenario in enumerate(scenarios):
        user_input = scenario["user_input"]
        print(f"\nEvaluating [{i+1}/{len(scenarios)}]: {user_input}")
        
        result = await run_supervisor(user_input, intent="audit")
        
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
        
        print(f"Status: {result.compliance_report.overall_approval_status} (Expected: {scenario.get('expected_status')})")

    # 3. Setup Gemini for Ragas
    # Ragas uses Langchain interfaces
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    
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
        
        print("\n=== Benchmark Results ===")
        print(results)
        
        # Dump detailed results
        with open("benchmark_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4)
            
        print("\nBenchmark results saved to benchmark_results.json")
    except Exception as e:
        print(f"Ragas evaluation failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
