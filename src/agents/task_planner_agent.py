import cohere
import json
from typing import Optional

from src.agent_team import AgentTeam
from config.tools_config import TASK_PLANNER_TOOLS_JSON
from config.agent_config import TASK_PLANNER_SYSTEM_PROMPT

class TaskPlannerAgent:
    def __init__(
        self, 
        client: cohere.ClientV2, 
        team: AgentTeam, 
        model_id: str,
        system_prompt_template: str = TASK_PLANNER_SYSTEM_PROMPT, # Default to config
        debug_mode: bool = False
    ):
        self.client = client
        self.team = team
        self.model_id = model_id
        
        # Inject the dynamic manifest into the static template
        manifest = self.team.get_team_manifest()
        self.system_prompt = system_prompt_template.format(team_manifest=manifest)
        self.debug_mode = debug_mode
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def run(self, user_request: str) -> str:
        if self.debug_mode:
            print(f"\n[Planner] Received Request: {user_request}")
        self.messages.append({"role": "user", "content": user_request})

        step = 0
        while step < 15:
            # --- 1. Think ---
            response = self.client.chat(
                model=self.model_id,
                messages=self.messages,
                tools=TASK_PLANNER_TOOLS_JSON 
            )
            self.messages.append(response.message)

            # --- 2. Act ---
            if response.message.tool_calls:
                for tc in response.message.tool_calls:
                    tool_name = tc.function.name
                    args = json.loads(tc.function.arguments)

                    # Termination Case: This must be checked explicitly to break the loop
                    if tool_name == "terminate_workflow":
                        return args["final_report"]

                    # STANDARD CASE: Delegation
                    if tool_name == "delegate_task":
                        # We call the internal implementation
                        result = self._execute_delegation(
                            agent_name=args["agent_name"], 
                            task=args["task"]
                        )
                        self._submit_tool_output(tc.id, result)
                
                step += 1
            else:
                # If the model chatters without calling a tool, return that text
                return response.message.content[0].text
        
        return "Error: specific task planner max steps reached."

    def _execute_delegation(self, agent_name: str, task: str) -> str:
        """
        The concrete logic for the 'delegate_task' tool.
        """
        if self.debug_mode:
            print(f"  → [Planner] Delegating to '{agent_name}': {task}")
        
        try:
            # 1. Get the agent from the team registry
            worker = self.team.get_agent(agent_name)
            
            # 2. Run the agent (Blocking call)
            # The worker does its own thinking and returns a string
            worker_response = worker.run(task)
            
            # 3. Return the result to the Planner
            return f"Agent '{agent_name}' reported: {worker_response}"
            
        except ValueError:
            return f"Error: Agent '{agent_name}' does not exist. Check your team manifest."
        except Exception as e:
            return f"Error during delegation: {str(e)}"

    def _submit_tool_output(self, call_id: str, output: str):
        """Helper to format the tool output for Cohere"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": [{"type": "document", "document": {"data": json.dumps({"output": output})}}]
        })