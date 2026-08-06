from selenium import webdriver # browser automation
from selenium.webdriver.chrome.options import Options # adding preferences to chrome driver (i.e block images etc)
from selenium.webdriver.common.by import By # to locate element from the webpages 
from selenium.webdriver.support.ui import WebDriverWait # for handling slow websites 
from selenium.webdriver.support import expected_conditions as EC # handling crashes (locating the element presence and clicking element)
from selenium.common.exceptions import WebDriverException # error class
import pandas as pd 
import os # file handling
import re # regex (for locating specific keywords)
import time # for limiting the request speed 
import csv # for saving the data in csv format
from bs4 import BeautifulSoup # for parsing the html data
import json # for saving the data in json format


def create_driver():
    """Setting up the chrome driver with specific options to run in headless mode to optimize time"""
    options = Options()
    # run in headless mode (background) without opening a physical browser window
    options.add_argument("--headless=new")
    # save memory and cpu usage
    options.add_argument("--disable-gpu")
    # bypass os security
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # speed up page load times by blocking all image content from downloading
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    return webdriver.Chrome(options=options)

# fucntion for navigating to district zones and locating to FPS web page
def navigate_to_district(driver, url, zone_name):
    """
    Executes the full 4-step sequence to reach a district's FPS list page cleanly:
    URL -> Click GOA -> Click District (e.g. SOUTH GOA) -> Click FAIR PRICE SHOPS
    """
    driver.get(url) # website link (dynamically changes month and year as per search needs)

    # 1 click GOA on main map
    goa_element = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//a[contains(@title, 'GOA')] | //img[contains(@aria-label, 'GOA')]"))
    )
    driver.execute_script("arguments[0].click();", goa_element)

    # verify are we on the right page or not 
    WebDriverWait(driver, 10).until(
        EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".status.m_menu"), "GOA")
    )

    # click specific District Zone (NORTH GOA or SOUTH GOA)
    zone_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, f"//a[@title='{zone_name}'] | //a[@aria-label='{zone_name}']"))
    )
    onclick_script = zone_element.get_attribute("onclick")
    driver.execute_script(onclick_script if onclick_script else "arguments[0].click();", zone_element)

    # click FAIR PRICE SHOPS link after locating to specific zone
    fair_price_shop = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//a[contains(@onclick, 'liveFpsdata')]"))
    )
    driver.execute_script(fair_price_shop.get_attribute("onclick"))

    # extract all FPS links
    fps_list_container = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "ul.menu")))
    fps_elements = fps_list_container.find_elements(By.CSS_SELECTOR, "li.menu_list a") # get all the fps codes which is in html element li.menu_list
    
    # get all the FPS links and their corresponding onclick actions and text
    fps_actions = [
        (elem.get_attribute("onclick"), elem.text.strip()) # creates a tuple of (onclick action, text) for each FPS element
        for elem in fps_elements 
        if elem.get_attribute("onclick") # only include elements that have an onclick attribute (filter out any non-clickable elements)
    ]
    
    return fps_actions

# -- MAIN  --
years = [2026] #  Specific year
months = [3, 4] # month (march and april)
goa_zones = ['NORTH GOA', 'SOUTH GOA'] # zones in goa 


driver = create_driver()
session_start_time = time.time()  # Track session age for every 15 min refresh

