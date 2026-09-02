#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SMBC China Monthly RSSフィード生成スクリプト
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

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

# ヘッダー
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
}


def fetch_page(url):
    """Requestsを使用してページを取得"""
    try:
        logger.info(f"ページを取得中: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        response.encoding = 'shift_jis'
        html = response.text
        logger.info(f"ページ取得完了: {len(html)} バイト")
        return html
    except requests.exceptions.RequestException as e:
        logger.error(f"ページ取得エラー: {e}")
        raise


def extract_date_from_th(th_element):
    """
    th要素から日付を抽出する
    例: th要素のテキストに "2026.8.18" が含まれている場合
    """
    # th要素内のテキストを取得（改行を含む）
    text = th_element.get_text()
    
    # 改行で分割して各行をチェック
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 日付パターン: YYYY.M.D または YYYY.MM.DD
        match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', line)
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)
            except ValueError:
                continue
    
    # 直接テキストからも再試行（改行コードが混ざっている場合）
    clean_text = re.sub(r'\s+', ' ', text.strip())
    match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', clean_text)
    if match:
        try:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return datetime(year, month, day)
        except ValueError:
            pass
    
    return None


def parse_china_monthly(html):
    """HTMLからSMBC China Monthlyの記事一覧をパース"""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # メインのテーブルを探す
    tables = soup.find_all('table', class_='tableLiquid')
    
    for table in tables:
        tbody = table.find('tbody')
        if not tbody:
            continue
        
        rows = tbody.find_all('tr')
        for row in rows:
            item = parse_row(row)
            if item:
                items.append(item)
    
    # 日付でソート（新しい順）
    items.sort(key=lambda x: x['pub_date'], reverse=True)
    
    logger.info(f"{len(items)}件の記事を取得しました")
    return items


def parse_row(row):
    """1行のデータをパース"""
    try:
        th = row.find('th', class_='tableTitle01')
        if not th:
            return None
        
        # 日付を抽出
        pub_date = extract_date_from_th(th)
        if not pub_date:
            logger.debug(f"日付抽出失敗: {th.get_text()[:50]}")
            return None
        
        pub_date = pub_date.replace(tzinfo=TIMEZONE_JST)
        
        # PDFリンクを抽出
        pdf_link = th.find('a', class_='glyphPdf01')
        pdf_url = None
        if pdf_link and pdf_link.get('href'):
            pdf_url = urljoin(PDF_BASE_URL, pdf_link.get('href'))
        
        # td要素からタイトルと説明を抽出
        td = row.find('td')
        if not td:
            return None
        
        # タイトル
        title_span = td.find('span', class_='dBlock')
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            # タイトルがない場合は日付から作成
            title = f"SMBC China Monthly ({pub_date.strftime('%Y年%m月')})"
        
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
            guid = f"smbc-china-monthly-{pub_date.strftime('%Y%m%d')}"
        
        return {
            'title': title,
            'link': pdf_url if pdf_url else BASE_URL,
            'description': description,
            'pub_date': pub_date,
            'guid': guid,
            'pdf_url': pdf_url,
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
    
    for item in items[:50]:
        fe = fg.add_entry()
        fe.title(item['title'])
        fe.link(href=item['link'], rel='alternate')
        
        if item['description']:
            fe.description(item['description'])
        
        # 実際の公開日を使用
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
        logger.info("SMBC China Monthly RSS生成を開始します")
        
        html = fetch_page(BASE_URL)
        items = parse_china_monthly(html)
        
        if not items:
            logger.warning("記事が見つかりませんでした")
            return
        
        rss_file = generate_rss(items, OUTPUT_RSS_FILE)
        logger.info(f"処理が完了しました: {rss_file}")
        logger.info(f"取得した記事数: {len(items)}件")
        
        # 最初の数件の日付を表示（デバッグ用）
        for i, item in enumerate(items[:5]):
            logger.info(f"  {i+1}. {item['pub_date'].strftime('%Y-%m-%d')} - {item['title'][:30]}...")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()
