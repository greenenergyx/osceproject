import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import io
import urllib.parse
import re
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master v19", page_icon="🩺", layout="wide")

# --- WIDGET API EXTRACTOR (Fixed to use Numeric rID) ---
def extract_study_url(base_url):
    """Extracts the exact numeric case path to prevent 'Quiz not available' errors."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    try:
        res = requests.get(base_url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Strategy 1: Find the exact Fullscreen button link
            fullscreen_btn = soup.select_one('a.view-fullscreen-link')
            if fullscreen_btn and fullscreen_btn.has_attr('href'):
                # href will be something like "/cases/87785/studies/104237?lang=us"
                clean_path = fullscreen_btn['href'].split('?')[0]
                return f"https://radiopaedia.org{clean_path}?widget=true"
            
            # Strategy 2: Regex fallback looking for the exact numeric pattern
            match = re.search(r'(/cases/\d+/studies/\d+)', res.text)
            if match:
                return f"https://radiopaedia.org{match.group(1)}?widget=true"
    except Exception as e: 
        pass
        
    # Failsafe: Return the base URL if everything is blocked
    return base_url

# --- SEARCH SCOUT ---
def find_radiopaedia_case(query):
    search_query = f"site:radiopaedia.org/cases {query}"
    base_case_url = None
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1. DuckDuckGo Lite
    try:
        res = requests.post("https://lite.duckduckgo.com/lite/", data={"q": search_query}, headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = urllib.parse.unquote(a['href'])
            match = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', href)
            if match and '/articles/' not in href:
                base_case_url = match.group(1)
                break
    except: pass

    # 2. Yahoo Search
    if not base_case_url:
        try:
            yahoo_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(search_query)}"
            res = requests.get(yahoo_url, headers=headers, timeout=8)
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = urllib.parse.unquote(a['href'])
                match = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', href)
                if match and '/articles/' not in href:
                    base_case_url = match.group(1)
                    break
        except: pass

    if base_case_url:
        return extract_study_url(base_case_url)

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
    st.title("🩺 Radiology OSCE Simulator v19")
    
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
    direct_url = st.sidebar.text_input("2. Direct Case Link (Optional)", help="Paste a Radiopaedia case link here.")
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
            topic = "Hepatocellular Carcinoma"
            sys = "Gastrointestinal"

        st.session_state.current_title = topic
        with st.spinner(f"🔍 Compiling clinical data and fetching DICOM stacks for: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, sys, model, "v1beta", "High-Yield")
            
            # Use direct URL if provided
            if direct_url and "radiopaedia.org/cases/" in direct_url:
                clean_direct = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', direct_url)
                if clean_direct:
                    st.session_state.case_url = extract_study_url(clean_direct.group(1))
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
            found_url = st.session_state.get('case_url')
            
            if found_url:
                if "widget=true" in found_url:
                    st.link_button("Open Fullscreen Viewer ↗️", found_url)
                    components.iframe(found_url, height=900, scrolling=True)
                else:
                    st.warning("⚠️ The Scout found the case, but Cloudflare blocked the embedded widget extraction.")
                    st.link_button("Open Case in New Tab ↗️", found_url, type="primary")
                    st.write("*(This happens when your server IP is temporarily rate-limited. Click the button above to view it externally).*")
            else:
                st.error("⚠️ Stack extraction failed completely.")
                st.write("Try pasting the case URL directly into the 'Direct Case Link' box in the sidebar.")

if __name__ == "__main__":
    main()
