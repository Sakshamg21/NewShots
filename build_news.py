import google.generativeai as genai
import os

print("🔍 STARTING DIAGNOSTIC SCAN...")

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    print("❌ ERROR: GitHub did not find the GEMINI_API_KEY secret!")
else:
    print("✅ API Key found! Asking Google what models you can access...")
    genai.configure(api_key=API_KEY)
    
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            print("⚠️ Google says your API key has NO access to any text models.")
        else:
            print("🟢 SUCCESS! Your key has access to these models:")
            for name in available_models:
                print(f"   -> {name}")
                
    except Exception as e:
        print(f"🚨 FATAL ERROR: {e}")
