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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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

def save_posted_job(job_id):
    try:
        jobs = list(load_posted_jobs())
        if job_id not in jobs:
            jobs.append(job_id)
            with open(POSTED_JOBS_FILE, 'w') as f:
                json.dump(jobs, f)
    except:
        pass

def clean_text(text):
    text = re.sub(r'\s+', ' ', str(text))
    return text.strip()

def scrape_individual_job_page(job_url):
    """Scrape individual job page for FULL details"""
    try:
        logger.info(f"    🔍 Scraping: {job_url[:50]}...")
        
        session = requests.Session()
        response = session.get(job_url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        page_text = soup.get_text()
        
        # Extract eligibility
        eligibility = 'Check official website'
        elig_patterns = [
            r'(?:Eligibility|Qualification|Education):\s*([^\n]+)',
            r'(?:Eligible|Required):\s*([^\n]+)',
        ]
        for pattern in elig_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                eligibility = clean_text(match.group(1))[:80]
                break
        
        # Extract salary/stipend
        salary = 'As per norms'
        sal_patterns = [
            r'(?:Salary|Pay|Stipend|CTC|Pay Scale):\s*([₹$\d,\-\s.k]+)',
            r'[₹$][\d,]+(?:\s*-\s*[₹$]?[\d,]+)?',
        ]
        for pattern in sal_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                salary = clean_text(match.group(0) if '\d' in match.group(0) else match.group(1))[:80]
                break
        
        # Extract last date
        last_date = 'Check official website'
        date_patterns = [
            r'(?:Last Date|Deadline|Apply Before|Application Deadline):\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{1,2}\s+\w+\s+\d{4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                last_date = clean_text(match.group(1))[:30]
                break
        
        # Extract vacancies
        vacancies = ''
        vac_match = re.search(r'(?:Vacancies|Posts?):\s*(\d+)', page_text, re.I)
        if vac_match:
            vacancies = vac_match.group(1)
        
        return {
            'eligibility': eligibility,
            'salary': salary,
            'last_date': last_date,
            'vacancies': vacancies
        }
        
    except Exception as e:
        logger.debug(f"    Error scraping page: {e}")
        return None

def scrape_homepage_jobs():
    """Scrape homepage for job listings"""
    jobs = []
    
    try:
        logger.info("📡 Scraping govtjobsalerts.in homepage...")
        
        url = "https://www.govtjobsalerts.in"
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=20)
        
        if response.status_code != 200:
            logger.warning(f"  Status: {response.status_code}")
            return jobs
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all links that are job listings
        all_links = soup.find_all('a', href=True, limit=100)
        
        logger.info(f"  Found {len(all_links)} links, filtering for jobs...")
        
        for link in all_links:
            try:
                title = clean_text(link.get_text())
                href = link.get('href', '').strip()
                
                # Filter: must be a valid URL and contain job keywords
                if not href or len(title) < 15:
                    continue
                
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = 'https://www.govtjobsalerts.in' + href
                    else:
                        continue
                
                # Skip govtjobsalerts links (we want official org links)
                if 'govtjobsalerts.in' in href:
                    continue
                
                # Check for job keywords
                job_keywords = ['recruitment', 'notification', 'exam', 'vacancy', 'apply', 'admit', 'post', 'job', 'bharti']
                if not any(kw in title.lower() for kw in job_keywords):
                    continue
                
                # Skip if already processed
                if href in [j['link'] for j in jobs]:
                    continue
                
                # Now scrape the INDIVIDUAL JOB PAGE
                details = scrape_individual_job_page(href)
                
                if details:
                    job = {
                        'title': title[:250],
                        'link': href,
                        'eligibility': details['eligibility'],
                        'salary': details['salary'],
                        'last_date': details['last_date'],
                        'vacancies': details['vacancies'],
                        'id': href  # Use URL as unique ID
                    }
                    jobs.append(job)
                    logger.info(f"  ✓ {title[:50]}...")
                
                # Add small delay between requests
                time.sleep(1)
                
            except Exception as e:
                logger.debug(f"  Error: {e}")
                continue
        
        logger.info(f"  ✓ Total jobs with full details: {len(jobs)}")
        
    except Exception as e:
        logger.error(f"  Error: {str(e)[:50]}")
    
    return jobs

def create_message(job):
    """Create professional job post with all details"""
    
    message = f"""
📢 <b>{job['title']}</b>

📌 <b>Vacancies:</b> {job['vacancies'] if job['vacancies'] else 'Multiple'}
🎓 <b>Eligibility:</b> {job['eligibility']}
💰 <b>Salary:</b> {job['salary']}
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
    logger.info("🤖 GOVT JOBS ALERT - HOURLY SCAN")
    logger.info("=" * 70)
    
    posted = load_posted_jobs()
    logger.info(f"✓ Cache: {len(posted)} jobs")
    
    jobs = scrape_homepage_jobs()
    
    if not jobs:
        logger.warning("⚠️ No jobs found")
        return
    
    logger.info(f"✓ Found {len(jobs)} jobs with full details")
    
    count = 0
    for job in jobs:
        if job['id'] not in posted:
            logger.info(f"📤 Posting: {job['title'][:40]}...")
            msg = create_message(job)
            success = await send_to_channel(msg)
            
            if success:
                save_posted_job(job['id'])
                count += 1
                await asyncio.sleep(2)
    
    if count == 0:
        logger.info("✓ No new jobs to post")
    else:
        logger.info(f"✓ Posted {count} NEW jobs! 🎉")
    
    logger.info("=" * 70)

def job_scheduler():
    asyncio.run(check_and_post_jobs())

def main():
    logger.info("🚂 BOT STARTED")
    logger.info("Source: govtjobsalerts.in")
    logger.info("Mode: Scrapes individual job pages for FULL details")
    logger.info("Schedule: Every hour")
    logger.info("=" * 70)
    
    # Run every hour
    schedule.every(1).hour.do(job_scheduler)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
