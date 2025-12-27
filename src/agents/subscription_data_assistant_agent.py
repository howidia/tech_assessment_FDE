import json
from typing import List, Dict, Any, Callable
import cohere

from config.agent_config import SUBSCRIPTION_DATA_AGENT_SYSTEM_PROMPT


class SubscriptionDataAssistantAgent:
    def __init__(
        self, 
        client: cohere.ClientV2, 
        model_id: str, 
        tools_json: List[Dict[str, Any]], 
        functions_map: Dict[str, Callable],
        system_prompt: str = SUBSCRIPTION_DATA_AGENT_SYSTEM_PROMPT, 
        max_steps: int = 8,
        debug_mode: bool = False
    ):
        """
        A generic Cohere Tool-Use Agent.
        """
        self.client = client
        self.model = model_id
        self.system_prompt = system_prompt
        self.tools_json = tools_json
        self.functions_map = functions_map
        self.max_steps = max_steps
        self.debug_mode = debug_mode
        
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def run(self, user_query: str) -> str:
        """
        Executes the multi-step reasoning loop.
        """
        if self.debug_mode:
            print(f"\nUser: {user_query}")
        self.messages.append({"role": "user", "content": user_query})

        # 1. Loop with safety limit
        for step in range(self.max_steps):
            response = self.client.chat(
                model=self.model,
                messages=self.messages,
                tools=self.tools_json
            )

            # 2. Add Assistant's output to history
            self.messages.append(response.message)
            
            # 3. Check for Tool Calls
            if response.message.tool_calls:
                if self.debug_mode:
                    print(f" > Step {step+1}: Agent requested {len(response.message.tool_calls)} tool(s).")
                
                # Execute all requested tools
                for tool_call in response.message.tool_calls:
                    self._execute_tool(tool_call)
                
                # The loop continues automatically to the next iteration
            else:
                # 4. No tools called? The agent is done.
                final_answer = response.message.content[0].text
                if self.debug_mode:
                    print(f"Agent: {final_answer}\n")
                return final_answer

        return "Error: Maximum steps reached without a final answer."

    def _execute_tool(self, tool_call):
        """
        Executes tool, handles errors, and formats output for Cohere V2.
        """
        func_name = tool_call.function.name
        args_str = tool_call.function.arguments
        if self.debug_mode:
            print(f"   - Executing: {func_name} with arguments\n{json.loads(args_str)}")

        # A. Parse Arguments
        try:
            func_args = json.loads(args_str)
        except json.JSONDecodeError:
            self._append_tool_error(tool_call.id, f"Invalid JSON arguments: {args_str}")
            return

        # B. Check Existence
        if func_name not in self.functions_map:
            self._append_tool_error(tool_call.id, f"Tool '{func_name}' not found.")
            return

        # C. Run Function
        try:
            result = self.functions_map[func_name](**func_args)
        except Exception as e:
            self._append_tool_error(tool_call.id, f"Execution Error: {str(e)}")
            return

        # D. Normalize & Format (The concise part)
        # Ensure result is always a list for consistency
        data_list = result if isinstance(result, list) else [result]

        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": [
                {
                    "type": "document",
                    "document": {"data": json.dumps(item, default=str)}
                } 
                for item in data_list
            ]
        })

    def _append_tool_error(self, tool_call_id: str, error_msg: str):
        """Helper to report tool errors back to the LLM so it can self-correct."""
        if self.debug_mode:
            print(f"   - Error: {error_msg}")
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": [{
                "type": "document", 
                "document": {"data": json.dumps({"error": error_msg})}
            }]
        })