for year in years: # loop over year (2026) 
    for month in months: #loop over month (march and april)

        # website link (dynamically changes month and year as per search needs)
        url = f"https://impds.nic.in/sale/stateUnautmated?month={month}&year={year}#"

        # loop over north zone and then follwed by south zone
        for zone_name in goa_zones:
            formatted_zone = zone_name.replace(" ", "_") # chnge the name from NORTH GOA TO NORTH_GOA (for folder)
            """
            Create a new folder
            data /
            |---raw/
            |------year_month (2026_3)/
            |-------------------------/NORTH_GOA
            |------------------------------------/....FPS RAW DATA
            """
            folder_path = f"data/raw/{year}-{int(month):02d}/{formatted_zone.lower()}"
            os.makedirs(folder_path, exist_ok=True)

            # Step 1 NAVIGATE TO DISTRICT PAGE 
            fps_actions = [] # create a list to store all the fps code 
            while not fps_actions: # if not in fps code , get the data 
                try:
                    print(f"\nNavigating to {zone_name} ({int(month)}/{year})...")
                    fps_actions = navigate_to_district(driver, url, zone_name) # function call 
                # If Chrome session runs out or faces any error     
                except (WebDriverException, Exception) as nav_err: 
                    print(f"Page navigation failed for {zone_name}. Rebooting Chrome... ({nav_err})")
                    try:
                        driver.quit() # quit the chrome driver 
                    except Exception:
                        pass
                    driver = create_driver() # again restart the chrome drive 

            total_fps = len(fps_actions) #total fps
            print(f"Extracting {total_fps} items for {zone_name} ({int(month)}/{year})...")
            start_time = time.time()

            # -- STEP 2 LOOP THROUGH ALL FPS ITEMS WITH AUTO RECOVERY --

            """
            this script is loops through a list of text actions, extracts a unique identification number (id)
            from each action using a regular expression (regex), and sets up a unique html file path to save data for each item
            fps_action (list containing all the fps code)

            """
            # index holds the current iteration count (1-based), action holds the onclick script for the current FPS item
            for index, (action, full_text) in enumerate(fps_actions, start=1):

                # extract target ID from sidebar link text (e.g. 158500100001)
                check_fps_id = re.search(r"^(\d+)", full_text)
                target_fps_id = check_fps_id.group(1)
        
                # Regex to extract the shop name 
                name_match = re.search(r":\s*([^-]+)", full_text) # match name and return the name
                raw_name = name_match.group(1).strip() if name_match else full_text

                # clean up the shop name (remove dots, slashes, punctuation, convert to lowercase underscores)
                clean_name = re.sub(r"[^\w\s]", "", raw_name)  # rmeove \ from name ( M/s -> M S)
                fps_name = "_".join(clean_name.lower().split())  # "smt_sanna_sanjay_padte" ( M S -> ms)

                # save the file 
                target_file = f"{folder_path}/{target_fps_id}_{fps_name}.json"

                # Skip downloaded files
                if os.path.exists(target_file):
                    continue

                # Timer for refressing website every 15 min for meomoy free up and to speed up 
                if time.time() - session_start_time > 900:  # 900 seconds = 15 minutes
                    print("\n[Timer] 15 minutes elapsed. Rebooting Chrome to keep session fresh")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = create_driver()
                    session_start_time = time.time()
                    try:
                        navigate_to_district(driver, url, zone_name)
                    except Exception as refresh_err:
                        print(f"Failed to restore district position during 15-min refresh: {refresh_err}")

                # Execute click and save logic using target_file...
                success = False # flag to indicate if the current item was downloaded successfully
                attempts = 0 # counter to track the number of attempts made to download the current item

                while not success and attempts < 3:
                    try:
                        # execute the javascript action to switch to the target FPS
                        driver.execute_script(action)

                        # Wait up to 10 seconds for span.counter_num4 text to match target_fps_id to avoid frequent mismatch and reboting the drive
                        WebDriverWait(driver, 10).until(
                            EC.text_to_be_present_in_element(
                                (By.CSS_SELECTOR, "span.counter_num4"), target_fps_id
                            )
                        )

                        # parse live page DOM with BeautifulSoup
                        soup = BeautifulSoup(driver.page_source, "html.parser")

                        # direct metadata extraction
                        cal_text = soup.find("li", id="calModal").text.strip() # get the month and year from the calModal element
                        page_month, page_year = cal_text.split("-") # separate month and year from the calModal element

                        state = ( soup.find("div", {"key": "state"}).text.replace("\n", "").strip()) # get the state name
                        district = (soup.find("div", {"key": "district"}).text.replace("\n", "").strip()) # get the district name

                        # Extract the FPS ID currently displayed on the webpage
                        extracted_fps_id = soup.find("span", class_="counter_num4").text.strip() # get the fps id from the counter_num4 element
                        extracted_fps_name = soup.find("span", class_="counter_num3").text.strip() # get the fps name from the counter_num3 element

                        # Verify that the web page actually updated to the target FPS ID (Classic webpage scraping bug fix)
                        # add a wait time so that atleast page loads properly before it verifies to avoid frequent DOM
                        if extracted_fps_id != target_fps_id:
                            raise Exception(
                                f"Stale DOM detected! Expected FPS '{target_fps_id}', but page still displays '{extracted_fps_id}'. "
                                f"Internet drop or failed AJAX load."
                            )

                        # extract summary cards
                        summary_cards = {
                            # total number of e-transactions
                            "total_etransaction": soup.select_one(".nav-block-greenlight .counter")
                            .text.strip()
                            .replace(",", ""),

                            # total number of aadhaar authenticated transactions
                            "aadhaar_authenticated": soup.select_one(".nav-block-green .counter")
                            .text.strip()
                            .replace(",", ""),

                            # total number of other mode authenticated transactions
                            "other_mode_authenticated": soup.select_one(".nav-light-pink .counter")
                            .text.strip()
                            .replace(",", ""),

                            # total number of non-authenticated transactions
                            "non_authenticated": soup.select_one(".nav-light-purple .counter")
                            .text.strip()
                            .replace(",", ""),
                        }

                        # function to parse table rows matrix
                        def parse_table_data(css_selector):
                            rows_list = []
                            table = soup.select_one(css_selector)
                            if table:
                                for tr in table.select("tbody tr, tfoot tr"):
                                    cells = tr.find_all(["td", "th"])
                                    if len(cells) >= 5:
                                        raw_label = (
                                            cells[0]
                                            .text.replace("+", "")
                                            .replace("-", "")
                                            .strip()
                                        )
                                        clean_label = re.sub(r"\s+", " ", raw_label)
                                        rows_list.append({
                                            "row_label": clean_label,
                                            "regular": cells[1].text.strip().replace(",", ""),
                                            "intra_state": cells[2]
                                            .text.strip()
                                            .replace(",", ""),
                                            "inter_state": cells[3]
                                            .text.strip()
                                            .replace(",", ""),
                                            "total": cells[4].text.strip().replace(",", ""),
                                        })
                            return rows_list

                        # fps record object to store all the data in a single json file
                        fps_record = {
                            "year": page_year,
                            "month": page_month,
                            "state": state,
                            "district": district,
                            "fps_id": extracted_fps_id,
                            "fps_name": extracted_fps_name,
                            "summary_cards": summary_cards,
                            "number_of_transactions": parse_table_data("table.state-rep0"),
                            "number_of_transacted_ration_cards": parse_table_data(
                                "table.state-rep2"
                            ),
                            "distributed_quantity_kg": parse_table_data("table.state-rep1"),
                        }

                        # save JSON file named after the specific FPS ID
                        json_filename = f"{target_file}"
                        with open(json_filename, "w", encoding="utf-8") as f:
                            json.dump(fps_record, f, indent=2, ensure_ascii=False)

                        print(
                            f"Successfully extracted & saved data for FPS ID {extracted_fps_id} to {json_filename}"
                        )
                        success = True  # Move to next FPS

                    # Session reboot error handling
                    except (WebDriverException, Exception) as err:
                        attempts += 1
                        print(
                            f"Session dropped at {zone_name} item {index}/{total_fps}. Rebooting (Attempt {attempts})... Error: {err}"
                        )
                        try:
                            driver.quit()
                        except Exception:
                            pass

                        # Full reboot & re-navigate back to district
                        driver = create_driver()
                        try:
                            navigate_to_district(driver, url, zone_name)
                        except Exception as restore_err:
                            print(f"Failed to restore district position: {restore_err}")

            # Task Complete for the current zone
            print(f"Finished {zone_name} in {round(time.time() - start_time, 2)}s!")

try:
    driver.quit() # final step quit the chrome driver
except Exception:
    pass