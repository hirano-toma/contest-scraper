import streamlit as st
import re
import csv
import io
import html as html_module
import urllib.request
import urllib.error

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

STAGE_MAP = {
    "1": "一次審査", "2": "一次審査",
    "3": "二次審査", "4": "二次審査",
    "5": "三次審査", "6": "三次審査",
    "7": "ファイナル", "8": "グランプリ",
}


def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def normalize_sns(platform: str, value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value.split("?")[0].rstrip("/")
    handle = value.lstrip("@")
    if platform == "twitter":
        return f"https://x.com/{handle}"
    elif platform == "instagram":
        return f"https://www.instagram.com/{handle}"
    elif platform == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    elif platform == "showroom":
        return f"https://www.showroom-live.com/r/{handle}" if handle else ""
    return value


def parse_entries(html: str):
    html = html_module.unescape(html)

    title_match = re.search(r"<title>([^<|]+)", html)
    page_title = title_match.group(1).strip() if title_match else "不明"

    pattern = re.compile(
        r'"entry_id":\[0,"(?P<entry_id>[^"]+)"\],'
        r'"name":\[0,"(?P<name>[^"]+)"\],'
        r'"name_kana":\[0,"(?P<name_kana>[^"]+)"\],'
        r'"hometown":\[0,"(?P<hometown>[^"]+)"\],'
        r'"birthday":\[0,"(?P<birthday>[^"]+)"\],'
        r'"university":\[0,"(?P<university>[^"]+)"\],'
        r'"awards":\[1,\[[^\]]*\]\],'
        r'"block":\[0,"(?P<block>[^"]*?)"\],'
        r'.*?'
        r'"twitter":\[0,"(?P<twitter>[^"]*?)"\],'
        r'"instagram":\[0,"(?P<instagram>[^"]*?)"\],'
        r'"tiktok":\[0,"(?P<tiktok>[^"]*?)"\],'
        r'"mysta":\[0,"(?P<mysta>[^"]*?)"\],'
        r'"showroom":\[0,"(?P<showroom>[^"]*?)"\],'
        r'"stage":\[0,(?P<stage>\d+)\]',
        re.DOTALL,
    )

    entries = []
    for m in pattern.finditer(html):
        d = m.groupdict()
        stage_name = STAGE_MAP.get(d.get("stage", ""), f"審査{d.get('stage','')}")
        entries.append({
            "エントリーID": d.get("entry_id", ""),
            "名前": d.get("name", ""),
            "名前(かな)": d.get("name_kana", ""),
            "大学": d.get("university", ""),
            "出身": d.get("hometown", ""),
            "グループ": d.get("block", ""),
            "審査": stage_name,
            "X(Twitter)": normalize_sns("twitter", d.get("twitter", "")),
            "Instagram": normalize_sns("instagram", d.get("instagram", "")),
            "TikTok": normalize_sns("tiktok", d.get("tiktok", "")),
            "SHOWROOM": normalize_sns("showroom", d.get("showroom", "")),
        })
    return entries, page_title


def to_csv_bytes(entries):
    fieldnames = [
        "エントリーID", "名前", "名前(かな)", "大学", "出身",
        "グループ", "審査", "X(Twitter)", "Instagram", "TikTok", "SHOWROOM",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(entries)
    return buf.getvalue().encode("utf-8-sig")


# --- UI ---
st.set_page_config(page_title="コンテストリスト抽出", page_icon="🏆", layout="wide")
st.title("🏆 コンテストリスト抽出")
st.caption("ミスコン・コンテストサイトから候補者のSNS情報を一括取得します")

url = st.text_input("サイトのURLを入力", placeholder="https://2026.frecam.jp/list/2")

if st.button("取得する", type="primary", disabled=not url):
    with st.spinner("データを取得中..."):
        try:
            html = fetch_page(url)
            entries, page_title = parse_entries(html)

            if not entries:
                st.error("エントリーデータが見つかりませんでした。URLを確認してください。")
            else:
                st.success(f"**{page_title}** から **{len(entries)} 件** 取得しました")

                # グループ別集計
                from collections import Counter
                blocks = Counter(e["グループ"] for e in entries)
                cols = st.columns(len(blocks))
                for col, (block, count) in zip(cols, sorted(blocks.items())):
                    col.metric(f"グループ {block}", f"{count} 人")

                st.divider()

                # テーブル表示
                import pandas as pd

                df = pd.DataFrame(entries)

                # SNS列をリンク付きで表示
                def make_link(url):
                    return f'<a href="{url}" target="_blank">{url}</a>' if url else ""

                display_df = df.copy()
                for col in ["X(Twitter)", "Instagram", "TikTok", "SHOWROOM"]:
                    display_df[col] = display_df[col].apply(make_link)

                st.write(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)

                st.divider()

                # CSV ダウンロード
                csv_bytes = to_csv_bytes(entries)
                filename = re.sub(r"[^\w]", "_", page_title) + ".csv"
                st.download_button(
                    label="CSVダウンロード",
                    data=csv_bytes,
                    file_name=filename,
                    mime="text/csv",
                )
                st.caption("ダウンロードしたCSVはGoogleスプレッドシートにそのままインポートできます")

        except urllib.error.HTTPError as e:
            st.error(f"HTTP エラー {e.code}: ページが見つかりません。URLを確認してください。")
        except urllib.error.URLError as e:
            st.error(f"接続エラー: {e.reason}")
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
