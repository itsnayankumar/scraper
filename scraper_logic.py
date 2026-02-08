import requests
from bs4 import BeautifulSoup
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    try: requests.post(url, data=payload)
    except Exception as e: print(f"Telegram Error: {e}")

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Essential for Docker
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def resolve_10gbps_link(driver, link, status_callback):
    status_callback("    > Resolving 10Gbps link...")
    original_window = driver.current_window_handle
    try:
        driver.switch_to.new_window('tab')
        driver.get(link)
        wait = WebDriverWait(driver, 30)
        # Wait for "Download Here" button
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Download Here')] | //button[contains(text(), 'Download Here')]")))
        final_link = btn.get_attribute('href')
        driver.close()
        driver.switch_to.window(original_window)
        return final_link
    except:
        try: driver.close(); driver.switch_to.window(original_window)
        except: pass
        return link 

def resolve_all_mirrors(initial_link, mediator_domain, hubdrive_domain, status_callback):
    driver = get_driver()
    final_results = []
    
    try:
        status_callback(f"  > Opening Link...")
        driver.get(initial_link)
        wait = WebDriverWait(driver, 30)
        
        # --- HUBDRIVE PHASE ---
        if hubdrive_domain in driver.current_url or "HubDrive" in driver.title:
            status_callback("  > HubDrive found. Redirecting...")
            try:
                hubcloud_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'HubCloud Server')]")))
                driver.get(hubcloud_btn.get_attribute('href'))
            except: pass

        # --- MEDIATOR PHASE ---
        if mediator_domain in driver.current_url or "Mediator" in driver.title:
            status_callback("  > Mediator found. Waiting for Timer...")
            # Wait for "Please Wait" to become "Continue"
            continue_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'CLICK TO CONTINUE')] | //a[contains(text(), 'CLICK TO CONTINUE')]")))
            time.sleep(1)
            status_callback("  > Timer done. Clicking Continue...")
            driver.execute_script("arguments[0].click();", continue_btn)
            wait.until(lambda d: "hubcloud" in d.current_url or "drive" in d.current_url)

        # --- HUBCLOUD PHASE ---
        if "hubcloud" in driver.current_url or "drive" in driver.current_url:
            status_callback("  > HubCloud found. Generating links...")
            generate_btn = wait.until(EC.element_to_be_clickable((By.ID, "download")))
            driver.execute_script("arguments[0].click();", generate_btn)
            
            status_callback("  > Waiting for server list...")
            wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Download [')]")))
            
            buttons = driver.find_elements(By.XPATH, "//a[contains(., 'Download [')]")
            status_callback(f"  > Found {len(buttons)} mirrors. extracting...")
            
            for btn in buttons:
                txt = btn.text
                lnk = btn.get_attribute('href')
                name = txt.replace("Download", "").replace("[", "").replace("]", "").strip()
                
                if "10gbps" in txt.lower():
                    res_lnk = resolve_10gbps_link(driver, lnk, status_callback)
                    final_results.append(f"🔴 <b>{name}:</b> {res_lnk}")
                else:
                    final_results.append(f"🔹 <b>{name}:</b> {lnk}")
    except Exception as e:
        final_results.append(f"Error: {str(e)}")
    finally:
        driver.quit()
        
    return final_results

def run_scraper(base_url, mediator_domain, hubdrive_domain, bot_token, chat_id, seen_history, status_callback, log_callback):
    new_items = []
    
    try:
        status_callback(f"Scanning Homepage: {base_url}")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(base_url, headers=headers)
        soup = BeautifulSoup(resp.text, 'html.parser')
        posts = soup.select('.latest-releases .movie-card')

        # Limit to top 2 posts per run to prevent timeout
        for post in posts[:2]: 
            title = post.select_one('.movie-card-title').get_text(strip=True)
            link = post['href']
            
            if title in seen_history: continue
            
            log_callback(f"Found new post: {title}")
            status_callback(f"Processing: {title}")
            
            p_resp = requests.get(link, headers=headers)
            p_soup = BeautifulSoup(p_resp.text, 'html.parser')
            boxes = p_soup.select('.episode-content, .season-content, .download-item')
            
            found_ep = False
            for box in boxes:
                fname_tag = box.select_one('code, .episode-file-title')
                if not fname_tag: continue
                fname = fname_tag.get_text(strip=True)
                
                buttons = box.select('a.btn')
                for btn in buttons:
                    b_text = btn.get_text(strip=True).lower()
                    if 'hubcloud' in b_text or 'hubdrive' in b_text:
                        mirrors = resolve_all_mirrors(btn.get('href'), mediator_domain, hubdrive_domain, status_callback)
                        if mirrors:
                            msg = f"📂 <b>{fname}</b>\n\n" + "\n".join(mirrors)
                            send_telegram(bot_token, chat_id, msg)
                            found_ep = True
            
            if found_ep:
                new_items.append(title)
                log_callback(f"Sent to Telegram: {title}")
            else:
                log_callback(f"Skipped {title} (No valid links)")
                
    except Exception as e:
        log_callback(f"Critical Error: {str(e)}", True)
        
    return new_items
