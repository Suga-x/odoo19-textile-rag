import os
from dotenv import load_dotenv
from litellm import completion

# 1. Load configuration from .env file
load_dotenv()

current_env = os.getenv("CURRENT_ENV")

# 2. Determine model based on current location
if current_env == "KANTOR":
    print(" Running Mode: Office PC (Using Gemini API)")
    model_name = "gemini/gemini-2.5-flash"
    api_key = os.getenv("GEMINI_API_KEY")
    api_base = None
else:
    print(" Running Mode: Home (Using Mac M1 Pro + Local Qwen)")
    model_name = os.getenv("LOCAL_MODEL")
    api_key = "ollama"
    api_base = os.getenv("LOCAL_API_BASE")

# 3. Test LLM call
try:
    response = completion(
        model=model_name,
        messages=[{"role": "user", "content": "Hello! Give me one short tip for learning AI Agents."}],
        api_key=api_key,
        api_base=api_base
    )
    print("\n LLM Answer:")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"\n Error Occurred: {e}")
