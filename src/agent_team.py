from typing import Dict, Protocol

# Protocol to ensure any agent we add has a .run() method
class RunnableAgent(Protocol):
    def run(self, input_text: str) -> str:
        ...

class AgentTeam:
    """
    A concrete registry that manages the available agents.
    It acts as the 'API Layer' between the Planner and the Workers.
    """
    def __init__(self):
        self._agents: Dict[str, RunnableAgent] = {}
        self._descriptions: Dict[str, str] = {}

    def register_agent(self, name: str, agent: RunnableAgent, description: str):
        """
        Add a worker agent to the team.
        name: How the Planner will refer to this agent (e.g., "DataAnalyst").
        description: Instructions for the Planner on WHEN to use this agent.
        """
        self._agents[name] = agent
        self._descriptions[name] = description
        print(f"[Team] Registered agent: '{name}'")

    def get_agent(self, name: str) -> RunnableAgent:
        if name not in self._agents:
            raise ValueError(f"Agent '{name}' not found in team.")
        return self._agents[name]

    def get_team_manifest(self) -> str:
        """
        Returns a string describing the team capabilities. 
        This is injected into the Planner's system prompt.
        """
        manifest = "AVAILABLE TEAM MEMBERS:\n"
        for name, desc in self._descriptions.items():
            manifest += f"- {name}: {desc}\n"
        return manifest