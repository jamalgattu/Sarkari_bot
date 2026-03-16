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
    """Scrape individual job page for full details"""
    details = {
        'eligibility': 'Check official website',
        'salary': 'As per norms',
        'last_date': 'Check official website',
        'vacancies': ''
    }
    
    try:
        session = requests.Session()
        response = session.get(job_url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            logger.warning(f"      ⚠️ Could not scrape page (Status {response.status_code})")
            return details
        
        soup = BeautifulSoup(response.content, 'html.parser')
        page_text = soup.get_text()
        
        # Extract eligibility
        elig_patterns = [
            r'(?:Eligibility|Qualification|Education|Eligible):\s*([^\n]+)',
        ]
        for pattern in elig_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                details['eligibility'] = clean_text(match.group(1))[:80]
                break
        
        # Extract salary/stipend
        sal_patterns = [
            r'(?:Salary|Pay|Stipend|CTC|Pay Scale|Pay Level):\s*([₹$\d,\-\s.k+]+)',
            r'[₹][\d,]+(?:\s*(?:\+|-)\s*[₹]?[\d,]+)?',
        ]
        for pattern in sal_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                salary_text = match.group(0) if '\d' in match.group(0) else match.group(1)
                details['salary'] = clean_text(salary_text)[:80]
                break
        
        # Extract last date
        date_patterns = [
            r'(?:Last Date|Deadline|Apply Before|Application Deadline|Last Date to Apply):\s*(\d{1,2}[/-]?\s*\w+\s*[/-]?\s*\d{4}|\d{1,2}\s+\w+\s+\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                details['last_date'] = clean_text(match.group(1))[:30]
                break
        
        # Extract vacancies
        vac_match = re.search(r'(?:Vacancies|Total Vacancies|Posts?):\s*(\d+)', page_text, re.I)
        if vac_match:
            details['vacancies'] = vac_match.group(1)
        
        logger.info(f"      ✓ Scraped details successfully")
        return details
        
    except Exception as e:
        logger.warning(f"      ⚠️ Error scraping page: {str(e)[:40]}")
        return details

def get_top_5_jobs():
    """Get TOP 5 jobs from homepage"""
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
        
        # Find all links
        all_links = soup.find_all('a', href=True, limit=100)
        
        logger.info(f"  Found {len(all_links)} links, filtering for jobs...")
        
        job_count = 0
        
        for link in all_links:
            if job_count >= 5:  # ONLY TOP 5
                break
            
            try:
                title = clean_text(link.get_text())
                href = link.get('href', '').strip()
                
                # Basic validation
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
                job_keywords = ['recruitment', 'notification', 'exam', 'vacancy', 'apply', 'admit', 'post', 'job', 'bharti', 'resident', 'senior', 'vacancies']
                if not any(kw in title.lower() for kw in job_keywords):
                    continue
                
                # Check if already processed (in current batch)
                if href in [j['link'] for j in jobs]:
                    continue
                
                job_count += 1
                job = {
                    'title': title[:250],
                    'link': href,
                    'id': href,
                    'eligibility': 'Check official website',
                    'salary': 'As per norms',
                    'last_date': 'Check official website',
                    'vacancies': ''
                }
                jobs.append(job)
                logger.info(f"  {job_count}. {title[:60]}...")
        
        logger.info(f"  ✓ Found TOP 5 jobs")
        return jobs
        
    except Exception as e:
        logger.error(f"  Error: {str(e)[:50]}")
    
    return jobs

def create_message(job):
    """Create professional job post"""
    
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
    logger.info("🤖 GOVT JOBS ALERT - TOP 5 VACANCIES CHECK")
    logger.info("=" * 70)
    
    posted = load_posted_jobs()
    logger.info(f"✓ Already posted: {len(posted)} jobs\n")
    
    # Get TOP 5 jobs from homepage
    top_5_jobs = get_top_5_jobs()
    
    if not top_5_jobs:
        logger.warning("⚠️ No jobs found on homepage")
        return
    
    logger.info(f"\n✓ Checking TOP 5 jobs...\n")
    
    count = 0
    
    for i, job in enumerate(top_5_jobs, 1):
        logger.info(f"Job {i}/5: {job['title'][:50]}...")
        
        # Check if already posted
        if job['id'] in posted:
            logger.info(f"  ⏭️  SKIPPED - Already posted\n")
            continue
        
        logger.info(f"  ✅ NEW JOB - Scraping details...")
        
        # Scrape individual job page
        details = scrape_individual_job_page(job['link'])
        
        # Update job with scraped details
        job['eligibility'] = details['eligibility']
        job['salary'] = details['salary']
        job['last_date'] = details['last_date']
        job['vacancies'] = details['vacancies']
        
        # POST IT (even if details couldn't be scraped)
        logger.info(f"  📤 Posting to Telegram...")
        message = create_message(job)
        success = await send_to_channel(message)
        
        if success:
            save_posted_job(job['id'])
            count += 1
            logger.info(f"  ✓ Posted successfully\n")
            await asyncio.sleep(2)
        else:
            logger.error(f"  ✗ Failed to post\n")
    
    logger.info("=" * 70)
    if count == 0:
        logger.info("✓ No new jobs to post")
    else:
        logger.info(f"✓ Posted {count} NEW jobs! 🎉")
    logger.info("=" * 70)

def job_scheduler():
    asyncio.run(check_and_post_jobs())

def main():
    logger.info("🚂 BOT STARTED")
    logger.info("Mode: Check TOP 5 vacancies every hour")
    logger.info("Action: Post if not already posted")
    logger.info("=" * 70)
    
    # Run every hour
    schedule.every(1).hour.do(job_scheduler)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
