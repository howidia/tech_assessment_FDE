import json
import os
import cohere
import time
from typing import List, Dict
from tqdm import tqdm
from dotenv import load_dotenv

# Import your actual Agent stack
from src.tools.subscription_store import SubscriptionStore
from src.agents.subscription_data_assistant_agent import SubscriptionDataAssistantAgent
from src.agent_team import AgentTeam
from src.agents.task_planner_agent import TaskPlannerAgent
from config.agent_config import MODEL_ID

# Setup
load_dotenv()
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
MODEL_ID = MODEL_ID
JUDGE_MODEL_ID = MODEL_ID

class AgentEvaluator:
    def __init__(self, agent_factory, client):
        self.agent_factory = agent_factory
        self.client = client

    def run_evaluation(self, eval_file: str, output_file: str = "evaluation_report.md", replications: int = 3):
        # 1. Load Data
        with open(eval_file, 'r') as f:
            data = json.load(f)["data"]

        summary_results = []
        
        print(f"Starting Evaluation on {len(data)} test cases with {replications} replications each...")

        # 2. Main Loop
        for item in tqdm(data):
            question = item["question"]
            golden_answer = item["golden_answer"]
            criteria = item.get("evaluation_criteria", "N/A")
            
            total_correctness = 0
            total_quality = 0
            replication_details = []

            for i in range(replications):
                # FRESH Agent per run
                agent = self.agent_factory()
                
                # Run Agent
                try:
                    start_time = time.time()
                    actual_answer = self._safe_agent_run(agent, question)
                    duration = time.time() - start_time
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

        # 3. Generate Report
        self._save_report(summary_results, output_file, replications)

    def _safe_agent_run(self, agent, question):
        """Wrapper to handle 429s during the Agent's run as well"""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return agent.run(question)
            except Exception as e:
                if "429" in str(e) or "limit" in str(e).lower():
                    print(f"\n⏳ Rate limit hit during Agent Run. Sleeping for 61s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(61)
                    continue
                raise e
        return "Error: Agent Rate Limit Exceeded"

    def _judge_answer(self, question, golden, actual, criteria):
        """
        Judge with Retry Logic for 429 Errors.
        Returns: (correctness_score, quality_score, reasoning)
        """
        prompt = f"""
        You are an expert evaluator grading an AI Agent.
        
        QUESTION: {question}
        GOLDEN ANSWER: {golden}
        CRITERIA: {criteria}
        ACTUAL ANSWER: {actual}
        
        TASK:
        Assign two scores based on the CRITERIA:
        
        1. CORRECTNESS (0 or 1): 
           - 1 (Pass): The answer is factually correct and meets the core criteria.
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
                response = self.client.chat(
                    model=JUDGE_MODEL_ID,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                
                content = response.message.content[0].text
                # Robust JSON cleaning
                start = content.find('{')
                end = content.rfind('}') + 1
                data = json.loads(content[start:end])
                
                return data["correctness"], data["quality"], data["reasoning"]
            
            except Exception as e:
                # Check for Rate Limit Error
                if "429" in str(e) or "limit" in str(e).lower():
                    print(f"\n⏳ Rate limit hit during Judging. Sleeping for 61s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(61)
                    continue
                
                # If it's another error (like JSON parsing), return 0s
                return 0, 0, f"Judge Error: {str(e)}"
        
        return 0, 0, "Judge Rate Limit Exceeded"

    def _save_report(self, summaries: List[Dict], filename: str, replications: int):
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
                
                f.write("| Rep | Pass | Quality | Duration | Answer Snippet | Judge Reasoning |\n")
                f.write("|---|---|---|---|---|---|\n")
                for rep in item['details']:
                    rep_icon = "✅" if rep['correctness'] == 1 else "❌"
                    qual_stars = "⭐" * rep['quality']
                    short_ans = str(rep['answer']).replace("\n", " ")[:80] + "..."
                    f.write(f"| {rep['rep']} | {rep_icon} | {qual_stars} ({rep['quality']}) | {rep['duration_sec']}s | {short_ans} | {rep['reasoning']} |\n")
                f.write("\n---\n")
        
        print(f"\nEvaluation Complete! Report saved to {filename}")

# ==========================================
# BOOTSTRAPPER (Factory Pattern)
# ==========================================
def create_agent_stack():
    """
    Creates a fresh instance of the entire agent team.
    Crucial for evaluation to ensure no memory leaks between runs.
    """
    co = cohere.ClientV2(api_key=COHERE_API_KEY)
    
    # 1. Store
    store = SubscriptionStore("data/subscription_data.csv")
    
    # 2. Worker
    worker = SubscriptionDataAssistantAgent(
        client=co, 
        model_id=MODEL_ID, 
        tools_json=store.get_tool_schemas(), 
        functions_map=store.get_tools()
    )
    
    # 3. Team & Planner
    team = AgentTeam()
    team.register_agent("DataAnalyst", worker, "SQL Data Retrieval")
    planner = TaskPlannerAgent(client=co, team=team, model_id=MODEL_ID)
    
    return planner

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    if not COHERE_API_KEY:
        print("Error: COHERE_API_KEY not found in environment.")
        exit(1)

    co_client = cohere.ClientV2(api_key=COHERE_API_KEY)
    
    # Pass the FACTORY function, not the object
    evaluator = AgentEvaluator(create_agent_stack, co_client)
    
    # Run with 3 replications per question
    evaluator.run_evaluation("data/evaluation_data.json", replications=3)