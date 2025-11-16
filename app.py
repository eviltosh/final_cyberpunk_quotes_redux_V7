def run_app():
    import streamlit as st

    # ------------------------------------------------------------------
    # Ensure page config is the first Streamlit call
    # ------------------------------------------------------------------
    st.set_page_config(page_title="Cyberpunk Stock Tracker", page_icon="💹", layout="wide")

    # ------------------------------------------------------------------
    # Imports (no Streamlit UI calls here)
    # ------------------------------------------------------------------
    import streamlit.components.v1 as components
    import yfinance as yf
    import requests
    from io import BytesIO
    from PIL import Image
    import datetime
    import time
    import pandas as pd
    import plotly.graph_objects as go
    from pathlib import Path
    import base64

    # ------------------------------------------------------------------
    # Helper: safe st.markdown wrapper to avoid accidental reassignment
    # ------------------------------------------------------------------
    def safe_markdown(html: str):
        # Use st.markdown directly; keep wrapper to centralize calls
        st.markdown(html, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # TRANSPARENCY + BASIC CSS (applied after page config)
    # ------------------------------------------------------------------
    safe_markdown("""
    <style>
    html, body, [data-testid="stBody"], [data-testid="stApp"],
    [data-testid="stAppViewContainer"], [data-testid="stMain"],
    section.main, .block-container { background: transparent !important; }

    .block-container { padding-top: 0rem !important; }

    .stApp > div[style] { position: relative; z-index: 1; }
    </style>
    """)

    # ------------------------------------------------------------------
    # Load external cyberpunk CSS if available, otherwise use a minimal fallback
    # ------------------------------------------------------------------
    css_path = Path("cyberpunk_style_embedded.css")
    if css_path.exists():
        try:
            with css_path.open("r", encoding="utf-8") as fh:
                safe_markdown(f"<style>{fh.read()}</style>")
        except Exception:
            # fail silently; fallback provided below
            pass
    else:
        safe_markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Major+Mono+Display&display=swap');
        .cyberpunk-title { font-family: 'Major Mono Display', monospace; font-size:58px; color:#00eaff; text-align:center; letter-spacing:2px; text-shadow:0 0 8px rgba(0,234,255,0.9),0 0 18px rgba(0,128,170,0.25); position:relative; top:-25px; margin-bottom:6px; }
        .news-card { background: rgba(0,0,0,0.35); padding:8px; border-radius:8px; margin-bottom:8px; }
        .card { background: linear-gradient(180deg, rgba(0,0,0,0.45), rgba(0,0,0,0.25)); border-radius:10px; padding:12px; border:1px solid rgba(0,234,255,0.08); }
        </style>
        """)

    # ------------------------------------------------------------------
    # VIDEO BACKGROUND: try local file first, then fallback to GitHub URL
    # ------------------------------------------------------------------
    def try_embed_local_video(path: Path) -> bool:
        try:
            if path.exists():
                data = path.read_bytes()
                b64 = base64.b64encode(data).decode()
                safe_markdown(f"""
                <video autoplay muted loop playsinline style="position:fixed;top:0;left:0;width:100vw;height:100vh;object-fit:cover;z-index:-1;">
                    <source src="data:video/mp4;base64,{b64}" type="video/mp4">
                </video>
                """)
                return True
        except Exception:
            pass
        return False

    video_embedded = try_embed_local_video(Path("videos/cyberpunk_light.mp4"))
    if not video_embedded:
        # GitHub release fallback; use components.html to avoid large markup inside st.markdown
        components.html("""
        <video autoplay loop muted playsinline style="position:fixed;top:0;left:0;width:100vw;height:100vh;object-fit:cover;z-index:-1;">
            <source src="https://github.com/eviltosh/final_cyberpunk_quotes_redux_V4/releases/download/v1.0/cyberpunk_light.mp4" type="video/mp4">
        </video>
        """, height=0, width=0)

    # ------------------------------------------------------------------
    # Sidebar controls
    # ------------------------------------------------------------------
    st.sidebar.header("⚙️ Controls")
    tickers_input = st.sidebar.text_input("Enter stock tickers (comma-separated):", "AAPL, TSLA, NVDA")
    period = st.sidebar.selectbox("Select time range:", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"])
    refresh_rate = st.sidebar.slider("Auto-refresh interval (seconds):", 10, 300, 60)

    st.sidebar.subheader("🔑 API Keys")
    finnhub_api = st.sidebar.text_input("Finnhub API key", value="", type="password")

    st.sidebar.subheader("🌅 Chart Background")
    bg_choice = st.sidebar.selectbox("Select Background Image:", ["Beach 1", "Beach 2", "Classic", "Upload Your Own"])
    uploaded_bg = None
    if bg_choice == "Upload Your Own":
        uploaded_bg = st.sidebar.file_uploader("Upload a background image", type=["jpg", "jpeg", "png"])

    bg_image = None
    if uploaded_bg is not None:
        try:
            bg_image = Image.open(uploaded_bg)
        except Exception:
            bg_image = None
    else:
        try:
            if bg_choice == "Beach 1":
                bg_image = Image.open("images/1.jpg")
            elif bg_choice == "Beach 2":
                bg_image = Image.open("images/2.jpg")
            else:
                bg_image = None
        except Exception:
            bg_image = None

    # ------------------------------------------------------------------
    # Title (with one extra line above and two below as requested)
    # ------------------------------------------------------------------
    safe_markdown("""
    <br>
    <div style='text-align:center;'>
        <h1 class='cyberpunk-title'>CYBERPUNK QUOTES</h1>
        <br><br>
    </div>
    """)

    # ------------------------------------------------------------------
    # Tickers list and auto-refresh
    # ------------------------------------------------------------------
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = time.time()
    else:
        if time.time() - st.session_state["last_refresh"] > refresh_rate:
            st.session_state["last_refresh"] = time.time()
            st.experimental_rerun()

    # ------------------------------------------------------------------
    # Cached helpers
    # ------------------------------------------------------------------
    @st.cache_data(ttl=3600)
    def get_stock_data(ticker: str, period: str):
        try:
            return yf.Ticker(ticker).history(period=period)
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def get_info_cached(ticker: str):
        try:
            return yf.Ticker(ticker).get_info()
        except Exception:
            return {}

    @st.cache_data(ttl=1800)
    def get_company_news(symbol: str, api_key: str):
        if not api_key:
            return []
        FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"
        today = datetime.date.today()
        past = today - datetime.timedelta(days=30)
        params = {"symbol": symbol, "from": past.isoformat(), "to": today.isoformat(), "token": api_key}
        try:
            response = requests.get(FINNHUB_NEWS_URL, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [item for item in data if item.get("headline") and item.get("url")]
        except Exception:
            pass
        return []

    # ------------------------------------------------------------------
    # Rendering helpers (extract large blocks out of the main loop)
    # ------------------------------------------------------------------

    def render_company_header(info: dict, ticker: str):
        # safe logo retrieval
        logo_url = info.get("logo_url")
        if not logo_url:
            domain = info.get("website", "").replace("https://", "").replace("http://", "").split("/")[0]
            if domain:
                logo_url = f"https://logo.clearbit.com/{domain}"

        cols = st.columns([1, 4])
        col_logo, col_meta = cols[0], cols[1]
        with col_logo:
            if logo_url:
                try:
                    r = requests.get(logo_url, timeout=5)
                    if r.status_code == 200:
                        st.image(Image.open(BytesIO(r.content)), width=100)
                except Exception:
                    # ignore logo errors
                    pass
        with col_meta:
            st.markdown(f"### {info.get('shortName', ticker)}")
            st.caption(f"{info.get('sector', 'N/A')} | {info.get('industry', 'N/A')}")

    def render_matplotlib_cyberpunk_chart(hist: pd.DataFrame, ticker: str, bg_image):
        # This function confines matplotlib imports and rendering to one place
        try:
            import matplotlib.pyplot as plt
            import mplcyberpunk
        except Exception:
            return False

        plt.style.use("cyberpunk")
        fig, ax = plt.subplots(figsize=(10, 5))

        # Transparent figure & axes to let video show through
        fig.patch.set_alpha(0)
        ax.set_facecolor('none')

        # If background image is present, plot it at full brightness
        if bg_image is not None:
            try:
                ax.imshow(bg_image,
                          extent=[hist.index.min(), hist.index.max(), hist['Close'].min(), hist['Close'].max()],
                          aspect='auto', alpha=1.0, zorder=0)
            except Exception:
                pass

        # Plot the price line
        ax.plot(hist.index, hist['Close'], label=ticker, linewidth=2, zorder=2)

        # Format dates as M/D/YY for Windows
        from matplotlib.dates import DateFormatter
        # Cross‑platform date format (Android APK = Linux, Windows desktop = Windows)
        import sys
        if sys.platform.startswith('win'):
            ax.xaxis.set_major_formatter(DateFormatter('%m/%d/%y'))  # Windows
        else:
            ax.xaxis.set_major_formatter(DateFormatter('%-m/%-d/%y'))  # Android/Linux (APK))

        # Keep grid and axes visible (but harmonize with cyberpunk look)
        ax.grid(True, color='white', alpha=0.25)
        ax.set_title(f"{ticker} Stock Price", fontsize=14)
        ax.set_xlabel("Date")
        ax.set_ylabel("Price ($)")

        try:
            mplcyberpunk.add_glow_effects()
        except Exception:
            pass

        st.pyplot(fig)
        return True

    def render_plotly_fallback(hist: pd.DataFrame, ticker: str):
        fig = go.Figure(data=[go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name=ticker)])
        fig.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=30, b=0), height=320,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

        # Keep gridlines + axes visible while making background transparent
        fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.3)', zeroline=False, showline=True,
                         linecolor='rgba(255,255,255,0.6)', ticks='outside', tickformat='%m/%d/%y')
        fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.3)', zeroline=False, showline=True,
                         linecolor='rgba(255,255,255,0.6)')

        # Inject CSS to ensure Plotly container is transparent
        safe_markdown("""
        <style>
        .plotly-graph-div, .js-plotly-plot svg, .js-plotly-plot .svg-container { background: transparent !important; }
        </style>
        """)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # ------------------------------------------------------------------
    # Main loop: iterate tickers and render sections
    # ------------------------------------------------------------------
    for ticker in tickers:
        try:
            info = get_info_cached(ticker)
            hist = get_stock_data(ticker, period)

            if hist is None or hist.empty:
                st.warning(f"No data available for {ticker}")
                continue

            # Render company header
            render_company_header(info, ticker)

            # Try matplotlib cyberpunk chart first
            rendered = render_matplotlib_cyberpunk_chart(hist, ticker, bg_image)
            if not rendered:
                render_plotly_fallback(hist, ticker)

            # Metrics row
            cols = st.columns(4)
            c_price, c_cap, c_range, c_change = cols[0], cols[1], cols[2], cols[3]
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            cap = info.get("marketCap")
            high = info.get("fiftyTwoWeekHigh")
            low = info.get("fiftyTwoWeekLow")
            with c_price:
                st.metric("Current Price", f"${price:,.2f}" if price else "N/A")
            with c_cap:
                st.metric("Market Cap", f"${cap:,.0f}" if cap else "N/A")
            with c_range:
                st.metric("52w High / Low", f"${high} / ${low}")
            with c_change:
                hist_5d = get_stock_data(ticker, "5d")
                if hist_5d is not None and len(hist_5d) >= 2:
                    change = hist_5d["Close"].iloc[-1] - hist_5d["Close"].iloc[-2]
                    pct = (change / hist_5d["Close"].iloc[-2]) * 100
                    st.metric("Daily Change", f"${change:.2f}", f"{pct:.2f}%")

            # Company info
            summary = info.get("longBusinessSummary", "No company description available.")
            if summary and summary.strip():
                with st.expander("📘 Company Info (click to expand)"):
                    st.write(summary)
            else:
                st.info("No company description available.")

            st.markdown("---")

            # News
            st.subheader(f"📰 {ticker} Recent News")
            if not finnhub_api:
                st.info("Enter your Finnhub API key in the sidebar to enable company news.")
                news = []
            else:
                news = get_company_news(ticker, finnhub_api)
            if news:
                for article in news[:5]:
                    dt = datetime.datetime.fromtimestamp(article.get("datetime", 0))
                    t_str = dt.strftime("%b %d, %Y")
                    safe_markdown(
                        f"<div class='news-card'><a href='{article.get('url')}' target='_blank'><b>{article.get('headline')}</b></a><br><small>{article.get('source', 'Unknown')} | {t_str}</small></div>")
            else:
                if finnhub_api:
                    st.info("No recent news available.")

            safe_markdown("<hr style='border: 1px solid #00f5ff; opacity: 0.3;'>")

        except Exception as e:
            st.error(f"Could not load info for {ticker}: {e}")

    # Footer
    safe_markdown("<hr>")
    safe_markdown("Built with ❤️ — Wizard Q")


try:
    run_app()
except Exception:
    import streamlit as st;

    st.rerun()
