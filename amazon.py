import requests as req
from bs4 import BeautifulSoup
import random
import math
from datetime import datetime as dt
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import os

import email, smtplib, ssl

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

wdir = os.path.dirname(os.path.realpath(__file__))

def get_mailconf():
    conf = {}
    for i, row in pd.read_csv(f"{wdir}/mailconf",header=None,names=["key","value"]).iterrows():
        conf[row["key"]] = row["value"]
    return conf

ids = pd.read_csv(f"{wdir}/products.txt")["id"].to_list()

filename = "price.png"
filecsv = f"{wdir}/{filename.replace('png','csv')}"
filepng = f"{wdir}/{filename}"

browser = ["Chrome", "Edge", "Firefox", "Opera", "Safari"]

patterns = [{"key":"class", "value":"a-size-base a-color-price a-color-price"},
            {"key":"id", "value":"priceblock_saleprice"},
            {"key":"class", "value":"a-size-medium a-color-price priceBlockBuyingPriceString"}]

def select_browser(browser):
    random.choice(browser)

def format_price(price):
    return price.strip('\n').strip(' €').replace(',','.')

def get_price_from_page(page):
    soup = BeautifulSoup(page.content,"html.parser")
    price = None
    for i in range(len(patterns)):
        if patterns[i]["key"] == "class":
            price = soup.find(class_=patterns[i]["value"])
        elif patterns[i]["key"] == "id":
            price = soup.find(id=patterns[i]["value"])
        if price != None:
            return float(format_price(price.get_text()))
    return math.nan

def get_title_from_page(page):
    soup = BeautifulSoup(page.content,"html.parser")
    title = soup.find(id="productTitle")
    if title != None:
        return title.get_text().strip('\n')
    else:
        return ""

def get_page(url):
    
    status_code = 900
    page = 0
    ntry = 0

    while status_code >= 400 and ntry <= 1000:
        page = req.get(url, headers={"user-agent":select_browser(browser)})
        status_code = page.status_code 
        ntry += 1
    
    return page

def get_url(id):
    return "https://www.amazon.it/dp/" + id

def get_info(id):    
    page = get_page(get_url(id))
    title = get_title_from_page(page)
    price = get_price_from_page(page)
    return title, price

def save_info_for_all(ids,filename):
    file = open(filename, "a", encoding="utf-8")

    for id in ids:
        title, price = get_info(id)
        file.write(f'{dt.now()}, {id}, "{title}", {price}\n')
        print(f"{id}: done")

    file.close()

def read_csv(filename):
    return pd.read_csv(filename,
        header=None,
        index_col=False,
        names=["time","id","title","price"],
        skipinitialspace=True,
        parse_dates=[0],
        dtype={"time":str, "id":str, "title":str, "price":float})

def get_reduced_df(df, id):
    return df[df["id"] == id]

def get_price_variation(rdf):
    price_time_ordered = rdf.sort_values(by='time')["price"]
    dp = 0
    if len(price_time_ordered)>1:
        dp = price_time_ordered.values[-1] - price_time_ordered.values[-2]
    return dp

def draw_subplot(rdf,npl,index):    
    plt.subplot(npl,1,index+1)
    plt.plot(rdf["time"],rdf["price"],
            color="b",
            label=rdf["title"].values[0])
    plt.xticks(rotation=20)
    plt.xlabel("time")
    plt.ylabel("price [euro]")
    plt.legend(loc='upper center', 
                ncol=1)

def check_price_variation(rdf,id,price_variations):
    dp = get_price_variation(rdf)
    if dp != 0 and not np.isnan(dp):
            price_variations[id] = dp

def draw_plot(ids,df,filepng):
    price_variations = {}

    nid = len(ids)
    plt.figure(figsize=(15,5*nid))

    for index in range(nid):
        rdf = get_reduced_df(df, ids[index])
        check_price_variation(rdf,ids[index],price_variations)
        draw_subplot(rdf,nid,index)

    plt.savefig(filepng)
    return price_variations

def get_message_body(df,price_variations):
    body = ""
    if len(price_variations) != 0:
        for id in price_variations:
            title = df[df["id"] == id]["title"].values[0]
            body += f"Title: {title}\t price variation: {price_variations[id]:.2f} euro\n"
    else:
        body = "No price variation"
    return body

def create_message(conf, 
                    subject, 
                    body):
    # Create a multipart message and set headers
    message = MIMEMultipart()
    message["From"] = conf["sender"]
    message["To"] = conf["receiver"]
    message["Subject"] = subject
    message["Bcc"] = conf["receiver"]  # Recommended for mass emails

    # Add body to email
    message.attach(MIMEText(body, "plain"))
    return message

def get_attachment(filepng,filename):
    # Open PDF file in binary mode
    with open(filepng, "rb") as attachment:
        # Add file as application/octet-stream
        # Email client can usually download this automatically as attachment
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())

    # Encode file in ASCII characters to send by email    
    encoders.encode_base64(part)

    # Add header as key/value pair to attachment part
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={filename}",
    )

    return part

def send_mail(conf, text):
    # Log in to server using secure context and send email
    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.bo.infn.it", 587) as server:
        server.ehlo()  # Can be omitted
        server.starttls(context=context)
        server.ehlo()  # Can be omitted
        server.login(conf["user"], conf["password"])
        server.sendmail(conf["sender"], conf["receiver"], text)

def process(ids, filecsv, filepng, conf):
    save_info_for_all(ids,filecsv)
    df = read_csv(filecsv)
    price_variations = draw_plot(ids,df,filepng)

    message = create_message(conf, 
                        "Monitor of the price of the books in Amazon", 
                        get_message_body(df,price_variations))

    message.attach(get_attachment(filepng,filename))

    send_mail(conf, message.as_string())

if __name__ == "__main__":
    mailconf = get_mailconf()
    process(ids, filecsv, filepng, mailconf)