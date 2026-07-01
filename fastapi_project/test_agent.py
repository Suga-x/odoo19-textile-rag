import os
from dotenv import load_dotenv
from litellm import completion

# 1. Load konfigurasi dari file .env
load_dotenv()

current_env = os.getenv("CURRENT_ENV")

# 2. Tentukan model berdasarkan lokasi kamu sekarang
if current_env == "KANTOR":
    print(" Menjalankan Mode: PC Kantor (Menggunakan Gemini API)")
    model_name = "gemini/gemini-2.5-flash"
    api_key = os.getenv("GEMINI_API_KEY")
    api_base = None
else:
    print(" Menjalankan Mode: Rumah (Menggunakan Mac M1 Pro + Qwen Lokal)")
    model_name = os.getenv("LOCAL_MODEL")
    api_key = "ollama" 
    api_base = os.getenv("LOCAL_API_BASE")
    
# 3. Test panggil LLM
try:
    response = completion(
        model=model_name,
        messages=[{"role": "user", "content": "Halo! Berikan satu tips singkat untuk belajar AI Agent."}],
        api_key=api_key,
        api_base=api_base
    )
    print("\n Jawaban LLM:")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"\n Terjadi Error: {e}")