SUBSCRIPTION_STORE_TOOLS_JSON = [
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "Get the list of tables and columns in the database. Call this first to understand the data structure.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql_query",
            "description": "Execute a SQLite query against the 'subscriptions' table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Valid SQL query (e.g., SELECT * FROM subscriptions WHERE status='active')"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

TASK_PLANNER_TOOLS_JSON = [
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Delegate a specific sub-task to a team member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "The name of the agent to call."},
                    "task": {"type": "string", "description": "Specific instructions for that agent."}
                },
                "required": ["agent_name", "task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "terminate_workflow",
            "description": "Call this when the user's request is fully answered.",
            "parameters": {
                "type": "object",
                "properties": {
                    "final_report": {"type": "string", "description": "The comprehensive answer to the user."}
                },
                "required": ["final_report"]
            }
        }
    }
]
