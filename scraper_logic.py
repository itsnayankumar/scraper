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

def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True
    }
    try: requests.post(url, data=payload, timeout=10)
    except Exception as e: print(f"Telegram Error: {e}")

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def click_and_clean(driver, element, trace):
    """Clicks element and closes any new tabs that open."""
    original_window = driver.current_window_handle
    try:
        driver.execute_script("arguments[0].click();", element)
        trace.append("      -> Clicked element via JS.")
        time.sleep(2)
        
        if len(driver.window_handles) > 1:
            trace.append(f"      -> Detected {len(driver.window_handles)} tabs. Closing popups...")
            for window in driver.window_handles:
                if window != original_window:
                    driver.switch_to.window(window)
                    driver.close()
            driver.switch_to.window(original_window)
            trace.append("      -> Popups closed. Refocused main tab.")
            return False 
        return True 
    except Exception as e:
        trace.append(f"      -> Click failed: {str(e)}")
        return False

def resolve_10gbps_link(driver, link, trace):
    trace.append(f"    > Resolving 10Gbps link: {link}")
    original_window = driver.current_window_handle
    try:
        driver.switch_to.new_window('tab')
        driver.get(link)
        wait = WebDriverWait(driver, 30)
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Download Here')] | //button[contains(text(), 'Download Here')]")))
        
        for i in range(3):
            if click_and_clean(driver, btn, trace):
                if "drive" in driver.current_url or "google" in driver.current_url:
                    break
        
        final_link = driver.current_url
        driver.close()
        driver.switch_to.window(original_window)
        return final_link
    except:
        try: driver.close(); driver.switch_to.window(original_window)
        except: pass
        return link 

def resolve_page_data(initial_link, mediator_domain, hubdrive_domain, status_callback):
    driver = get_driver()
    trace = [] 
    data = { "filename": "Unknown Title", "size": "N/A", "links": [] }
    
    try:
        trace.append(f"Opening Link: {initial_link}")
        status_callback(f"Opening Link...")
        driver.get(initial_link)
        wait = WebDriverWait(driver, 30)
        
        if hubdrive_domain in driver.current_url or "HubDrive" in driver.title:
            trace.append("Detected HubDrive.")
            status_callback("HubDrive found...")
            try:
                hubcloud_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'HubCloud Server')]")))
                link = hubcloud_btn.get_attribute('href')
                trace.append(f"Found HubCloud button. Redirecting to: {link}")
                driver.get(link)
            except Exception as e:
                trace.append(f"HubDrive Error: {e}")

        if mediator_domain in driver.current_url or "Mediator" in driver.title:
            trace.append("Detected Mediator Page.")
            status_callback("Mediator found. Waiting for Timer...")
            
            try:
                xpath = "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')] | //a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]"
                trace.append("Waiting for 'Continue' button to be clickable...")
                continue_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                trace.append("Button became clickable. Waiting 1.5s for JS...")
                time.sleep(1.5)
                
                status_callback("Timer done. Clicking...")
                
                clicked_through = False
                for i in range(1, 4):
                    trace.append(f"Attempt {i}: Clicking Continue Button...")
                    driver.execute_script("arguments[0].click();", continue_btn)
                    time.sleep(2)
                    
                    if len(driver.window_handles) > 1:
                        trace.append(f"  > Popup detected! Closing it.")
                        driver.switch_to.window(driver.window_handles[1])
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    
                    curr_url = driver.current_url
                    trace.append(f"  > Current URL: {curr_url}")
                    
                    if "hubcloud" in curr_url or "drive" in curr_url:
                        trace.append("  > Success! Redirected to HubCloud.")
                        clicked_through = True
                        break
                    else:
                        trace.append("  > Still on Mediator. Retrying...")
                
                if not clicked_through:
                    trace.append("WARNING: Failed to pass Mediator after 3 clicks.")
            
            except Exception as e:
                trace.append(f"Mediator Error: {e}")

        if "hubcloud" in driver.current_url or "drive" in driver.current_url:
            trace.append("Landed on HubCloud.")
            status_callback("HubCloud found. Extracting...")
            
            try:
                try:
                    size_elem = driver.find_element(By.XPATH, "//td[contains(text(), 'File Size')]/following-sibling::td")
                    data["size"] = size_elem.text.strip()
                except: pass

                try:
                    name_elem = driver.find_element(By.CLASS_NAME, "card-header")
                    data["filename"] = name_elem.text.strip()
                except: pass

                generate_btn = wait.until(EC.presence_of_element_located((By.ID, "download")))
                trace.append("Found Generate Button. Clicking...")
                driver.execute_script("arguments[0].click();", generate_btn)
                
                trace.append("Waiting for server list...")
                wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Download [')]")))
                
                buttons = driver.find_elements(By.XPATH, "//a[contains(., 'Download [')]")
                trace.append(f"Found {len(buttons)} server buttons.")
                
                for btn in buttons:
                    txt = btn.text
                    lnk = btn.get_attribute('href')
                    name = txt.replace("Download", "").replace("[", "").replace("]", "").strip()
                    
                    if "10gbps" in txt.lower():
                        res_lnk = resolve_10gbps_link(driver, lnk, trace)
                        data["links"].append({"name": name, "url": res_lnk})
                    else:
                        data["links"].append({"name": name, "url": lnk})
            except Exception as e:
                trace.append(f"HubCloud Error: {e}")

    except Exception as e:
        trace.append(f"CRITICAL FAILURE: {str(e)}")
        data["error"] = str(e)
    finally:
        driver.quit()
        
    return data, trace

def format_message(data):
    msg = f"<b>┎ 📚 Title :-</b> <code>{data['filename']}</code>\n<b>┃</b>\n<b>┠ 💾 Size :-</b> {data['size']}\n<b>┃</b>\n"
    for i, link in enumerate(data['links']):
        prefix = "┖" if i == len(data['links']) - 1 else "┠"
        msg += f"<b>{prefix} 🔗 {link['name']} :-</b> <a href='{link['url']}'>Link</a>\n"
        if prefix == "┠": msg += "<b>┃</b>\n"
    msg += f"\n━━━━━━━✦✗✦━━━━━━━\n\n<b>Requested By :-</b> {REQUESTED_BY}"
    return msg

def run_scraper(base_url, mediator_domain, hubdrive_domain, bot_token, chat_id, seen_history, status_callback, log_callback):
    new_items = []
    try:
        status_callback(f"Scanning Homepage: {base_url}")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(base_url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
        posts = soup.select('.latest-releases .movie-card')

        for post in posts[:2]: 
            title = post.select_one('.movie-card-title').get_text(strip=True)
            link = post['href']
            if link.startswith('/'): link = base_url.rstrip('/') + link
            if title in seen_history: continue
            
            page_data, trace = resolve_page_data(link, mediator_domain, hubdrive_domain, status_callback)
            
            if page_data["links"]:
                if page_data["filename"] == "Unknown Title":
                   page_data["filename"] = title
                
                send_telegram(bot_token, chat_id, format_message(page_data))
                new_items.append(title)
                log_callback(f"Sent: {title}")
            else:
                failure_reason = " | ".join(trace[-3:])
                log_callback(f"Failed {title}: {failure_reason}")
                
    except Exception as e:
        log_callback(f"Critical Error: {str(e)}", True)
    return new_items
