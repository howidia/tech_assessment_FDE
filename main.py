
import cohere
from dotenv import load_dotenv
import os

from src.config.agent_config import SYSTEM_PROMPT
from src.config.tools_config import TOOLS_JSON
from src.tools.subscription_data_tools import get_weather

# Load environment variables from .env file
load_dotenv()

# Initialize Cohere client with API key from environment variable
co = cohere.ClientV2(
    api_key=os.environ.get("COHERE_API_KEY")  # Gets the API key securely
)

functions_map = {"get_weather": get_weather}

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "What's the weather in Toronto?"},
]


response = co.chat(
    model="command-a-03-2025", messages=messages, tools=TOOLS_JSON
)

if response.message.tool_calls:
    messages.append(
        {
            "role": "assistant",
            "tool_plan": response.message.tool_plan,
            "tool_calls": response.message.tool_calls,
        }
    )
    print(response.message.tool_plan, "\n")
    print(response.message.tool_calls)
