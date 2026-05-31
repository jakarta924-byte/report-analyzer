import streamlit as st
import requests, time
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

try:
    import FinanceDataReader as fdr
    FDR_OK = TrueS
except:
    FDR_OK = False

# ── 비밀번호 설정 ──────────────────────────────
PASSWORD = "1004"  # ← 원하는 비밀번호로 바꾸세요

def check_password():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.title('🔒 Brokerage Report Analyzer')
    pwd = st.text_input('Password', type='password', placeholder='비밀번호를 입력하세요')
    if st.button('Login'):
        if pwd == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error('비밀번호가 틀렸습니다')
    return False

if not check_password():
    st.stop()

# ── 이하 메인 앱 ───────────────────────────────
H = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/research/company_list.naver'}
URL = 'https://finance.naver.com/research/company_list.naver'
UP_KW   = ['상향', '목표주가 상향', 'TP 상향', '상향 조정', '올려', '높여']
DOWN_KW = ['하향', '목표주가 하향', 'TP 하향', '하향 조정', '낮춰']

def detect_change(title):
    for k in UP_KW:
        if k in title: return 'UP'
    for k in DOWN_KW:
        if k in title: return 'DOWN'
    return 'KEEP'

def make_stock_url(href):
    if not href: return ''
    if href.startswith('http'): return href
    if href.startswith('/'): return 'https://finance.naver.com' + href
    return 'https://finance.naver.com/' + href

def make_report_search_url(stock_name):
    encoded = requests.utils.quote(stock_name)
    return f'https://finance.naver.com/research/company_list.naver?keyword={encoded}'

def fetch(page):
    try:
        r = requests.get(URL, params={'page': page}, headers=H, timeout=10)
        r.encoding = 'euc-kr'
    except:
        return []
    soup = BeautifulSoup(r.text, 'html.parser')
    tbl = soup.find('table', class_='type_1')
    if not tbl: return []
    rows = []
    for tr in tbl.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) < 6: continue
        a = tds[0].find('a')
        if not a: continue
        stock_name = a.get_text(strip=True)
        stock_href = a.get('href', '')
        stock_url  = make_stock_url(stock_href)
        report_url = make_report_search_url(stock_name)
        title_tag  = tds[1].find('a')
        title = title_tag.get_text(strip=True) if title_tag else tds[1].get_text(strip=True)
        tp_raw = tds[3].get_text(strip=True).replace(',','').replace(' ','')
        try: tp = int(tp_raw)
        except: tp = None
        rows.append({
            'Stock':      stock_name,
            'Stock_URL':  stock_url,
            'Title':      title,
            'Report_URL': report_url,
            'Broker':     tds[2].get_text(strip=True),
            'Target':     tp,
            'Opinion':    tds[4].get_text(strip=True),
            'Date':       tds[5].get_text(strip=True),
            'Signal':     detect_change(title),
        })
    return rows

@st.cache_data(ttl=1800)
def load_data(pages=10):
    all_rows = []
    for p in range(1, pages+1):
        all_rows.extend(fetch(p))
        time.sleep(0.5)
    return pd.DataFrame(all_rows)

@st.cache_data(ttl=1800)
def load_prices(_names):
    prices = {}
    if not FDR_OK: return prices
    try:
        listing = fdr.StockListing('KRX')[['Name','Code']]
        name_to_code = dict(zip(listing['Name'], listing['Code']))
    except:
        return prices
    for name in _names:
        code = name_to_code.get(name)
        if not code: continue
        try:
            df = fdr.DataReader(code)
            if df is not None and not df.empty:
                prices[name] = int(df['Close'].iloc[-1])
        except:
            pass
        time.sleep(0.1)
    return prices

def color_direction(val):
    if 'UP'   in str(val): return 'background-color: #FFE5E5; color: #CC0000; font-weight: bold'
    if 'DOWN' in str(val): return 'background-color: #E5F0FF; color: #0000CC; font-weight: bold'
    return ''

def color_gap(val):
    try:
        v = float(val)
        if v >= 20: return 'color: #CC0000; font-weight: bold'
        if v >= 10: return 'color: #FF6600; font-weight: bold'
        if v < 0:   return 'color: #0000CC'
    except:
        pass
    return ''

st.set_page_config(page_title='Report Analyzer', page_icon='📈', layout='wide')
st.title('📈 Brokerage Report Analyzer')
st.caption(f'Source: Naver Finance | Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}')

