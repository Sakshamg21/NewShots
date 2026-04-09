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

# NEW: Google Custom Search API Credentials
GOOGLE_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY")
GOOGLE_CX_ID = os.environ.get("GOOGLE_CX_ID")

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

def fetch_media_details(headline, link):
    """Scrapes the article to find images/videos, with Google API Fallback."""
    image_url = "https://images.unsplash.com/photo-1495020689067-958852a7765e?q=80&w=1000"
    is_video = False
    
    try:
        # 1. Scrape the page
        res = requests.get(link, headers={'User-Agent': USER_AGENT}, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        # 2. Video Detection Logic
        if "/videos/" in link.lower() or "video-show" in link.lower():
            is_video = True
        og_type = soup.find('meta', property='og:type')
        if og_type and "video" in og_type.get('content', '').lower():
            is_video = True
        vids = soup.find_all('iframe', src=re.compile(r'youtube|vimeo|dailymotion|videoplayer|indiatimes', re.I))
        if vids:
            is_video = True

        # 3. Image Detection Logic
        og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'twitter:image'})
        if og_img and og_img.get('content'):
            temp_img = og_img['content']
            # If it's a generic logo, force the Google fallback
            if not any(x in temp_img.lower() for x in ["logo", "icon", "thehindu", "toi-logo", "default"]):
                image_url = temp_img
                return {"image": image_url, "is_video": is_video}

        # 4. Official Google Image Search Fallback
        if GOOGLE_API_KEY and GOOGLE_CX_ID:
            print(f"    🔍 Asking Google for a better image...")
            clean_query = re.sub(r'[^\w\s]', '', headline) 
            search_query = " ".join(clean_query.split()[:7]) + " news"
            
            google_url = "https://customsearch.googleapis.com/customsearch/v1"
            params = {
                'q': search_query,
                'cx': GOOGLE_CX_ID,
                'key': GOOGLE_API_KEY,
                'searchType': 'image',
                'num': 1 # We only need the top 1 result
            }
            
            api_res = requests.get(google_url, params=params, timeout=10)
            if api_res.status_code == 200:
                data = api_res.json()
                if 'items' in data and len(data['items']) > 0:
                    image_url = data['items'][0]['link']
            else:
                print(f"    ⚠️ Google API Error: {api_res.status_code} - {api_res.text}")
                
    except Exception as e:
        print(f"    ⚠️ Media fetch error: {e}")
        
    return {"image": image_url, "is_video": is_video}

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
                
                # Fetch image and video status
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
