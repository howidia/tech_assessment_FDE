"""
Agent Team Registry Module.

This module defines the AgentTeam class, which serves as a central registry
for managing worker agents. It allows for the dynamic registration and retrieval
of agents, providing a unified interface for the Task Planner to discover and
delegate tasks to available team members.
"""

from typing import Dict, Protocol


class RunnableAgent(Protocol):
    """
    Protocol defining the interface for executable agents.

    Any agent registered with the AgentTeam must implement the `run` method
    taking a string input and returning a string output.
    """
    def run(self, input_text: str) -> str:
        ...


class AgentTeam:
    """
    A registry for managing and discovering worker agents.

    This class maintains a mapping of agent names to their instances and descriptions,
    acting as an abstraction layer between the high-level planner and the specific
    worker implementations.
    """

    def __init__(self):
        """
        Initialize an empty AgentTeam registry.
        """
        self._agents: Dict[str, RunnableAgent] = {}
        self._descriptions: Dict[str, str] = {}

    def register_agent(self, name: str, agent: RunnableAgent, description: str):
        """
        Register a new worker agent with the team.

        Args:
            name (str): The unique identifier for the agent (e.g., "DataAnalyst").
            agent (RunnableAgent): The agent instance to register.
            description (str): A brief description of the agent's capabilities,
                               used by the Planner to decide when to delegate.
        """
        self._agents[name] = agent
        self._descriptions[name] = description
        print(f"[Team] Registered agent: '{name}'")

    def get_agent(self, name: str) -> RunnableAgent:
        """
        Retrieve a registered agent by name.

        Args:
            name (str): The name of the agent to retrieve.

        Returns:
            RunnableAgent: The requested agent instance.

        Raises:
            ValueError: If no agent with the given name is found.
        """
        if name not in self._agents:
            raise ValueError(f"Agent '{name}' not found in team.")
        return self._agents[name]

    def get_team_manifest(self) -> str:
        """
        Generate a text manifest describing all registered agents.

        Returns:
            str: A formatted string listing agent names and their descriptions,
                 suitable for injection into a system prompt.
        """
        manifest = "AVAILABLE TEAM MEMBERS:\n"
        for name, desc in self._descriptions.items():
            manifest += f"- {name}: {desc}\n"
        return manifest
