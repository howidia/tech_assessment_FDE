"""
Main Entry Point for the Subscription Agent System.

This script bootstraps the entire agent architecture, initializing the
subscription store, worker agents, and the task planner. It provides an
interactive command-line interface (CLI) for users to query the system.
"""

import os
import sys
import cohere
from dotenv import load_dotenv

from src.tools.subscription_store import SubscriptionStore 
from src.agents import TaskPlannerAgent, SubscriptionDataAssistantAgent 
from src.agent_team import AgentTeam
from config.agent_config import MODEL_ID


def main():
    # Setup environment
    load_dotenv()
    if not os.environ.get("COHERE_API_KEY"):
        print("Error: COHERE_API_KEY not found in .env file.")
        return

    debug_mode = 'True' == os.environ.get("DEBUG_MODE", False)

    co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])

    # Initialize the Infrastructure (Database)
    print("Initializing Database...")
    store = SubscriptionStore("data/subscription_data.csv")

    # Initialize the Worker Aegnts (n=1 currently)
    data_agent = SubscriptionDataAssistantAgent(
        client=co,
        model_id=MODEL_ID,
        tools_json=store.get_tool_schemas(),
        functions_map=store.get_tools(),
        debug_mode=debug_mode
    )

    # Create the Agent Team
    team = AgentTeam()
    team.register_agent(
        name="DataAnalyst",
        agent=data_agent,
        description="Can query the SQL database for revenue, churn, and subscription details."
    )

    # Initialize the Task Planner Agent
    planner = TaskPlannerAgent(
        client=co, 
        model_id=MODEL_ID, 
        team=team,
        debug_mode=debug_mode
    )

    # Interactive Loop with User
    print("\n" + "="*50)
    print("🤖 Agent Team Ready. Type -1 to exit.")
    print("="*50 + "\n")

    while True:
        try:
            # Get User Input
            user_input = input("\nUser Request: ").strip()

            # Check Termination Condition
            if user_input == "-1" or user_input.lower() in ["exit", "quit"]:
                print("Terminating session. Goodbye!")
                break

            if not user_input:
                continue

            # Run the Agent
            result = planner.run(user_input)

            # Display Result
            print("\n--------------- Agent Response ---------------")
            print(result)
            print("----------------------------------------------")

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            print("\n\nForced Exit. Goodbye!")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
