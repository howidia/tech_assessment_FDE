"""
Task Planner Agent Module.

This module defines the TaskPlannerAgent, which acts as the supervisor in a
hierarchical agent system. It decomposes complex user requests and delegates
sub-tasks to specific worker agents registered in the AgentTeam.
"""

import cohere
import json

from src.agent_team import AgentTeam
from config.tools_config import TASK_PLANNER_TOOLS_JSON
from config.agent_config import TASK_PLANNER_SYSTEM_PROMPT


class TaskPlannerAgent:
    """
    A supervisor agent that orchestrates workflows by delegating tasks.

    This agent does not execute data retrieval directly; instead, it uses
    available tools to route instructions to worker agents and aggregates
    their responses into a final report.
    """

    def __init__(
        self,
        client: cohere.ClientV2,
        team: AgentTeam,
        model_id: str,
        system_prompt_template: str = TASK_PLANNER_SYSTEM_PROMPT,  # Default to config
        debug_mode: bool = False
    ):
        """
        Initialize the TaskPlannerAgent.

        Args:
            client (cohere.ClientV2): The Cohere API client.
            team (AgentTeam): The registry of available worker agents.
            model_id (str): The model identifier for the planner.
            system_prompt_template (str, optional): The prompt template. Defaults to config.
            debug_mode (bool, optional): Enable print statements for debugging. Defaults to False.
        """
        self.client = client
        self.team = team
        self.model_id = model_id

        # Inject the dynamic manifest into the static template
        manifest = self.team.get_team_manifest()
        self.system_prompt = system_prompt_template.format(team_manifest=manifest)
        self.debug_mode = debug_mode
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def run(self, user_request: str) -> str:
        """
        Execute the high-level planning loop for a user request.

        Args:
            user_request (str): The complex query or instruction from the user.

        Returns:
            str: The final consolidated report or answer.
        """
        if self.debug_mode:
            print(f"\n[Planner] Received Request: {user_request}")
        self.messages.append({"role": "user", "content": user_request})

        step = 0
        while step < 15:
            # Generate initial response
            response = self.client.chat(
                model=self.model_id,
                messages=self.messages,
                tools=TASK_PLANNER_TOOLS_JSON
            )
            self.messages.append(response.message)

            # Check for tool calls
            if response.message.tool_calls:
                for tc in response.message.tool_calls:
                    tool_name = tc.function.name
                    args = json.loads(tc.function.arguments)

                    # Termination Case: This must be checked explicitly to break the loop
                    if tool_name == "terminate_workflow":
                        # Before we return, otherwise the API history breaks on the next turn
                        self._submit_tool_output(tc.id, "Workflow Completed.")
                        return args["final_report"]

                    # Standard case: Delegation
                    if tool_name == "delegate_task":
                        # We call the internal implementation
                        result = self._execute_delegation(
                            agent_name=args["agent_name"],
                            task=args["task"]
                        )
                        self._submit_tool_output(tc.id, result)

                step += 1
            else:
                # If the model outputs without calling a tool, return that text
                return response.message.content[0].text

        return "Error: specific task planner max steps reached."

    def _execute_delegation(self, agent_name: str, task: str) -> str:
        """
        Execute a delegation task by triggering a specific worker agent.

        Args:
            agent_name (str): The name of the registered agent to call.
            task (str): The specific instructions for the worker agent.

        Returns:
            str: The textual response/report from the worker agent.
        """
        """
        The concrete logic for the 'delegate_task' tool.
        """
        if self.debug_mode:
            print(f"  → [Planner] Delegating to '{agent_name}': {task}")

        try:
            # Get the agent from the team registry
            worker = self.team.get_agent(agent_name)

            # Run the agent, the worker does its own thinking and returns a string
            worker_response = worker.run(task)

            # Return the result to the Planner
            return f"Agent '{agent_name}' reported: {worker_response}"

        except ValueError:
            return f"Error: Agent '{agent_name}' does not exist. Check your team manifest."
        except Exception as e:
            return f"Error during delegation: {str(e)}"

    def _submit_tool_output(self, call_id: str, output: str):
        """
        Format and append a tool execution result to the conversation history.

        Args:
            call_id (str): The unique ID of the tool call.
            output (str): The content/result to return to the model.
        """
        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": [{"type": "document", "document": {"data": json.dumps({"output": output})}}]
        })
