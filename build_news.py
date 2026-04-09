import feedparser
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import time
from datetime import datetime
import re

# ==========================================
# 🛑 CONFIGURATION
# ==========================================
API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
FIREBASE_URL = "https://newshots-9e66b-default-rtdb.asia-southeast1.firebasedatabase.app"

model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

RSS_FEEDS = {
    "The Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "The Economic Times": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# ==========================================
# 🧠 AI & HELPER FUNCTIONS
# ==========================================

def get_existing_database():
    """Fetches the current database from Firebase to prevent duplicates."""
    try:
        response = requests.get(f"{FIREBASE_URL}/articles.json", timeout=10)
        if response.status_code == 200 and response.json():
            return response.json().get("data", [])
    except Exception:
        pass
    return []

def analyze_with_ai(headline, summary):
    """Asks Gemini to categorize, summarize, and tag for UPSC."""
    prompt = f"""
    Read this news article.
    Headline: {headline}
    Context: {summary}
    
    You must output your response exactly in this format:
    CATEGORY: [Choose exactly one: Politics, Business, Technology, Science, Sports, Entertainment, International, National, Miscellaneous]
    UPSC_RELEVANT: [True or False - True ONLY if it impacts Indian polity, economy, IR, or major science]
    SUMMARY: [Write exactly 3 concise, factual sentences.]
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Parse the AI's structured response
        category = re.search(r'CATEGORY:\s*(.*)', text).group(1).strip()
        upsc_tag = re.search(r'UPSC_RELEVANT:\s*(.*)', text).group(1).strip()
        summary_text = re.search(r'SUMMARY:\s*(.*)', text, re.DOTALL).group(1).strip()
        
        is_upsc = "True" in upsc_tag
        return {"category": category, "is_upsc_relevant": is_upsc, "summary": summary_text}
    except Exception as e:
        print(f"  ⚠️ AI Parsing Error: {e}")
        return None

def fetch_image_from_link(link):
    """Scrapes the article link to find the main image."""
    try:
        res = requests.get(link, headers={'User-Agent': USER_AGENT}, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content'):
            return og_img['content']
    except Exception:
        pass
    return "https://images.unsplash.com/photo-1495020689067-958852a7765e?q=80&w=1000"

# ==========================================
# 🚜 MAIN HARVESTER LOGIC
# ==========================================

def harvest_news():
    print(f"🚜 Harvester started at {datetime.now().strftime('%H:%M:%S')}")
    
    # 1. Load existing news so we don't repeat articles
    existing_articles = get_existing_database()
    seen_headlines = {art['headline'].lower() for art in existing_articles}
    print(f"📚 Loaded {len(existing_articles)} existing articles from Firebase.")
    
    new_articles = []
    
    # 2. Check Feeds
    for source_name, feed_url in RSS_FEEDS.items():
        print(f"\nReading {source_name}...")
        feed = feedparser.parse(feed_url, agent=USER_AGENT)
        
        for entry in feed.entries[:10]:
            headline = entry.get("title", "")
            raw_summary = entry.get("summary", "")
            link = entry.get("link", "")
            
            # THE DUPLICATE CHECK
            if headline.lower() in seen_headlines:
                continue
                
            seen_headlines.add(headline.lower())
            
            # Process new article
            ai_data = analyze_with_ai(headline, raw_summary)
            
            if ai_data:
                print(f"  ✨ Added [{ai_data['category']}] (UPSC: {ai_data['is_upsc_relevant']}) -> {headline[:40]}...")
                
                image_url = fetch_image_from_link(link)
                
                new_articles.append({
                    "headline": headline,
                    "summary": ai_data['summary'],
                    "link": link,
                    "image": image_url,
                    "source": source_name,
                    "category": ai_data['category'],
                    "is_upsc_relevant": ai_data['is_upsc_relevant'],
                    "time_added": datetime.now().strftime("%Y-%m-%d %I:%M %p")
                })
            
            time.sleep(2) # Respect API limits
            
    # 3. Combine Old and New News (Keep latest 100 to save space)
    all_articles = new_articles + existing_articles
    all_articles = all_articles[:100] 
    
    # 4. Save back to Firebase
    payload = {
        "status": "success",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_articles": len(all_articles),
        "data": all_articles
    }
    
    try:
        response = requests.put(f"{FIREBASE_URL}/articles.json", json=payload)
        if response.status_code == 200:
            print(f"\n🚀 SUCCESS! Added {len(new_articles)} new articles. Database now has {len(all_articles)} items.")
        else:
            print(f"❌ Firebase Error: {response.text}")
    except Exception as e:
         print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    harvest_news()
