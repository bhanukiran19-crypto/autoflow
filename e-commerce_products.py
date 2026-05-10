from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from tkinter import ttk
import tkinter as tk
from tkinter import messagebox
import threading
import time
import random
import csv


def scraper() :

    search = product_entry.get()
    min_price=min_entry.get()
    max_price=max_entry.get()

    if not search or not min_price or not max_price:
        messagebox.showerror("Error", "Please fill all fields")
        return

    status_label.config(text="Scraping started. Wait for a while...")
    progress['value'] = 0
    window.update_idletasks()



    url=f"https:///s?k={search}&low-price={min_price}&high-price={max_price}"

    options=Options()
    options.add_argument("--headless=new")

    wb=webdriver.Chrome(options=options)
    wb.get("")

    time.sleep(3)

    wb.get(url)

    total_products=[]
    while True :
        try :

            WebDriverWait(wb,8).until(EC.presence_of_all_elements_located((By.XPATH,"//div[@data-component-type='s-search-result']")))
        except :
            status_label.config(text="Slow Internet connection.try again...")
            continue
        time.sleep(12)
        raw_products=wb.find_elements(By.XPATH,"//div[@data-component-type='s-search-result']")
        print()
    
        
        for product in raw_products :

        
            try:
                desc=product.find_element(By.CSS_SELECTOR, "div[data-cy='title-recipe']")
                link=desc.find_element(By.TAG_NAME,"a").get_attribute("href")
                desc=desc.find_element(By.TAG_NAME,"span").text
            except :
                status_label.config(text="Slow internet connection")
                continue
        
            try:
                reviews=product.find_element(By.CSS_SELECTOR, "div[data-cy='reviews-block'] ")
                reviews=reviews.find_element(By.XPATH, "./div/span")
                reviews=reviews.text
            except :
                reviews="no reviews"
        
            try :
                price = product.find_element(By.CSS_SELECTOR, "div[data-cy='price-recipe'] span.a-price ")
                price=price.find_element(By.CLASS_NAME, "a-price-whole").text
                
            except :
                continue

            if "/dp/" in link :
                total_products.append([desc, int(price.replace(",","")), reviews, link])

        if len(wb.find_elements(By.XPATH,"//a[contains(@class,'s-pagination-next')]")) ==0 :
            break

        nxt=wb.find_element(By.XPATH,"//a[contains(@class,'s-pagination-next')]")
        wb.execute_script("arguments[0].scrollIntoView();", nxt)
        time.sleep(random.uniform(2,4))
        wb.execute_script("arguments[0].click();", nxt)
    
        window.after(0, lambda: progress.step(1))

    wb.close()

    filename=f"{search}_scraper.csv"

    with open(filename,"w",newline="", encoding="utf-8") as file :
        writer=csv.writer(file)
        writer.writerow(["description","price","reviews","link"])
        writer.writerows(total_products)
    status_label.config(text=f"Finished. {len(total_products)} products saved.")
    messagebox.showinfo("Done", f"Data saved to {filename}")



def run_thread():
    threading.Thread(target=scraper).start()

window = tk.Tk()
window.title("Product Scraper")
window.geometry("600x500")


main_frame = tk.Frame(window)
main_frame.place(relx=0.5, rely=0.5, anchor="center")


title = tk.Label(main_frame, text="Product Scraper", font=("Arial", 20))
title.grid(row=0, column=0, columnspan=2, pady=20)


tk.Label(main_frame, text="Product Name", font=("Arial", 14)).grid(row=1, column=0, padx=10, pady=10, sticky="e")
product_entry = tk.Entry(main_frame, width=30, font=("Arial", 13))
product_entry.grid(row=1, column=1, padx=10, pady=10)


tk.Label(main_frame, text="Min Price", font=("Arial", 14)).grid(row=2, column=0, padx=10, pady=10, sticky="e")
min_entry = tk.Entry(main_frame, width=30, font=("Arial", 13))
min_entry.grid(row=2, column=1, padx=10, pady=10)


tk.Label(main_frame, text="Max Price", font=("Arial", 14)).grid(row=3, column=0, padx=10, pady=10, sticky="e")
max_entry = tk.Entry(main_frame, width=30, font=("Arial", 13))
max_entry.grid(row=3, column=1, padx=10, pady=10)


start_button = tk.Button(main_frame, text="Start Scraping", command=run_thread, font=("Arial", 13))
start_button.grid(row=4, column=0, columnspan=2, pady=20)


status_label = tk.Label(main_frame, text="", fg="blue", font=("Arial", 14))
status_label.grid(row=5, column=0, columnspan=2)

progress = ttk.Progressbar(main_frame, orient="horizontal", length=300, mode="determinate")
progress.grid(row=6, column=0, columnspan=2, pady=10)
progress["maximum"] = 19
window.mainloop()
