import os
import requests
from telegram import Bot
import asyncio
import json
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import time
import schedule
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
time.sleep(1)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
POSTED_JOBS_FILE = "posted_jobs.json"

logger.info(f"✓ Bot Token loaded" if TELEGRAM_BOT_TOKEN else "✗ Bot Token missing")
logger.info(f"✓ Channel ID loaded" if TELEGRAM_CHANNEL_ID else "✗ Channel ID missing")

# Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def load_posted_jobs():
    try:
        if os.path.exists(POSTED_JOBS_FILE):
            with open(POSTED_JOBS_FILE, 'r') as f:
                return set(json.load(f))
    except:
        pass
    return set()

def save_posted_job(link):
    try:
        jobs = list(load_posted_jobs())
        if link not in jobs:
            jobs.append(link)
            with open(POSTED_JOBS_FILE, 'w') as f:
                json.dump(jobs, f)
    except:
        pass

def clean_text(text):
    text = re.sub(r'\s+', ' ', str(text))
    return text.strip()

def scrape_freejobsalert():
    jobs = []
    try:
        logger.info("📡 Scraping freejobsalert.com...")
        url = "https://www.freejobsalert.com"
        response = requests.get(url, headers=HEADERS, timeout=20)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all links that might be job postings
            links = soup.find_all('a', href=True, limit=100)
            
            for link in links:
                try:
                    title = clean_text(link.get_text())
                    href = link.get('href', '')
                    
                    # Skip if too short or not a valid link
                    if len(title) < 15 or not href.startswith('http'):
                        continue
                    
                    # Skip if already seen on this site (freejobsalert)
                    if 'freejobsalert' in href and href.count('/') < 5:
                        continue
                    
                    # Filter for job-related keywords
                    job_keywords = ['recruitment', 'notification', 'exam', 'vacancy', 'apply', 'admit', 'result', 'job', 'position', 'psc', 'ssc', 'railway', 'bank', 'police']
                    if not any(kw in title.lower() for kw in job_keywords):
                        continue
                    
                    # Get the container (parent) to extract details
                    container = link.find_parent(['div', 'article', 'li'])
                    if not container:
                        container = link.find_parent('table')
                    if not container:
                        continue
                    
                    # Extract details from container
                    container_text = container.get_text()
                    
                    # Organization
                    org_match = re.search(r'(?:Organization|Ministry|Department|Board|Bank):\s*([^\n]+)', container_text, re.I)
                    organization = org_match.group(1).strip() if org_match else 'Government Organization'
                    organization = clean_text(organization)[:100]
                    
                    # Eligibility
                    elig_match = re.search(r'(?:Eligibility|Qualification):\s*([^\n]+)', container_text, re.I)
                    eligibility = elig_match.group(1).strip() if elig_match else 'Check official website'
                    eligibility = clean_text(eligibility)[:100]
                    
                    # Salary
                    sal_match = re.search(r'(?:Salary|Pay|CTC|Pay Scale):\s*([₹\d,\-k.]+[^\n]*)', container_text, re.I)
                    salary = sal_match.group(1).strip() if sal_match else 'As per norms'
                    salary = clean_text(salary)[:100]
                    
                    # Last date
                    date_match = re.search(r'(?:Last Date|Deadline|Apply Before):\s*([^\n]+)', container_text, re.I)
                    last_date = date_match.group(1).strip() if date_match else 'Check official website'
                    last_date = clean_text(last_date)[:100]
                    
                    # Check if posted today
                    posted_match = re.search(r'(?:Posted|Updated|Published):\s*([^\n]+)', container_text, re.I)
                    is_today = False
                    if posted_match:
                        posted_text = posted_match.group(1).lower()
                        is_today = 'today' in posted_text or datetime.now().strftime('%d') in posted_text
                    else:
                        # If no date found, include it
                        is_today = True
                    
                    if is_today:
                        job = {
                            'title': title[:200],
                            'organization': organization,
                            'eligibility': eligibility,
                            'salary': salary,
                            'last_date': last_date,
                            'link': href
                        }
                        
                        # Avoid duplicates
                        if not any(j['link'] == href for j in jobs):
                            jobs.append(job)
                            logger.info(f"  ✓ {title[:50]}...")
                
                except Exception as e:
                    continue
            
            logger.info(f"  ✓ Total: {len(jobs)} jobs")
        else:
            logger.warning(f"  Status: {response.status_code}")
    except Exception as e:
        logger.error(f"  Error: {str(e)[:50]}")
    
    return jobs

def create_message(job):
    message = f"""
📢 <b>{job['title']}</b> 🚀

🎓 <b>Eligibility:</b> {job['eligibility']}
💰 <b>Stipend/Salary:</b> {job['salary']}
🗓️ <b>Last Date:</b> {job['last_date']}

<a href="{job['link']}"><b>✅ APPLY NOW ✅</b></a>
"""
    return message

async def send_to_channel(message):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='HTML')
        return True
    except Exception as e:
        logger.error(f"Telegram error: {str(e)[:50]}")
        return False

async def check_and_post_jobs():
    logger.info("=" * 70)
    logger.info("🤖 FREE JOBS ALERT - LATEST JOBS ONLY")
    logger.info("=" * 70)
    
    posted = load_posted_jobs()
    logger.info(f"✓ Cache: {len(posted)} jobs")
    
    jobs = scrape_freejobsalert()
    
    if not jobs:
        logger.warning("⚠️ No jobs found")
        return
    
    logger.info(f"✓ Checking {len(jobs)} jobs")
    
    count = 0
    for job in jobs:
        if job['link'] not in posted:
            logger.info(f"📤 {job['title'][:40]}...")
            msg = create_message(job)
            success = await send_to_channel(msg)
            
            if success:
                save_posted_job(job['link'])
                count += 1
                await asyncio.sleep(1)
    
    logger.info(f"✓ Posted: {count} NEW jobs")
    logger.info("=" * 70)

def job_scheduler():
    asyncio.run(check_and_post_jobs())

def main():
    logger.info("🚂 BOT STARTED")
    logger.info("Source: freejobsalert.com")
    logger.info("Posts: Latest jobs only")
    logger.info("=" * 70)
    
    schedule.every(5).minutes.do(job_scheduler)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()

