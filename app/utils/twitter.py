from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

logger = logging.getLogger(__name__)

async def get_twitter_followers():
    """
    Scrape Twitter followers count from SwifeyAI profile
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get('https://x.com/SwifeyAi')
        
        # Wait for the followers element to be present
        followers_xpath = '/html/body/div[1]/div/div/div[2]/main/div/div/div/div/div/div[3]/div/div/div/div/div[5]/div[2]/a/span[1]/span'
        followers_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, followers_xpath))
        )
        
        followers_count = followers_element.text
        driver.quit()
        
        # Convert text to number (remove 'K' if present and multiply by 1000)
        if 'K' in followers_count:
            followers_count = float(followers_count.replace('K', '')) * 1000
        return int(float(followers_count))
    except Exception as e:
        logger.error(f"Error scraping Twitter followers: {e}")
        return None
    finally:
        if 'driver' in locals():
            driver.quit() 