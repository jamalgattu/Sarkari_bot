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

def extract_last_date(text):
    """Extract last date from text like 'Last Date: 11 Apr 2026'"""
    match = re.search(r'Last Date:\s*(\d{1,2}\s+\w+\s+\d{4})', text, re.I)
    if match:
        return match.group(1)
    return 'Check official website'

def extract_salary(text):
    """Extract salary from text"""
    # Look for patterns like "₹14,411" or "Salary ₹14,411"
    match = re.search(r'[₹$][\d,]+', text)
    if match:
        return match.group(0)
    # Look for salary range
    match = re.search(r'Salary\s*[₹$]?([\d,\-\s]+)', text, re.I)
    if match:
        return f"₹{match.group(1)}"
    return 'As per norms'

def extract_org_and_vacancies(text):
    """Extract organization and vacancies"""
    # Pattern: "Org: Railway" or "State: Uttar Pradesh"
    org_match = re.search(r'(?:Org|Organization|State|Ministry|Department):\s*([^\n]+)', text, re.I)
    org = org_match.group(1).strip() if org_match else 'Government'
    
    # Pattern: "Vacancy: 2801"
    vac_match = re.search(r'Vacancy:\s*(\d+)', text, re.I)
    vacancies = vac_match.group(1) if vac_match else ''
    
    return clean_text(org), vacancies

def check_if_today(update_date):
    """Check if job was updated today"""
    try:
        # Pattern: "Updated on 15 Mar 2026"
        match = re.search(r'Updated on\s+(\d{1,2}\s+\w+\s+\d{4})', update_date, re.I)
        if match:
            date_str = match.group(1)
            posted_date = datetime.strptime(date_str, '%d %b %Y').strftime('%Y-%m-%d')
            today = datetime.now().strftime('%Y-%m-%d')
            return posted_date == today
    except:
        pass
    # If no date found, include it anyway
    return True

def scrape_govtjobsalerts():
    """Scrape govtjobsalerts.in for latest jobs"""
    jobs = []
    
    try:
        logger.info("📡 Scraping govtjobsalerts.in...")
        
        url = "https://www.govtjobsalerts.in"
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=20)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all job containers - they are divs with job-post class or similar structure
            # Based on screenshot, each job is in a bordered container
            job_containers = soup.find_all('div', class_=re.compile(r'job|post|card|item', re.I))
            
            if not job_containers:
                # Alternative: find by structure - JOB POST button + title + details
                job_containers = soup.find_all('div', limit=100)
            
            logger.info(f"  Scanning {len(job_containers)} potential containers...")
            
            for container in job_containers:
                try:
                    # Look for title (usually h2 or h3 or a tag with blue color)
                    title_elem = container.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'title|heading|job', re.I))
                    
                    if not title_elem:
                        # Try to find any link in the container
                        title_elem = container.find('a')
                    
                    if not title_elem:
                        continue
                    
                    title_text = clean_text(title_elem.get_text())
                    
                    # Must contain job keywords
                    job_keywords = ['recruitment', 'notification', 'exam', 'vacancy', 'apply', 'admit', 'post', 'job']
                    if not any(kw in title_text.lower() for kw in job_keywords):
                        continue
                    
                    # Get the link
                    link_elem = container.find('a', href=True)
                    if not link_elem:
                        continue
                    
                    official_link = link_elem.get('href', '')
                    if not official_link or not official_link.startswith('http'):
                        continue
                    
                    # Get full container text for details extraction
                    container_text = container.get_text()
                    
                    # Extract details
                    last_date = extract_last_date(container_text)
                    salary = extract_salary(container_text)
                    org, vacancies = extract_org_and_vacancies(container_text)
                    
                    # Extract update date to check if posted today
                    is_today = check_if_today(container_text)
                    
                    # Extract eligibility from title or details
                    eligibility = 'Check official website'
                    # Sometimes eligibility is in the title
                    if 'iti' in title_text.lower():
                        eligibility = 'ITI Pass'
                    elif '12th' in title_text.lower():
                        eligibility = '12th Pass'
                    elif 'graduation' in title_text.lower() or 'degree' in title_text.lower():
                        eligibility = 'Bachelor\'s Degree'
                    
                    if is_today:
                        job = {
                            'id': clean_text(official_link),  # Use link as unique ID
                            'title': title_text[:250],
                            'organization': org,
                            'vacancies': vacancies,
                            'eligibility': eligibility,
                            'salary': salary,
                            'last_date': last_date,
                            'link': official_link
                        }
                        
                        # Avoid duplicates
                        if not any(j['link'] == official_link for j in jobs):
                            jobs.append(job)
                            logger.info(f"  ✓ {title_text[:50]}...")
                
                except Exception as e:
                    logger.debug(f"  Error: {e}")
                    continue
            
            logger.info(f"  ✓ Total: {len(jobs)} jobs from today")
        else:
            logger.warning(f"  Status: {response.status_code}")
    
    except Exception as e:
        logger.error(f"  Error: {str(e)[:50]}")
    
    return jobs

def create_message(job):
    """Create professional job post"""
    
    message = f"""
📢 <b>{job['title']}</b>

🏢 <b>Organization:</b> {job['organization']}
📌 <b>Vacancies:</b> {job['vacancies']}
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
    logger.info("🤖 GOVT JOBS ALERT - LATEST JOBS ONLY")
    logger.info("=" * 70)
    
    posted = load_posted_jobs()
    logger.info(f"✓ Cache: {len(posted)} jobs")
    
    jobs = scrape_govtjobsalerts()
    
    if not jobs:
        logger.warning("⚠️ No jobs found")
        return
    
    logger.info(f"✓ Checking {len(jobs)} jobs")
    
    count = 0
    for job in jobs:
        if job['id'] not in posted:
            logger.info(f"📤 {job['title'][:40]}...")
            msg = create_message(job)
            success = await send_to_channel(msg)
            
            if success:
                save_posted_job(job['id'])
                count += 1
                await asyncio.sleep(1)
    
    logger.info(f"✓ Posted: {count} NEW jobs")
    logger.info("=" * 70)

def job_scheduler():
    asyncio.run(check_and_post_jobs())

def main():
    logger.info("🚂 BOT STARTED")
    logger.info("Source: govtjobsalerts.in")
    logger.info("Posts: Latest jobs only (updated today)")
    logger.info("=" * 70)
    
    schedule.every(5).minutes.do(job_scheduler)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
