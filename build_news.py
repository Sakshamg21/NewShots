import feedparser
import google.generativeai as genai
import os
import json
import time

# 1. Grab the API key securely from GitHub Secrets
API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Flash is incredibly fast and cheap/free

# 2. Your elite sources
rss_feeds = {
"The Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "The Economic Times": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "Press Information Bureau": "https://pib.gov.in/rss/Mainstream.xml"
}

def analyze_with_ai(headline, summary):
    """Sends the article to Gemini to act as a UPSC filter and summarizer."""
    prompt = f"""
    You are a strict UPSC exam curator. Read this news article. 
    Headline: {headline}
    Summary: {summary}
    
    If it is purely political rhetoric, gossip, or useless for exams, reply ONLY with the word: REJECT
    If it is highly relevant for UPSC (GS-1, GS-2, or GS-3), write a strictly factual, 3-bullet-point summary. Do not use formatting like bolding, just plain text.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "REJECT" in text:
            return None
        return text
    except Exception as e:
        return None

def harvest_news():
    print("🚜 Starting the AI Harvester...")
    final_articles = []
    
    for source_name, feed_url in rss_feeds.items():
        print(f"Reading {source_name}...")
        feed = feedparser.parse(feed_url)
        
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
            
    # Save everything to a clean JSON file
    with open("upsc_news.json", "w", encoding="utf-8") as f:
        json.dump({"status": "success", "data": final_articles}, f, indent=4)
    print("✅ Finished! Data written to upsc_news.json")

if __name__ == "__main__":
    harvest_news()
