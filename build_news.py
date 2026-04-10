import feedparser
import requests
from bs4 import BeautifulSoup
import os
import time
from datetime import datetime, timedelta
import re
import difflib
import json 

from groq import Groq

# ==========================================
# 🛑 CONFIGURATION
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ")
client = Groq(api_key=GROQ_API_KEY)

# Ensure NO trailing slash here
FIREBASE_URL = "https://newshots-9e66b-default-rtdb.asia-southeast1.firebasedatabase.app"

# Google Custom Search API Credentials 
GOOGLE_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY")
GOOGLE_CX_ID = os.environ.get("GOOGLE_CX_ID")

RSS_FEEDS = {
    "The Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "The Economic Times": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "Press Information Bureau": "https://pib.gov.in/rss/Mainstream.xml"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Helper function to get exact IST time
def get_ist_time():
    return datetime.now() + timedelta(hours=5, minutes=30)

# ==========================================
# 🧠 AI & HELPER FUNCTIONS
# ==========================================

def get_existing_database():
    try:
        response = requests.get(f"{FIREBASE_URL}/articles.json", timeout=10)
        if response.status_code == 200 and response.json():
            return response.json().get("data", [])
    except Exception as e:
        print(f"⚠️ Connection issue: {e}")
    return []

# Threshold set to 0.85 to allow similar but different news
def is_duplicate_story(new_headline, processed_headlines, threshold=0.85):
    for old_headline in processed_headlines:
        score = difflib.SequenceMatcher(None, new_headline.lower(), old_headline.lower()).ratio()
        if score > threshold:
            print(f"   🚫 Skipped: Too similar to '{old_headline[:30]}...' (Score: {score:.2f})")
            return True
    return False

# 👇 NEW JSON-ENFORCED AI FUNCTION
def analyze_with_ai(headline, summary):
    """Professional News Analyst persona. Synced to strict JSON output."""
    
    prompt = (
        f"You are a professional News Analyst. Read the following news story and "
        f"categorize it, determine UPSC relevance, and summarize it into exactly 5 concise, factual sentences.\n\n"
        f"You MUST output your response as a valid JSON object using exactly these three keys:\n"
        f"1. \"category\" (string, one word)\n"
        f"2. \"is_upsc_relevant\" (boolean, true or false)\n"
        f"3. \"summary\" (string, the 4 sentences)\n\n"
        f"HEADLINE: {headline}\n"
        f"TEXT: {summary[:2500]}"
    )

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile", 
            temperature=0.1, 
            # This is the magic parameter that blocks conversational filler
            response_format={"type": "json_object"}
        )
        
        raw_json_text = response.choices[0].message.content.strip()
        ai_data = json.loads(raw_json_text)
        
        return {
            "category": str(ai_data.get("category", "General")).capitalize(), 
            "is_upsc_relevant": bool(ai_data.get("is_upsc_relevant", False)), 
            "summary": str(ai_data.get("summary", "")).strip()
        }
        
    except Exception as e:
        print(f"  ⚠️ AI Parsing Error: {e}")
        return None

def fetch_media_details(headline, link):
    image_url = "https://images.unsplash.com/photo-1495020689067-958852a7765e?q=80&w=1000"
    is_video = False
    try:
        res = requests.get(link, headers={'User-Agent': USER_AGENT}, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        if "/videos/" in link.lower() or "video-show" in link.lower():
            is_video = True
        
        og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'twitter:image'})
        if og_img and og_img.get('content'):
            temp_img = og_img['content']
            if not any(x in temp_img.lower() for x in ["logo", "icon", "thehindu", "toi-logo", "default"]):
                image_url = temp_img
                return {"image": image_url, "is_video": is_video}

        if GOOGLE_API_KEY and GOOGLE_CX_ID:
            clean_query = re.sub(r'[^\w\s]', '', headline) 
            search_query = " ".join(clean_query.split()[:7]) + " news"
            google_url = "https://customsearch.googleapis.com/customsearch/v1"
            params = {'q': search_query, 'cx': GOOGLE_CX_ID, 'key': GOOGLE_API_KEY, 'searchType': 'image', 'num': 1}
            api_res = requests.get(google_url, params=params, timeout=10)
            if api_res.status_code == 200:
                data = api_res.json()
                if 'items' in data and len(data['items']) > 0:
                    image_url = data['items'][0]['link']
                
    except Exception:
        pass
    return {"image": image_url, "is_video": is_video}

# ==========================================
# 🚜 MAIN HARVESTER LOGIC
# ==========================================

def harvest_news():
    ist = get_ist_time()
    print(f"🚜 Harvester (8B) started at {ist.strftime('%H:%M:%S')} (IST)")
    existing_articles = get_existing_database()
    processed_headlines = [art['headline'] for art in existing_articles]
    
    new_articles = []
    
    for source_name, feed_url in RSS_FEEDS.items():
        print(f"\nReading {source_name}...")
        feed = feedparser.parse(feed_url, agent=USER_AGENT)
        
        for entry in feed.entries[:10]:
            headline = entry.get("title", "")
            raw_summary = entry.get("summary", "")
            link = entry.get("link", "")
            
            if is_duplicate_story(headline, processed_headlines):
                continue
                
            processed_headlines.append(headline)
            ai_data = analyze_with_ai(headline, raw_summary)
            
            if ai_data:
                print(f"  ✨ Added [{ai_data['category']}] -> {headline[:40]}...")
                media_data = fetch_media_details(headline, link)
                
                new_articles.append({
                    "headline": headline,
                    "summary": ai_data['summary'],
                    "link": link,
                    "image": media_data['image'],
                    "is_video": media_data['is_video'],
                    "source": source_name,
                    "category": ai_data['category'],
                    "is_upsc_relevant": ai_data['is_upsc_relevant'],
                    "time_added": get_ist_time().strftime("%Y-%m-%d %I:%M %p")
                })
            else:
                print(f"  🤖 AI Failed/Rejected: {headline[:30]}...")
            
            time.sleep(2) 
            
    all_articles = (new_articles + existing_articles)[:1000]
    
    payload = {
        "status": "success",
        "last_updated": get_ist_time().strftime("%Y-%m-%d %I:%M %p"),
        "total_articles": len(all_articles),
        "data": all_articles
    }
    
    # 💾 Local backup for GitHub
    with open('upsc_news.json', 'w') as f:
        json.dump(payload, f, indent=4)

    # 🚀 Direct Push to Firebase
    try:
        response = requests.put(f"{FIREBASE_URL}/articles.json", json=payload, timeout=15)
        if response.status_code == 200:
            print(f"\n🚀 SUCCESS! Added {len(new_articles)} new stories.")
        else:
            print(f"❌ Firebase Error {response.status_code}: {response.text}")
    except Exception as e:
         print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    harvest_news()
