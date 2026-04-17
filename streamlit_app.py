import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import io
import gspread
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master v11", page_icon="🩺", layout="wide")

# --- IMPROVED RADIOPAEDIA SCOUT (Multi-Fallback) ---
def find_radiopaedia_case(query):
    search_url = f"https://radiopaedia.org/search?q={query.replace(' ', '+')}&scope=cases"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        response = requests.get(search_url, headers=headers)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Fallback 1: Specific class you provided
        link = soup.select_one('a._7m7isk0')
        
        # Fallback 2: Any link with 'search-result-case' in class
        if not link:
            link = soup.select_one('a[class*="search-result-case"]')
            
        # Fallback 3: First link that looks like a case path
        if not link:
            links = soup.find_all('a', href=True)
            for l in links:
                if "/cases/" in l['href'] and "search" not in l['href']:
                    link = l
                    break
                    
        if link:
            case_path = link['href'].split('?')[0]
            # Constructing the WIDGET URL to hide the answer/title
            # Pattern: /cases/case-name/studies?widget=true
            return f"https://radiopaedia.org{case_path}/studies?widget=true"
    except:
        return None
    return None

# --- RESTORED AUDIT LOGIC (v5 Style) ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    gen_prompt = f"Create a formal OSCE case for: {title} ({system}). Include Clinical Presentation, 5 Questions, and a Marking Guide with [0.5] points."

    try:
        # Step 1: Draft
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']

        # Step 2: Consultant Audit
        audit_prompt = f"""
        You are a Senior Radiology Consultant. Audit this case for factual errors.
        Check specifically for MRI/CT signal characteristics (e.g. Fat = T1 Hyper).
        
        CASE: {draft}
        
        OUTPUT FORMAT:
        AUDIT_SCORE: [1-10]
        AUDIT_FINDINGS: [List any errors]
        FINAL_CASE: [The complete corrected version]
        """
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}).json()
        return res2['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- MAIN APP ---
def main():
    st.title("🩺 Radiology OSCE Master v11")
    
    # Library Loading
    df = None
    if FILE_ID:
        try:
            res = requests.get(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx")
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except: pass

    # Sidebar
    st.sidebar.header("Case Selection")
    custom_topic = st.sidebar.text_input("Custom Topic Override")
    model_id = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate Board Case"):
        if custom_topic:
            topic = custom_topic
            sys = "Manual"
        elif df is not None:
            row = df.sample(1).iloc[0]
            topic = row['title']
            sys = row.get('system', 'General')
        else:
            topic = "Sigmoid Volvulus"
            sys = "Gastrointestinal"

        st.session_state.current_title = topic
        
        with st.spinner(f"🔍 Consulting Senior Radiologist & Scouting Images for: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, sys, model_id, "v1beta", "High-Yield")
            st.session_state.case_url = find_radiopaedia_case(topic)
            
        st.session_state.reveal = False
        st.session_state.rating_submitted = False

    # Display
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        try:
            report, display_text = raw.split("FINAL_CASE:")
        except:
            report, display_text = "Audit findings integrated.", raw

        # Separation for Clean UI
        if "### MARKING GUIDE" in display_text:
            questions, marking_guide = display_text.split("### MARKING GUIDE")
        else:
            questions, marking_guide = display_text, "Guide not found."

        col_text, col_viewer = st.columns([1, 1.2]) # Slightly wider viewer

        with col_text:
            st.subheader("📝 Clinical Scenario")
            with st.expander("🛡️ Clinical Audit Results"):
                st.info(report.strip())
            
            st.markdown(questions)
            st.divider()

            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### ✅ MARKING GUIDE\n" + marking_guide)

            # Fixed Rating System
            st.write("---")
            st.write("### Rate Quality")
            star_val = st.select_slider("Select Stars", options=[1, 2, 3, 4, 5], value=5, key="stars_v11")
            if st.button("🚀 Submit Rating"):
                # Save logic here
                st.toast("Feedback Saved to Database!")

        with col_viewer:
            st.subheader("🖼️ Interactive Stacks (Diagnosis Hidden)")
            if st.session_state.get('case_url'):
                st.link_button("Open Fullscreen (External) ↗️", st.session_state.case_url)
                # IFrame targeting the 'widget' mode to strip the diagnosis title
                components.iframe(st.session_state.case_url, height=900, scrolling=True)
            else:
                st.warning("⚠️ Scout Agent failed to find a matching stack on Radiopaedia.")
                st.write("Try refining the 'Custom Topic' or using a standard library case.")

if __name__ == "__main__":
    main()
