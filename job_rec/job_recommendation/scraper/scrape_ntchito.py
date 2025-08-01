import psycopg2
from datetime import datetime
import logging
import asyncio
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Database connection configuration
DB_CONFIG = {
    "dbname": "job_recommendation",
    "user": "postgres",
    "password": "Mwaah2004.",
    "host": "localhost",
    "port": "5432"
}

# Proxy configuration (optional)
PROXY = None  # Example: "http://api.scraperapi.com?api_key=YOUR_API_KEY"

async def scrape_ntchito():
    base_url = "https://ntchito.com/jobs/"
    jobs = []
    
    # Set up Selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.7103.94 Safari/537.36")
    if PROXY:
        chrome_options.add_argument(f"--proxy-server={PROXY}")
    
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        for page in range(1, 3):
            url = f"{base_url}page/{page}/" if page > 1 else base_url
            logger.info(f"Scraping ntchito.com page: {url}")
            
            for attempt in range(3):
                try:
                    driver.get(url)
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "article.job_listing"))
                    )
                    page_source = driver.page_source
                    logger.debug(f"ntchito.com page source (first 500 chars): {page_source[:500]}")
                    
                    soup = BeautifulSoup(page_source, "html.parser")
                    job_elements = soup.select("article.job_listing")
                    logger.info(f"Found {len(job_elements)} potential job elements on page {page}")
                    
                    for job in job_elements:
                        try:
                            job_html = str(job)[:300]
                            logger.debug(f"Job element HTML: {job_html}")
                            
                            title_elem = job.find("h2", class_="entry-title")
                            location_elem = job.find("div", class_="company-address")
                            job_type_elem = job.find("li", class_="job-type")
                            url_elem = job.find("h2", class_="entry-title").find("a") if job.find("h2", class_="entry-title") else None
                            
                            company = "N/A"
                            date_posted = datetime.now().strftime("%Y-%m-%d")
                            job_url = url_elem["href"] if url_elem and url_elem.get("href") else ""
                            
                            # Scrape job description and skills from detail page
                            description = ""
                            skills = ""
                            if job_url:
                                try:
                                    driver.get(job_url)
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.job-description, div.content, div.entry-content"))
                                    )
                                    detail_source = driver.page_source
                                    detail_soup = BeautifulSoup(detail_source, "html.parser")
                                    
                                    # Extract description
                                    desc_elem = detail_soup.select_one("div.job-description, div.content, div.entry-content")
                                    description = desc_elem.text.strip() if desc_elem else "N/A"
                                    logger.info(f"Scraped description for {job_url} (length: {len(description)} chars)")
                                    
                                    # Extract skills
                                    skills_elem = detail_soup.select_one("ul.skills, div.requirements, div.qualifications")
                                    if skills_elem:
                                        skills_list = [li.text.strip() for li in skills_elem.find_all("li")] or [skills_elem.text.strip()]
                                        skills = ",".join([s for s in skills_list if s])
                                    else:
                                        # Fallback: Extract skills from description using regex
                                        skills_match = re.search(r"Skills: ([^.]*)", description, re.IGNORECASE)
                                        if skills_match:
                                            skills = skills_match.group(1).replace("and", ",").strip()
                                        else:
                                            skills = "N/A"
                                    logger.info(f"Scraped skills for {job_url}: {skills}")
                                    
                                    await asyncio.sleep(2)  # Delay to avoid bot detection
                                except Exception as e:
                                    logger.warning(f"Failed to scrape details for {job_url}: {e}")
                                    description = "N/A"
                                    skills = "N/A"
                            
                            if title_elem and location_elem and url_elem:
                                job_data = {
                                    "title": title_elem.text.strip(),
                                    "company": company,
                                    "location": location_elem.text.strip(),
                                    "job_type": job_type_elem.text.strip() if job_type_elem else "N/A",
                                    "date_posted": date_posted,
                                    "url": job_url,
                                    "source": "ntchito.com",
                                    "description": description,
                                    "skills": skills
                                }
                                jobs.append(job_data)
                                logger.info(f"Parsed job: {job_data['title']}")
                            else:
                                logger.warning(f"Skipping job due to missing elements: title={bool(title_elem)}, location={bool(location_elem)}, url={bool(url_elem)}")
                                logger.debug(f"Skipped job HTML: {job_html}")
                        except AttributeError as e:
                            logger.warning(f"Failed to parse job element: {e}")
                            logger.debug(f"Error job HTML: {job_html}")
                            continue
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                    if attempt == 2:
                        logger.error(f"All attempts to scrape {url} failed")
                        break
                    await asyncio.sleep(5)
        
        # Save to database
        if jobs:
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cursor = conn.cursor()
                inserted = 0
                for job in jobs:
                    try:
                        cursor.execute("""
                            INSERT INTO jobs (title, company, location, job_type, date_posted, url, source, description)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (url) DO NOTHING
                        """, (job["title"], job["company"], job["location"], job["job_type"], job["date_posted"], job["url"], job["source"], job["description"]))
                        if cursor.rowcount == 0:
                            logger.debug(f"Skipped duplicate job: {job['url']}")
                        else:
                            inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert job {job['url']}: {e}")
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"Saved {inserted} jobs from ntchito.com to database")
            except Exception as e:
                logger.error(f"Failed to save jobs to database: {e}")
        else:
            logger.warning("No jobs scraped from ntchito.com")
        
        return jobs
    
    except Exception as e:
        logger.error(f"Selenium scraping failed for ntchito.com: {e}")
        return []
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    asyncio.run(scrape_ntchito())