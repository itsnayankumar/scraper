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

# --- CONFIGURATION ---
REQUESTED_BY = "HDHub Bot 🤖"

# --- TELEGRAM SENDER ---
def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id, 
        'text': message, 
        'parse_mode': 'HTML', 
        'disable_web_page_preview': True
    }
    try: requests.post(url, data=payload, timeout=10)
    except Exception as e: print(f"Telegram Error: {e}")

# --- BROWSER SETUP ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Anti-Bot Detection Features
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# --- HELPER: HANDLE ADS & POPUPS ---
def click_and_clean(driver, element):
    """Clicks an element and closes any ad tabs that open."""
    original_window = driver.current_window_handle
    
    # 1. Attempt Click
    try:
        driver.execute_script("arguments[0].click();", element)
        time.sleep(2) # Wait for potential ad to trigger
    except:
        return False

    # 2. Check for new tabs (Pop-ups)
    if len(driver.window_handles) > 1:
        for window in driver.window_handles:
            if window != original_window:
                driver.switch_to.window(window)
                driver.close()
        driver.switch_to.window(original_window)
        return False # Click was consumed by ad, need to retry

    # 3. Check if we were redirected to a bogus URL in the same tab
    # (Simple check: if URL is very long or suspicious, we go back)
    # For now, we assume if we are still on the same domain, it failed
    return True

# --- HELPER: 10GBPS RESOLVER ---
def resolve_10gbps_link(driver, link, status_callback):
    status_callback("    > Resolving 10Gbps link...")
    original_window = driver.current_window_handle
    try:
        driver.switch_to.new_window('tab')
        driver.get(link)
        wait = WebDriverWait(driver, 30)
        
        # Click "Download Here" with Ad-Busting
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Download Here')] | //button[contains(text(), 'Download Here')]")))
        
        # Try up to 3 times
        for _ in range(3):
            click_and_clean(driver, btn)
            if "drive" in driver.current_url or "google" in driver.current_url or "mega" in driver.current_url:
                break # Success
        
        final_link = driver.current_url
        # If still on the button page, try grabbing href directly
        if final_link == link:
            final_link = btn.get_attribute('href')

        driver.close()
        driver.switch_to.window(original_window)
        return final_link
    except:
        try: driver.close(); driver.switch_to.window(original_window)
        except: pass
        return link 

# --- MAIN PAGE RESOLVER ---
def resolve_page_data(initial_link, mediator_domain, hubdrive_domain, status_callback):
    driver = get_driver()
    data = {
        "filename": "Unknown Title",
        "size": "N/A",
        "links": []
    }
    
    try:
        status_callback(f"  > Opening Link...")
        driver.get(initial_link)
        wait = WebDriverWait(driver, 30)
        
        # --- PHASE 1: HUBDRIVE ---
        if hubdrive_domain in driver.current_url or "HubDrive" in driver.title:
            status_callback("  > HubDrive found. Clicking HubCloud...")
            try:
                # Scrape Size
                try:
                    size_elem = driver.find_element(By.XPATH, "//td[contains(text(), 'File Size')]/following-sibling::td")
                    data["size"] = size_elem.text.strip()
                except: pass
                
                # Click HubCloud Server
                hubcloud_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'HubCloud Server')]")))
                driver.get(hubcloud_btn.get_attribute('href'))
            except: pass

        # --- PHASE 2: MEDIATOR (AD BUSTER ADDED) ---
        if mediator_domain in driver.current_url or "Mediator" in driver.title:
            status_callback("  > Mediator found. Waiting for Timer...")
            
            # Wait for "Continue"
            xpath = "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')] | //a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]"
            continue_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            time.sleep(1.5) # Let JS settle
            
            status_callback("  > Timer done. Clicking (Anti-Ad Mode)...")
            
            # Try clicking up to 3 times to kill ads
            for i in range(3):
                # Check if we moved on
                if "hubcloud" in driver.current_url or "drive" in driver.current_url:
                    break
                
                # Perform Click & Clean
                driver.execute_script("arguments[0].click();", continue_btn)
                time.sleep(2)
                
                # Handle New Tab Ads
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[1])
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    status_callback(f"  > Ad Tab Closed. Retrying click {i+2}...")

            # Final Wait
            wait.until(lambda d: "hubcloud" in d.current_url or "drive" in d.current_url)

        # --- PHASE 3: HUBCLOUD ---
        if "hubcloud" in driver.current_url or "drive" in driver.current_url:
            status_callback("  > HubCloud found. Generating...")
            
            # Scrape Info if missing
            try:
                if data["size"] == "N/A":
                    size_elem = driver.find_element(By.XPATH, "//td[contains(text(), 'File Size')]/following-sibling::td")
                    data["size"] = size_elem.text.strip()
                name_elem = driver.find_element(By.CLASS_NAME, "card-header")
                data["filename"] = name_elem.text.strip()
            except: pass

            # Click Generate (Ad-Buster)
            generate_btn = wait.until(EC.presence_of_element_located((By.ID, "download")))
            
            # Try clicking up to 2 times
            for _ in range(2):
                driver.execute_script("arguments[0].click();", generate_btn)
                time.sleep(1)
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[1])
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                
                # Check if server list appeared
                if len(driver.find_elements(By.XPATH, "//a[contains(., 'Download [')]")) > 0:
                    break

            status_callback("  > Extracting mirrors...")
            buttons = driver.find_elements(By.XPATH, "//a[contains(., 'Download [')]")
            
            for btn in buttons:
                txt = btn.text
                lnk = btn.get_attribute('href')
                name = txt.replace("Download", "").replace("[", "").replace("]", "").strip()
                
                if "10gbps" in txt.lower():
                    res_lnk = resolve_10gbps_link(driver, lnk, status_callback)
                    data["links"].append({"name": name, "url": res_lnk})
                else:
                    data["links"].append({"name": name, "url": lnk})
                    
    except Exception as e:
        data["error"] = str(e)
    finally:
        driver.quit()
        
    return data

