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
    "https://bdjobs.com", 
    "https://unjobs.org/duty_stations/bangladesh"
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
    except:
        pass

def get_ai_summary(raw_text):
    """ Sends job text to AI for summarization """
    if not OPENROUTER_API_KEY:
        return None

    prompt = f"""
    You are a job analyst. Extract details from this BdJobs circular.
    
    1. Project/Organization Name: (If not found, assume the Company Name)
    2. Education: (Summarize the required degree, e.g. "Masters in Environmental Science")
    3. Experience: (Years required)
    4. Salary: (If mentioned, else 'Negotiable')
    
    RAW TEXT: "{raw_text[:8000]}"
    
    Return JSON: {{"org": "...", "edu": "...", "exp": "...", "sal": "..."}}
    """
    try:
        completion = client.chat.completions.create(
            model="google/gemini-2.0-flash-lite-preview-02-05:free", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        import json
        return json.loads(completion.choices[0].message.content)
    except:
        return None

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    with open(HISTORY_FILE, "r") as f: return set(line.strip() for line in f)

def save_history(seen_set):
    with open(HISTORY_FILE, "w") as f:
        for item in seen_set: f.write(f"{item}\n")

# --- PARSER FOR BDJOBS ---
def parse_bdjobs(soup, seen_jobs):
    new_found = False
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    cards = soup.find_all('div', class_=re.compile(r'(norm-jobs-wrapper|sout-jobs-wrapper)'))
    for card in cards:
        try:
            title_tag = card.find('div', class_='job-title-text').find('a')
            if not title_tag: continue
            raw_title = title_tag.get_text(" ", strip=True)
            
            # Filter
            if not any(k.lower() in raw_title.lower() for k in KEYWORDS): continue

            full_link = urllib.parse.urljoin("https://bdjobs.com", title_tag['href'])
            job_id = hashlib.md5(full_link.encode()).hexdigest()
            
            if job_id in seen_jobs: continue
            
            print(f"New BdJob: {raw_title}")
            seen_jobs.add(job_id)
            new_found = True
            
            # AI Check
            resp = requests.get(full_link, headers=headers)
            data = get_ai_summary(BeautifulSoup(resp.content, 'html.parser').get_text(" ", strip=True))
            
            msg = f"🔔 **New BdJobs Circular!**\n\n📌 *Post:* [{raw_title}]({full_link})"
            if data:
                msg += f"\n🏢 *Org:* {data.get('org')}\n🎓 *Edu:* {data.get('edu')}\n⏳ *Exp:* {data.get('exp')}\n💰 *Sal:* {data.get('sal')}"
            send_telegram(msg)
            time.sleep(2)
        except: pass
    return new_found

# --- PARSER FOR UN JOBS ---
def parse_unjobs(soup, seen_jobs):
    new_found = False
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # UnJobs lists are inside <div class="job"> or simple <a> tags
    # We look for all links inside the main content area
    links = soup.find_all('a', class_='jtitle') # 'jtitle' is common on unjobs
    
    for link in links:
        try:
            raw_title = link.get_text(" ", strip=True)
            
            # Filter
            if not any(k.lower() in raw_title.lower() for k in KEYWORDS): continue
            
            full_link = urllib.parse.urljoin("https://unjobs.org", link['href'])
            job_id = hashlib.md5(full_link.encode()).hexdigest()
            
            if job_id in seen_jobs: continue
            
            print(f"New UN Job: {raw_title}")
            seen_jobs.add(job_id)
            new_found = True
            
            # AI Check
            resp = requests.get(full_link, headers=headers)
            # UN Jobs detail pages are often simple wrappers. We grab the text.
            data = get_ai_summary(BeautifulSoup(resp.content, 'html.parser').get_text(" ", strip=True))
            
            msg = f"🇺🇳 **New UN Job Detected!**\n\n📌 *Post:* [{raw_title}]({full_link})"
            if data:
                msg += f"\n🏢 *Org:* {data.get('org')}\n🎓 *Edu:* {data.get('edu')}\n⏳ *Exp:* {data.get('exp')}"
            send_telegram(msg)
            time.sleep(2)
        except: pass
    return new_found

def main():
    print("Starting Multi-Site Scan...")
    seen_jobs = load_history()
    files_changed = False
    headers = {'User-Agent': 'Mozilla/5.0'}

    for url in URLS:
        try:
            print(f"Scanning: {url}")
            response = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            if "bdjobs" in url:
                if parse_bdjobs(soup, seen_jobs): files_changed = True
            elif "unjobs" in url:
                if parse_unjobs(soup, seen_jobs): files_changed = True
                
        except Exception as e:
            print(f"Error on {url}: {e}")

    if files_changed:
        save_history(seen_jobs)

import re
if __name__ == "__main__":
    main()
