import requests
from bs4 import BeautifulSoup
import os
import time
import urllib.parse
import hashlib
from openai import OpenAI

# --- CONFIGURATION ---
# We check the "NGO/Development" and "General" categories for Consultants
URLS = [
    "https://bdjobs.com"
]

KEYWORDS = [
    "Individual Consultant", "SIC", "Consultant", "National Consultant", "Individual Local Consultant", "Local Consultant", "Environment", 
    "Environmental", "Natural", "Disaster", "Water", "Expert", "Program", "Project", "Coordinator", "Manager", "Climate", "Monitoring", "Evaluation", "Specialist"
]

HISTORY_FILE = "history.txt"

# Secrets
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Setup Free AI
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_ai_summary(raw_text):
    """ Sends job text to AI for summarization """
    if not OPENROUTER_API_KEY:
        return None

    prompt = f"""
    You are a job analyst. Extract details from this BdJobs circular.
    
    1. Project/Organization Name: (If not found, assume the Company Name)
    2. Education: (Summarize the required degree, e.g. "Masters in Environmental Science")
    3. Experience: (Years required)
    4. Salary: (Specific amount or 'Negotiable')
    
    RAW TEXT: "{raw_text[:8000]}"
    
    Return JSON format:
    {{"org": "...", "edu": "...", "exp": "...", "sal": "..."}}
    """

    try:
        completion = client.chat.completions.create(
            # Using Google's Free Flash Lite model via OpenRouter
            model="google/gemini-2.0-flash-lite-preview-02-05:free", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        import json
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"AI Error: {e}")
        return None

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    with open(HISTORY_FILE, "r") as f: return set(line.strip() for line in f)

def save_history(seen_set):
    with open(HISTORY_FILE, "w") as f:
        for item in seen_set: f.write(f"{item}\n")

def check_bdjobs():
    print("Scanning BdJobs...")
    seen_jobs = load_history()
    new_found = False
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for url in URLS:
        try:
            print(f"Checking: {url}")
            response = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job cards
            job_cards = soup.find_all('div', class_=re.compile(r'(norm-jobs-wrapper|sout-jobs-wrapper)'))

            for card in job_cards:
                # 1. Extract Title and Link
                title_tag = card.find('div', class_='job-title-text').find('a')
                if not title_tag: continue
                
                raw_title = title_tag.get_text(" ", strip=True)
                
                # 2. Check Keywords in Title
                if not any(k.lower() in raw_title.lower() for k in KEYWORDS):
                    continue

                # 3. Create Unique ID
                relative_link = title_tag['href']
                full_link = urllib.parse.urljoin("https://jobs.bdjobs.com/", relative_link)
                job_id = hashlib.md5(full_link.encode()).hexdigest()
                
                # 4. Check History (Skip if old)
                if job_id in seen_jobs:
                    continue
                
                # --- NEW JOB DETECTED ---
                print(f"New Job Found: {raw_title}")
                seen_jobs.add(job_id)
                new_found = True
                
                # 5. Fetch Full Details for AI
                try:
                    # Visit the job link
                    job_resp = requests.get(full_link, headers=headers, timeout=10)
                    job_soup = BeautifulSoup(job_resp.content, 'html.parser')
                    full_text = job_soup.get_text(" ", strip=True)
                    
                    # 6. Ask AI to Summarize
                    data = get_ai_summary(full_text)
                    
                    if data:
                        msg = (
                            f"🔔 **New BdJobs Circular!**\n\n"
                            f"📌 *Post:* [{raw_title}]({full_link})\n"
                            f"🏢 *Org:* {data.get('org', 'N/A')}\n"
                            f"🎓 *Edu:* {data.get('edu', 'Not Mentioned')}\n"
                            f"⏳ *Exp:* {data.get('exp', 'N/A')}\n"
                            f"💰 *Salary:* {data.get('sal', 'Negotiable')}"
                        )
                        send_telegram(msg)
                    else:
                        # Fallback if AI fails
                        send_telegram(f"🔔 **New Job:** [{raw_title}]({full_link})")
                        
                    time.sleep(3) # Wait 3 seconds to be polite to BdJobs

                except Exception as e:
                    print(f"Error fetching details: {e}")

        except Exception as e:
            print(f"Connection Error: {e}")

    if new_found:
        save_history(seen_jobs)

import re
if __name__ == "__main__":
    check_bdjobs()
