import time
import random
import pandas as pd
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import os


from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

from faster_whisper import WhisperModel

# ================= CONFIG =================
NUM_DRIVERS = 5
SAVE_EVERY = 20
MAX_RETRIES = 3
CHECKPOINT_FILE = "checkpoint.csv"
INPUT_FILE = "ladakh_taxpayer.xlsx"
OUTPUT_FILE = "gst_results.csv"

# ================= GLOBALS =================
checkpoint_lock = Lock()
global_results = []
global_counter = 0

# ================= MODEL =================
model = WhisperModel("base.en", device="cuda", compute_type="float16")

# ================= UTILS =================
def chunkify(lst, n):
    return [lst[i::n] for i in range(n)]

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        df = pd.read_csv(CHECKPOINT_FILE)
        return df, set(df["GSTIN"].astype(str))
    return pd.DataFrame(), set()

# ================= CAPTCHA SOLVER =================
def solve_captcha(audio_bytes):
    try:
        audio_stream = BytesIO(audio_bytes)
        segments, _ = model.transcribe(audio_stream, beam_size=5, temperature=0,vad_filter=True)
        text = "".join(s.text for s in segments)
        digits = "".join(filter(str.isdigit, text))
        return digits
    except:
        return ""
    
def get_audio_bytes(driver):
    try:
        audio_data = driver.execute_script("""
    var audio = document.querySelector('audio');
    return fetch(audio.src)
      .then(res => res.arrayBuffer())
      .then(buf => Array.from(new Uint8Array(buf)));
""")

        audio_bytes = bytes(audio_data)
        return audio_bytes

    except Exception as e:
        print(e)
        return None

# ================= CORE FUNCTION ============
def process_gstin(driver, gstin):
    result = {
        "GSTIN": gstin,
        "Business Name": "Error",
        "Status": "Error",
        "Address": "Error"
    }

    driver.get("https:")

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "for_gstin"))
    ).send_keys(gstin)

    for attempt in range(MAX_RETRIES):
        try:
            # click audio
            play_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[ng-click='play()']"))
            )
            driver.execute_script("arguments[0].click();", play_btn)

            time.sleep(3)

            audio_bytes = get_audio_bytes(driver)
            if not audio_bytes:
                continue

            captcha = solve_captcha(audio_bytes)
            #print(f"[{gstin}] Attempt {attempt+1} → {captcha}")

            if len(captcha) != 6:
                driver.find_element(By.XPATH, "//button[@ng-click='refreshCaptcha()']").click()
                time.sleep(1)
                continue

            
            captcha_box = driver.find_element(By.ID, "fo-captcha")
            captcha_box.clear()
            captcha_box.send_keys(captcha)

            driver.find_element(By.ID, "lotsearch").click()

            # wait for either success OR error
            WebDriverWait(driver, 5).until(
                lambda d: d.find_elements(By.ID, "lottable") or
                          d.find_elements(By.CLASS_NAME, "error")
            )

            # SUCCESS CASE
            if driver.find_elements(By.ID, "lottable"):
                result["Business Name"] = driver.find_element(
                    By.XPATH, "//strong[contains(text(),'Legal Name')]/following::p[1]"
                ).text

                result["Status"] = driver.find_element(
                    By.XPATH, "//strong[contains(text(),'Status')]/following::p[1]"
                ).text

                result["Address"] = driver.find_element(
                    By.XPATH, "//strong[contains(text(),'Principal Place')]/following::p[1]"
                ).text

                return result

            # CAPTCHA FAILED → refresh
            else:
                print(f"[{gstin}] Invalid captcha, retrying...")
                driver.find_element(By.XPATH, "//button[@ng-click='refreshCaptcha()']").click()
                time.sleep(1)

        except Exception as e:
            print(f"[{gstin}] Error: {e}")
            try:
                driver.find_element(By.XPATH, "//button[@ng-click='refreshCaptcha()']").click()
            except:
                pass

    return result

# ================= WORKER'S MANAGING =================
def create_driver():
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-dev-shm-usage")

    return webdriver.Chrome(options=options)


def worker(gstin_chunk, worker_id):
    global global_results, global_counter

    driver = create_driver()
    print(f" Worker {worker_id} started")

    try:
        for gstin in gstin_chunk:
            result = process_gstin(driver, gstin)

            with checkpoint_lock:
                global_results.append(result)
                global_counter += 1

                if global_counter % SAVE_EVERY == 0:
                    pd.DataFrame(global_results).to_csv(CHECKPOINT_FILE, index=False)
                    print(f" Saved {global_counter}")

            time.sleep(random.uniform(1, 2))

    finally:
        try:
            driver.quit()
        except:
            pass

        print(f" Worker {worker_id} closed")

# ================= CLEANUP =================
def kill_chrome():
    os.system("taskkill /f /im chrome.exe >nul 2>&1")
    os.system("taskkill /f /im chromedriver.exe >nul 2>&1")

# ================= MAIN =================
def main():
    global global_results, global_counter

    df = pd.read_excel(INPUT_FILE)
    df["GSTIN"] = df["GSTIN"].astype(str)

    checkpoint_df, done = load_checkpoint()

    if not checkpoint_df.empty:
        global_results = checkpoint_df.to_dict("records")
        global_counter = len(global_results)

    pending = df[~df["GSTIN"].isin(done)]
    gstins = pending["GSTIN"].tolist()

    print(f"Remaining: {len(gstins)}")

    chunks = chunkify(gstins, NUM_DRIVERS)

    try:
        with ThreadPoolExecutor(max_workers=NUM_DRIVERS) as executor:
            executor.map(lambda args: worker(*args), [(c, i+1) for i, c in enumerate(chunks)])

    except KeyboardInterrupt:
        print("⚠ Interrupted! Saving progress...")

    finally:
        kill_chrome()

    result_df = pd.DataFrame(global_results)
    final_df = pd.merge(df, result_df, on="GSTIN", how="left", suffixes=("_old", "_new"))

    def compare(col):
        return final_df[f"{col}_old"].astype(str).str.strip() == final_df[f"{col}_new"].astype(str).str.strip()

    final_df["Name Match"] = compare("Business Name")
    final_df["Status Match"] = compare("Status")
    final_df["Address Match"] = compare("Address")

    final_df.to_csv(OUTPUT_FILE, index=False)
    print(" Completed and saved")


if __name__ == "__main__":
    main()
