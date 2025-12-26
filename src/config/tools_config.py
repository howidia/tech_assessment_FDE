TOOLS_JSON = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "gets the weather of a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "the location to get the weather, example: San Francisco.",
                    }
                },
                "required": ["location"],
            },
        },
    },
]