# --- MESSAGE FORMATTER ---
def format_message(data):
    title = data["filename"]
    size = data["size"]
    links = data["links"]
    
    msg = f"<b>┎ 📚 Title :-</b> <code>{title}</code>\n"
    msg += "<b>┃</b>\n"
    msg += f"<b>┠ 💾 Size :-</b> {size}\n"
    msg += "<b>┃</b>\n"
    
    total_links = len(links)
    for i, link in enumerate(links):
        is_last = (i == total_links - 1)
        prefix = "┖" if is_last else "┠"
        msg += f"<b>{prefix} 🔗 {link['name']} :-</b> <a href='{link['url']}'>Link</a>\n"
        if not is_last: msg += "<b>┃</b>\n"

    msg += "\n━━━━━━━✦✗✦━━━━━━━\n\n"
    msg += f"<b>Requested By :-</b> {REQUESTED_BY}"
    return msg

# --- MAIN SCRAPER ---
def run_scraper(base_url, mediator_domain, hubdrive_domain, bot_token, chat_id, seen_history, status_callback, log_callback):
    new_items = []
    
    try:
        status_callback(f"Scanning Homepage: {base_url}")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(base_url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
        posts = soup.select('.latest-releases .movie-card')

        for post in posts[:2]: 
            title_tag = post.select_one('.movie-card-title')
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            link = post['href']
            
            if link.startswith('/'): link = base_url.rstrip('/') + link
            if title in seen_history: continue
            
            log_callback(f"Found new post: {title}")
            status_callback(f"Processing: {title}")
            
            p_resp = requests.get(link, headers=headers, timeout=20)
            p_soup = BeautifulSoup(p_resp.text, 'html.parser')
            boxes = p_soup.select('.episode-content, .season-content, .download-item')
            
            found_ep = False
            for box in boxes:
                buttons = box.select('a.btn')
                for btn in buttons:
                    b_text = btn.get_text(strip=True).lower()
                    if 'hubcloud' in b_text or 'hubdrive' in b_text:
                        
                        page_data = resolve_page_data(btn.get('href'), mediator_domain, hubdrive_domain, status_callback)
                        
                        if page_data["links"]:
                            if page_data["filename"] == "Unknown Title":
                                fname_tag = box.select_one('code, .episode-file-title')
                                if fname_tag: page_data["filename"] = fname_tag.get_text(strip=True)

                            final_msg = format_message(page_data)
                            send_telegram(bot_token, chat_id, final_msg)
                            found_ep = True
            
            if found_ep:
                new_items.append(title)
                log_callback(f"Sent: {title}")
            else:
                log_callback(f"Skipped {title} (No links)")
                
    except Exception as e:
        log_callback(f"Critical Error: {str(e)}", True)
        
    return new_items
