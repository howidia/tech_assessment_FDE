"""
Agent Evaluation Pipeline.

This script runs a comprehensive evaluation of the agent system against a
predefined test dataset (`evaluation_data.json`). It uses an "LLM-as-a-Judge"
approach to grade the agent's responses based on correctness and quality.

Key Features:
- Consistency Testing: Runs each question multiple times (replications) to measure stability.
- Dual Scoring: Assigns both a binary Pass/Fail score and a qualitative 1-5 score.
- Rate Limit Handling: Automatically pauses and retries on API rate limits.
- Markdown Reporting: Generates a detailed `evaluation_report.md` file.
"""

import json
import os
import cohere
import time
import pandas as pd
from typing import List, Dict
from tqdm import tqdm
from dotenv import load_dotenv

from src.tools.subscription_store import SubscriptionStore
from src.agent_team import AgentTeam
from src.agents import TaskPlannerAgent, SubscriptionDataAssistantAgent
from config.agent_config import MODEL_ID

# Setup
load_dotenv()
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
JUDGE_MODEL_ID = MODEL_ID  # Using the same model for judging

class AgentEvaluator:
    """
    Evaluator class that runs the agent against test cases and grades the results.
    """

    def __init__(self, agent_factory, client):
        """
        Initialize the evaluator.

        Args:
            agent_factory (Callable): A function that returns a new agent instance.
            client (cohere.ClientV2): The Cohere client for the judge model.
        """
        self.agent_factory = agent_factory
        self.client = client

    def run_evaluation(self, eval_file: str, output_file: str = "evaluation_report.md", replications: int = 3):
        """
        Run the full evaluation suite.

        Args:
            eval_file (str): Path to the JSON evaluation data.
            output_file (str): Path where the markdown report will be saved.
            replications (int): Number of times to run each question (consistency check).
        """
        # Load Data
        with open(eval_file, 'r') as f:
            data = json.load(f)["data"]

        summary_results = []
        
        print(f"Starting Evaluation on {len(data)} test cases with {replications} replications each...")

        # Main Loop
        for item in tqdm(data):
            question = item["question"]
            golden_answer = item["golden_answer"]
            criteria = item.get("evaluation_criteria", "N/A")
            
            total_correctness = 0
            total_quality = 0
            replication_details = []

            for i in range(replications):
                # New agent per run
                agent = self.agent_factory()
                
                # Run Agent
                try:
                    start_time = time.time()
                    actual_answer = self._safe_agent_run(agent, question)
                    duration = time.time() - start_time
                    # When api limit is reached, deduct 61 seconds that we froze for
                    if duration > 61: duration -= 61  
                except Exception as e:
                    actual_answer = f"ERROR: {str(e)}"
                    duration = 0

                # Judge Answer
                correctness, quality, reasoning = self._judge_answer(question, golden_answer, actual_answer, criteria)
                
                total_correctness += correctness
                total_quality += quality
                
                replication_details.append({
                    "rep": i + 1,
                    "answer": actual_answer,
                    "correctness": correctness,
                    "quality": quality,
                    "reasoning": reasoning,
                    "duration_sec": round(duration, 2)
                })
            
            # Calculate Averages
            avg_quality = total_quality / replications
            pass_rate = (total_correctness / replications) * 100
            is_stable = (pass_rate == 100)
            
            summary_results.append({
                "question": question,
                "golden_answer": golden_answer,
                "criteria": criteria,
                "pass_rate": pass_rate,
                "avg_quality": avg_quality,
                "is_stable": is_stable,
                "details": replication_details
            })

        # Generate Report
        self._save_report(summary_results, output_file, replications)

    def _safe_agent_run(self, agent, question):
        """
        Wrapper to execute agent run with 429 Rate Limit handling.

        Args:
            agent: The agent instance.
            question (str): The user query.

        Returns:
            str: The agent's response.
        """
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return agent.run(question)
            except Exception as e:
                if "You are using a Trial key, which is limited to" in str(e):
                    print(f"\n⏳ Rate limit hit during Agent Run. Sleeping for 61s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(61)
                    agent = self.agent_factory()
                    continue
                raise e
        return "Error: Agent Rate Limit Exceeded"

    def _judge_answer(self, question, golden, actual, criteria):
        """
        Judge the agent's answer using an LLM.

        Args:
            question (str): The test question.
            golden (str): The ground truth answer.
            actual (str): The agent's generated answer.
            criteria (str): Specific evaluation criteria.

        Returns:
            tuple: (correctness_int, quality_int, reasoning_str)
        """
        prompt = f"""
        You are an expert evaluator grading an AI Agent.
        
        QUESTION: {question}
        GOLDEN ANSWER: {golden}
        CRITERIA: {criteria}
        ACTUAL ANSWER: {actual}
        
        TASK:
        Assign two scores based on the CRITERIA & QUESTION:
        
        1. CORRECTNESS (0 or 1): 
           - 1 (Pass): The answer is factually correct and answers the core and basic Question only.
           - 0 (Fail): The answer is wrong, hallucinates, or refuses valid questions (false refusal).
        
        2. QUALITY (0 to 5):
           - 5: Perfect. Matches the Golden Answer in detail, tone, and formatting.
           - 4: Great. Correct info, minor style differences.
           - 3: Good. Correct info, but missing context or slightly verbose.
           - 1: Bare Minimum. Technically correct but very poor presentation (e.g. just a number).
           - 0: Incorrect. (If Correctness is 0, Quality must be 0).
        
        OUTPUT JSON ONLY:
        {{"correctness": <int>, "quality": <int>, "reasoning": "<string>"}}
        """
        
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                # Use Cohere-defined response schema to guarantee valid JSON
                response = self.client.chat(
                    model=JUDGE_MODEL_ID,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    response_format={
                        "type": "json_object",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "correctness": {"type": "integer"},
                                "quality": {"type": "integer"},
                                "reasoning": {"type": "string"}
                                },
                        "required": ["correctness", "quality", "reasoning"]
                        }
                    }
                )
                content = response.message.content[0].text
                # Robust JSON cleaning
                start = content.find('{')
                end = content.rfind('}') + 1
                data = json.loads(content[start:end])
                
                return data["correctness"], data["quality"], data["reasoning"]
            
            except Exception as e:
                # Check for Rate Limit Error
                if "You are using a Trial key, which is limited to" in str(e):
                    print(f"\n⏳ Rate limit hit during Judging. Sleeping for 61s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(61)
                    continue
                
                # If it's another error (like JSON parsing), return 0s
                return 0, 0, f"Judge Error: {str(e)}"
        
        return 0, 0, "Judge Rate Limit Exceeded"

    def _save_report(self, summaries: List[Dict], filename: str, replications: int):
        """
        Generate and save both a Markdown report and a raw CSV dataset of the evaluation results.

        Args:
            summaries (List[Dict]): The list of evaluation results.
            filename (str): The output file path (expected .md).
            replications (int): The number of replications used.
        """

        # Generate raw csv

        # json_normalize automatically unrolls the 'details' list
        # and repeats the 'meta' fields for every row.
        df = pd.json_normalize(
            summaries,
            record_path=['details'],
            meta=['question', 'golden_answer', 'criteria', 'pass_rate', 'avg_quality', 'is_stable']
        )

        # Rename the raw keys to professional schema
        df = df.rename(columns={
            'rep': 'replication_id',
            'answer': 'actual_answer',
            'reasoning': 'judge_reasoning',
            'correctness': 'score_correctness',
            'quality': 'score_quality',
            'duration_sec': 'duration_seconds',
            'pass_rate': 'agg_pass_rate',
            'avg_quality': 'agg_avg_quality'
        })

        # Reorder columns for readability
        # We must ensure all columns exist, so we select them explicitly
        column_order = [
            "question", "criteria", "golden_answer",
            "replication_id", "actual_answer", "judge_reasoning",
            "score_correctness", "score_quality", "duration_seconds",
            "agg_pass_rate", "agg_avg_quality", "is_stable"
        ]

        # Safe selection (in case a key is missing, though strictly it shouldn't be)
        df = df[column_order]

        # Save CSV
        csv_filename = filename.replace(".md", ".csv")
        try:
            df.to_csv(csv_filename, index=False)
            print(f"Raw evaluation data saved to {csv_filename}")
        except Exception as e:
            print(f"Error saving CSV: {e}")

        # Generate markdown report
        total_questions = len(summaries)
        perfect_stability = sum(1 for s in summaries if s['is_stable'])
        avg_quality = sum(s['avg_quality'] for s in summaries) / total_questions
        
        with open(filename, "w", encoding='utf-8') as f:
            f.write(f"# 🛡️ Agent Consistency & Quality Report\n\n")
            f.write(f"- **Total Questions:** {total_questions}\n")
            f.write(f"- **Replications per Question:** {replications}\n")
            f.write(f"- **Perfect Stability (100% Pass):** {perfect_stability}/{total_questions}\n")
            f.write(f"- **Average Quality Score:** {avg_quality:.2f} / 5.0\n\n")
            
            f.write("## Detailed Breakdown\n\n")
            
            for item in summaries:
                icon = "🟢" if item['is_stable'] else "kT" if item['pass_rate'] > 0 else "🔴"
                f.write(f"### {icon} {item['question']}\n")
                f.write(f"**Pass Rate:** {item['pass_rate']:.0f}% | **Avg Quality:** {item['avg_quality']:.1f}/5\n\n")
                f.write(f"**Criteria:** _{item['criteria']}_\n\n")
                
                f.write("| Rep | Pass | Quality | Duration | Answer | Judge Reasoning |\n")
                f.write("|---|---|---|---|---|---|\n")
                for rep in item['details']:
                    rep_icon = "✅" if rep['correctness'] == 1 else "❌"
                    qual_stars = "⭐" * rep['quality']
                    # Truncate answer slightly for table readability
                    short_ans = str(rep['answer']).replace("\n", " ")[:80] + "..."
                    f.write(f"| {rep['rep']} | {rep_icon} | {qual_stars} ({rep['quality']}) | {rep['duration_sec']}s | {short_ans} | {rep['reasoning']} |\n")
                f.write("\n---\n")
        
        print(f"\nEvaluation Complete! Report saved to {filename}")

def create_agent_stack():
    """
    Factory function to create a fresh instance of the Agent Team.

    Returns:
        TaskPlannerAgent: A ready-to-use planner instance connected to a fresh store.
    """
    co = cohere.ClientV2(api_key=COHERE_API_KEY)
    debug_mode = 'True' == os.environ.get("DEBUG_MODE", False)

    # Store
    store = SubscriptionStore("data/subscription_data.csv")
    
    # Worker
    worker = SubscriptionDataAssistantAgent(
        client=co, 
        model_id=MODEL_ID, 
        tools_json=store.get_tool_schemas(), 
        functions_map=store.get_tools(),
        debug_mode=debug_mode
    )
    
    # Team & Planner
    team = AgentTeam()
    team.register_agent("DataAnalyst", worker, "SQL Data Retrieval")
    planner = TaskPlannerAgent(
        client=co, 
        team=team, 
        model_id=MODEL_ID, 
        debug_mode=debug_mode
    )
    
    return planner

if __name__ == "__main__":
    if not COHERE_API_KEY:
        print("Error: COHERE_API_KEY not found in environment.")
        exit(1)

    # Create the output directory if it doesn't exist
    OUTPUT_DIR = "reports"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Define the full path for the report
    report_path = os.path.join(OUTPUT_DIR, "evaluation_report.md")

    co_client = cohere.ClientV2(api_key=COHERE_API_KEY)
    
    # Initialize Evaluator
    evaluator = AgentEvaluator(create_agent_stack, co_client)
    
    # Run with explicit output path
    print(f"Running evaluation... Results will be saved to {OUTPUT_DIR}/")
    evaluator.run_evaluation(
        eval_file="data/evaluation_data.json",
        output_file=report_path,
        replications=3
    )