with st.sidebar:
    st.header('Settings')
    pages = st.slider('Pages to collect', 1, 20, 10)
    if st.button('🔄 Refresh Data'):
        st.cache_data.clear()
        st.rerun()
    st.markdown('---')
    if st.button('🔓 Logout'):
        st.session_state.authenticated = False
        st.rerun()

with st.spinner('Collecting reports...'):
    df = load_data(pages)

with st.spinner('Collecting stock prices...'):
    prices = load_prices(tuple(df['Stock'].unique().tolist()))

df['Price']     = df['Stock'].map(prices)
df['Gap(%)']    = df.apply(
    lambda r: round((r['Target'] - r['Price']) / r['Price'] * 100, 1)
    if pd.notna(r['Target']) and pd.notna(r['Price']) and r['Price'] > 0 else None, axis=1
)
df['Direction'] = df['Signal'].map({'UP': '🔺 UP', 'DOWN': '🔻 DOWN', 'KEEP': '➖'})

tab1, tab2, tab3 = st.tabs(['🔺 Target Price Change', '🏢 Multiple Brokers', '📋 All Reports'])

with tab1:
    df_ud = df[df['Signal'] != 'KEEP'].copy()
    c1, c2 = st.columns(2)
    c1.metric('🔺 UP', f"{len(df_ud[df_ud['Signal']=='UP'])}")
    c2.metric('🔻 DOWN', f"{len(df_ud[df_ud['Signal']=='DOWN'])}")
    filt = st.radio('Filter', ['ALL', '🔺 UP only', '🔻 DOWN only'], horizontal=True)
    if filt == '🔺 UP only':
        df_ud = df_ud[df_ud['Signal'] == 'UP']
    elif filt == '🔻 DOWN only':
        df_ud = df_ud[df_ud['Signal'] == 'DOWN']
    df_ud = df_ud.sort_values('Gap(%)', ascending=False)
    show = [c for c in ['Stock','Stock_URL','Broker','Target','Price','Gap(%)','Direction','Date','Title','Report_URL'] if c in df_ud.columns]
    st.dataframe(
        df_ud[show].style
            .map(color_direction, subset=['Direction'])
            .map(color_gap, subset=['Gap(%)']),
        column_config={
            'Stock_URL':  st.column_config.LinkColumn('Stock Link'),
            'Report_URL': st.column_config.LinkColumn('Reports'),
        },
        use_container_width=True, height=500
    )

with tab2:
    mc_list = []
    for s, g in df.groupby('Stock'):
        if len(g) >= 2:
            avg_gap = g['Gap(%)'].mean()
            mc_list.append({
                'Stock':      s,
                'Stock_URL':  g['Stock_URL'].iloc[0],
                'Report_URL': make_report_search_url(s),
                'Count':      len(g),
                'Brokers':    ' / '.join(sorted(set(g['Broker']))),
                'Avg Target': round(g['Target'].mean(), 0) if g['Target'].notna().any() else None,
                'Price':      prices.get(s),
                'Avg Gap(%)': round(avg_gap, 1) if pd.notna(avg_gap) else None,
                'Latest':     g['Date'].max(),
            })
    df_mc = pd.DataFrame(sorted(mc_list, key=lambda x: x['Count'], reverse=True))
    st.metric('Multiple Broker Stocks', f'{len(df_mc)}')
    min_cnt = st.slider('Min broker count', 2, 5, 2)
    st.dataframe(
        df_mc[df_mc['Count'] >= min_cnt],
        column_config={
            'Stock_URL':  st.column_config.LinkColumn('Stock Link'),
            'Report_URL': st.column_config.LinkColumn('Reports'),
        },
        use_container_width=True, height=500
    )

with tab3:
    search = st.text_input('🔍 Search stock')
    df_all = df.copy()
    if search:
        df_all = df_all[df_all['Stock'].str.contains(search)]
    st.metric('Total Reports', f'{len(df_all)}')
    show_all = [c for c in ['Stock','Stock_URL','Broker','Target','Price','Gap(%)','Direction','Opinion','Date','Title','Report_URL'] if c in df_all.columns]
    st.dataframe(
        df_all[show_all],
        column_config={
            'Stock_URL':  st.column_config.LinkColumn('Stock Link'),
            'Report_URL': st.column_config.LinkColumn('Reports'),
        },
        use_container_width=True, height=500
    )
