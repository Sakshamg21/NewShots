import google.generativeai as genai
import os

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    print("❌ ERROR: GitHub did not find the GEMINI_API_KEY secret!")
else:
    genai.configure(api_key=API_KEY)
    print("🔍 Scanning your new API key for 1.5-flash...")

    try:
        found = False
        for m in genai.list_models():
            # Specifically searching for 1.5-flash models
            if '1.5-flash' in m.name and 'generateContent' in m.supported_generation_methods:
                print(f"✅ FOUND: {m.name}")
                found = True
                
        if not found:
            print("❌ NOT FOUND: This key is still locked out of 1.5-flash.")
            
    except Exception as e:
        print(f"🚨 ERROR: {e}")
