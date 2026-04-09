import feedparser
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import time
import requests
from datetime import datetime

# 1. Grab the API key securely from GitHub Secrets
API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# ==========================================
# 🛑 FIREBASE CONFIGURATION
FIREBASE_URL = "https://newshots-9e66b-default-rtdb.asia-southeast1.firebasedatabase.app"
# ==========================================

model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

rss_feeds = {
    "The Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "The Economic Times": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "Press Information Bureau": "https://pib.gov.in/rss/Mainstream.xml"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def analyze_with_ai(headline, summary):
    """Refined UPSC filter to ensure we get results."""
    prompt = f"""
    You are a UPSC curriculum expert.
    Headline: {headline}
    Context: {summary}
    
    TASK:
    1. If this news is about Indian Politics, Global Summits, Economy, Science/Tech, or Environment, it is HIGHLY RELEVANT.
    2. If it is purely about Entertainment, Local Petty Crime, or Sports scores, say REJECT.
    3. Otherwise, provide a 3-bullet factual summary for a Civil Services aspirant. Do not use bold (**) characters.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "REJECT" in text.upper():
            return None
        return text
    except Exception:
        return None

def harvest_news():
    print(f"🚜 Harvester started at {datetime.now().strftime('%H:%M:%S')}")
    final_articles = []
    
    for source_name, feed_url in rss_feeds.items():
        print(f"Reading {source_name}...")
        feed = feedparser.parse(feed_url, agent=USER_AGENT)
        
        # Limit to top 5 articles per source to keep the run fast and avoid API limits
        for entry in feed.entries[:5]:
            headline = entry.get("title", "")
            raw_summary = entry.get("summary", "")
            link = entry.get("link", "")
            
            ai_summary = analyze_with_ai(headline, raw_summary)
            
            if ai_summary:
                print(f"  ✅ Kept: {headline[:50]}...")
                final_articles.append({
                    "headline": headline,
                    "summary": ai_summary,
                    "link": link,
                    "source": source_name,
                    "category": "UPSC Exam",
                    "time": datetime.now().strftime("%I:%M %p")
                })
            
            # 2-second pause to be safe with the free Gemini tier
            time.sleep(2) 
            
    # CRITICAL: Even if no articles found, we send the "last_updated" time
    payload = {
        "status": "success",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "article_count": len(final_articles),
        "data": final_articles
    }
    
    database_endpoint = f"{FIREBASE_URL}/upsc_news.json"
    
    try:
        # We use .put() to replace the old news with the fresh news
        response = requests.put(database_endpoint, json=payload)
        if response.status_code == 200:
            print(f"🚀 SUCCESS! {len(final_articles)} articles live on Firebase.")
        else:
            print(f"❌ Firebase Error: {response.text}")
    except Exception as e:
         print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    harvest_news()
