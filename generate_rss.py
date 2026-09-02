#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SMBC China Monthly RSSフィード生成スクリプト（簡易版）
日付抽出をスキップし、現在日時を公開日として使用
"""

import os
import re
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from feedgen.feed import FeedGenerator
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 設定
BASE_URL = "https://www.smbc.co.jp/hojin/international/monthly.html"
PDF_BASE_URL = "https://www.smbc.co.jp"
OUTPUT_RSS_FILE = "smbc_china_monthly.xml"
TIMEZONE_JST = timezone(timedelta(hours=9))


def setup_driver():
    """Selenium WebDriverの設定"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def fetch_page_with_selenium(url):
    """Seleniumを使用して動的コンテンツを含むページを取得"""
    driver = None
    try:
        driver = setup_driver()
        logger.info(f"ページを読み込み中: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        
        driver.implicitly_wait(5)
        html = driver.page_source
        logger.info("ページの読み込みが完了しました")
        return html
        
    except Exception as e:
        logger.error(f"ページ取得エラー: {e}")
        raise
    finally:
        if driver:
            driver.quit()


def parse_china_monthly(html):
    """HTMLからSMBC China Monthlyの記事一覧をパース（日付抽出スキップ）"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    now = datetime.now(TIMEZONE_JST)
    
    # メインのテーブルを探す
    tables = soup.find_all('table', class_='tableLiquid')
    
    for table in tables:
        tbody = table.find('tbody')
        if not tbody:
            continue
            
        rows = tbody.find_all('tr')
        for row in rows:
            item = parse_row(row, now)
            if item:
                items.append(item)
    
    # 項目数が多すぎる場合は制限
    if len(items) > 50:
        items = items[:50]
    
    logger.info(f"{len(items)}件の記事を取得しました")
    return items


def parse_row(row, default_date):
    """1行のデータをパース（日付はスキップ）"""
    try:
        th = row.find('th', class_='tableTitle01')
        if not th:
            return None
        
        # PDFリンクを抽出
        pdf_link = th.find('a', class_='glyphPdf01')
        pdf_url = None
        if pdf_link and pdf_link.get('href'):
            pdf_url = urljoin(PDF_BASE_URL, pdf_link.get('href'))
        
        # 日付情報を取得（表示用）
        date_text = th.get_text(strip=True)
        # 日付らしき文字列を抽出（表示用）
        date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', date_text)
        display_date = date_match.group(1) if date_match else "不明"
        
        # td要素からタイトルと説明を抽出
        td = row.find('td')
        if not td:
            return None
        
        # タイトル
        title_span = td.find('span', class_='dBlock')
        title = title_span.get_text(strip=True) if title_span else f"SMBC China Monthly ({display_date})"
        
        # 説明を構築
        description_parts = []
        sections = td.find_all('div', class_='iconText01')
        
        for section in sections:
            title_dt = section.find('dt', class_='title')
            content_dds = section.find_all('dd', class_='text')
            
            if title_dt:
                section_title = title_dt.get_text(strip=True)
                contents = []
                for content_dd in content_dds:
                    content_text = content_dd.get_text(strip=True)
                    if content_text:
                        contents.append(content_text)
                
                if contents:
                    description_parts.append(f"{section_title}: {' / '.join(contents)}")
        
        description = "\n".join(description_parts) if description_parts else title
        
        # guid
        if pdf_url:
            guid = pdf_url
        else:
            guid = f"smbc-china-monthly-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            'title': title,
            'link': pdf_url if pdf_url else BASE_URL,
            'description': description,
            'pub_date': default_date,  # 現在日時を使用
            'guid': guid,
            'pdf_url': pdf_url,
            'display_date': display_date,  # 表示用の日付
        }
        
    except Exception as e:
        logger.warning(f"行のパース中にエラーが発生しました: {e}")
        return None


def generate_rss(items, output_file):
    """RSSフィードを生成"""
    fg = FeedGenerator()
    fg.title('SMBC China Monthly')
    fg.link(href=BASE_URL, rel='alternate')
    fg.description('三井住友銀行の中国関連レポート China Monthly のRSSフィード')
    fg.language('ja')
    
    now = datetime.now(TIMEZONE_JST)
    fg.lastBuildDate(now)
    
    for item in items:
        fe = fg.add_entry()
        fe.title(item['title'])
        fe.link(href=item['link'], rel='alternate')
        
        if item['description']:
            fe.description(item['description'])
        
        # 公開日は現在日時を使用
        fe.pubDate(item['pub_date'])
        
        fe.guid(item['guid'], permalink=False)
    
    rss_str = fg.rss_str(pretty=True)
    
    with open(output_file, 'wb') as f:
        f.write(rss_str)
    
    logger.info(f"RSSフィードを生成しました: {output_file}")
    return output_file


def main():
    """メイン関数"""
    try:
        logger.info("SMBC China Monthly RSS生成を開始します（日付抽出スキップモード）")
        
        html = fetch_page_with_selenium(BASE_URL)
        items = parse_china_monthly(html)
        
        if not items:
            logger.warning("記事が見つかりませんでした")
            return
        
        rss_file = generate_rss(items, OUTPUT_RSS_FILE)
        logger.info(f"処理が完了しました: {rss_file}")
        logger.info(f"取得した記事数: {len(items)}件")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()
