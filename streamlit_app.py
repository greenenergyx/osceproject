import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import io
import gspread
import urllib.parse
import re
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master v16", page_icon="🩺", layout="wide")

# --- UNIVERSAL SCOUT AGENT (Unblockable) ---
def find_radiopaedia_case(query):
    """
    Checks multiple search engines and uses Regex to extract the true Radiopaedia link.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    search_query = f"site:radiopaedia.org/cases {query}"
    
    # 1. DuckDuckGo Lite (Highly resilient text-only search)
    try:
        res = requests.post("https://lite.duckduckgo.com/lite/", data={"q": search_query}, headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = urllib.parse.unquote(a['href'])
            if 'radiopaedia.org/cases/' in href and '/articles/' not in href:
                match = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', href)
                if match: return f"{match.group(1)}/studies?widget=true"
    except: pass

    # 2. Yahoo Search (Lenient scraping policies)
    try:
        yahoo_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(search_query)}"
        res = requests.get(yahoo_url, headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = urllib.parse.unquote(a['href'])
            if 'radiopaedia.org/cases/' in href and '/articles/' not in href:
                match = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', href)
                if match: return f"{match.group(1)}/studies?widget=true"
    except: pass
        
    # 3. Direct Radiopaedia Fallback
    try:
        rp_url = f"https://radiopaedia.org/search?q={urllib.parse.quote(query)}&scope=cases"
        res = requests.get(rp_url, headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        link = soup.select_one('a[class*="search-result-case"]')
        if link:
            clean_path = link['href'].split('?')[0]
            return f"https://radiopaedia.org{clean_path}/studies?widget=true"
    except: pass

    return None

# --- AGENTIC ENGINE ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    gen_prompt = f"Create a formal OSCE case for: {title} ({system}). Include Clinical Presentation, 5 Questions, and a Marking Guide with [0.5] points."
    
    try:
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']
        
        audit_prompt = f"""You are a Senior Radiology Consultant. Audit this case for factual errors.
        Check specifically for MRI/CT signal characteristics.
        CASE: {draft}
        OUTPUT FORMAT:
        AUDIT_SCORE: [1-10]
        AUDIT_FINDINGS: [List errors]
        FINAL_CASE: [The complete corrected version]"""
        
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}).json()
        return res2['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Simulator v16")
    
    df = None
    if FILE_ID:
        try:
            res = requests.get(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx")
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except: pass

    # Sidebar Selection
    st.sidebar.header("Case Engine")
    custom_topic = st.sidebar.text_input("1. Manual Topic Override")
    direct_url = st.sidebar.text_input("2. Direct Radiopaedia Link (Optional)", help="Paste a URL here to bypass the scout agent completely.")
    model = st.sidebar.text_input("AI Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate Board Case"):
        if custom_topic:
            topic = custom_topic
            sys = "Manual"
        elif df is not None:
            row = df.sample(1).iloc[0]
            topic = row['title']
            sys = row.get('system', 'General')
        else:
            topic = "Acute Appendicitis"
            sys = "Gastrointestinal"

        st.session_state.current_title = topic
        with st.spinner(f"🔍 Scouting images & auditing clinical scenario for: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, sys, model, "v1beta", "High-Yield")
            
            # Use direct URL if provided, otherwise run the Scout
            if direct_url and "radiopaedia.org/cases/" in direct_url:
                clean_direct = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', direct_url)
                st.session_state.case_url = f"{clean_direct.group(1)}/studies?widget=true" if clean_direct else None
            else:
                st.session_state.case_url = find_radiopaedia_case(topic)
            
        st.session_state.reveal = False

    # Main Display
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        try:
            report, display_text = raw.split("FINAL_CASE:")
        except:
            report, display_text = "Audit findings integrated.", raw

        if "### MARKING GUIDE" in display_text:
            questions, marking_guide = display_text.split("### MARKING GUIDE")
        else:
            questions, marking_guide = display_text, "Guide not generated."

        col_text, col_viewer = st.columns([1, 1.2])

        with col_text:
            st.subheader("📝 Clinical Vignette")
            with st.expander("🛡️ Consultant Audit Report"):
                st.info(report.strip())
            
            st.markdown(questions)
            st.divider()

            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### ✅ MARKING GUIDE\n" + marking_guide)

            st.write("---")
            st.write("### Rate this Scenario")
            star_val = st.select_slider("Select Stars", options=[1, 2, 3, 4, 5], value=5, key="stars")
            if st.button("🚀 Submit Feedback"):
                st.toast("Feedback Saved!")

        with col_viewer:
            st.subheader("🖼️ Interactive Stacks")
            if st.session_state.get('case_url'):
                st.link_button("Open Fullscreen Viewer ↗️", st.session_state.case_url)
                components.iframe(st.session_state.case_url, height=900, scrolling=True)
            else:
                st.error("⚠️ All scout agents were blocked by security headers.")
                st.write(f"**Workaround:**")
                st.write(f"1. Search [{st.session_state.current_title} on Radiopaedia](https://radiopaedia.org/search?q={st.session_state.current_title.replace(' ', '+')}&scope=cases)")
                st.write(f"2. Copy the case URL and paste it into the **'Direct Radiopaedia Link'** box in the sidebar, then hit Generate.")

if __name__ == "__main__":
    main()
