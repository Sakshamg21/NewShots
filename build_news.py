import feedparser
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import time
import requests

# 1. Grab the API key securely from GitHub Secrets
API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# ==========================================
# 🛑 PASTE YOUR FIREBASE URL RIGHT HERE:
FIREBASE_URL = "https://newshots-9e66b-default-rtdb.asia-southeast1.firebasedatabase.app"
# ==========================================

# Create the model with relaxed safety settings for news analysis
model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# Your elite sources
rss_feeds = {
"The Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "The Economic Times": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "Press Information Bureau": "https://pib.gov.in/rss/Mainstream.xml"
}

# Define a fake browser header so websites don't block us
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def analyze_with_ai(headline, summary):
    """Sends the article to Gemini to act as a UPSC filter and summarizer."""
    prompt = f"""
    You are a UPSC curriculum expert. Read this news.
    Headline: {headline}
    Summary: {summary}
    
    TASK:
    1. Determine if this impacts Indian Polity, Economy, International Relations, or Science.
    2. If it is 100% irrelevant (like celebrity news or local crime), say REJECT.
    3. If it has even 10% relevance to the UPSC syllabus, write a clear 3-bullet factual summary. Do not use bolding.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "REJECT" in text:
            return None
        return text
    except Exception as e:
        print(f"   ⚠️ AI Error: {e}")
        return None

def harvest_news():
    print("🚜 Starting the AI Harvester...")
    final_articles = []
    
    for source_name, feed_url in rss_feeds.items():
        print(f"\nReading {source_name}...")
        # Tell feedparser to pretend it's a real browser
        feed = feedparser.parse(feed_url, agent=USER_AGENT)
        
        if not feed.entries:
            print(f"⚠️ Warning: Could not find any entries for {source_name}. Feed might be down or blocking us.")
            continue
            
        # Limit to top 10 to respect API rate limits
        for entry in feed.entries[:10]:
            headline = entry.get("title", "")
            raw_summary = entry.get("summary", "")
            link = entry.get("link", "")
            
            print(f"Checking: {headline[:40]}...")
            ai_summary = analyze_with_ai(headline, raw_summary)
            
            if ai_summary:
                print("   ✅ UPSC VIP Approved by AI!")
                final_articles.append({
                    "headline": headline,
                    "summary": ai_summary,
                    "link": link,
                    "source": source_name,
                    "category": "UPSC Exam"
                })
            else:
                print("   🚫 Rejected by AI.")
            
            # Pause for 4 seconds so Google doesn't block us for spamming the free tier
            time.sleep(4) 
            
    print("\n☁️ Sending data to Firebase...")
    payload = {"status": "success", "data": final_articles}
    
    # We add /upsc_news.json to the end of your Firebase URL so it formats correctly
    database_endpoint = f"{FIREBASE_URL}/upsc_news.json"
    
    try:
        response = requests.put(database_endpoint, json=payload)
        if response.status_code == 200:
            print("✅ Success! News is live on Firebase.")
        else:
            print(f"❌ Failed to send to Firebase: {response.text}")
    except Exception as e:
         print(f"❌ Failed to connect to Firebase: {e}")

if __name__ == "__main__":
    harvest_news()
