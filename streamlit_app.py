import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import io
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
# Removed timeouts to allow for complex audit generation
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

# Use wide mode to give space for the scrollable Radiopaedia case
st.set_page_config(page_title="Radiology OSCE Visualizer", page_icon="🩺", layout="wide")

# --- DATABASE CONNECTION ---
def get_gspread_client():
    try:
        creds_dict = {
            "type": st.secrets["GCP_TYPE"],
            "project_id": st.secrets["GCP_PROJECT_ID"],
            "private_key_id": st.secrets["GCP_PRIVATE_KEY_ID"],
            "private_key": st.secrets["GCP_PRIVATE_KEY"],
            "client_email": st.secrets["GCP_CLIENT_EMAIL"],
            "client_id": st.secrets["GCP_CLIENT_ID"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{st.secrets.get('GCP_CLIENT_EMAIL', '').replace('@', '%40')}"
        }
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        return None

def save_to_sheets(title, content, rating):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open_by_key(DB_ID).sheet1
            sheet.append_row([title, content, rating])
            return True
        except:
            pass
    return False

# --- AGENTIC ENGINE (With CASE-SPECIFIC URL discovery) ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    # We explicitly instruct the AI to find a CASE url, not an ARTICLE url.
    full_prompt = f"""
    You are a Radiology Examiner. 
    1. Create a formal OSCE case for: {title} ({system}).
    2. Audit the draft for accuracy (check signal characteristics).
    3. Find the most representative RADIOPAEDIA CASE URL (e.g., https://radiopaedia.org/cases/[case-name]). 
       DO NOT use /articles/. Use /cases/.
    
    OUTPUT FORMAT:
    AUDIT_REPORT: [Critique]
    RADIOPAEDIA_CASE_URL: [Link to the Case page with images]
    FINAL_OSCE_TEXT: [Full Case Text]
    """

    try:
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
        # Timeout removed to prevent truncation
        response = requests.post(url, json=payload) 
        res_json = response.json()
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Master v7")
    st.caption("Interactive AI Examiner with Scrollable Case Viewer")

    # Load Library
    df = None
    if FILE_ID:
        try:
            lib_url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
            res = requests.get(lib_url)
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except:
            st.warning("Library Excel offline. Using custom entry.")

    # Sidebar
    st.sidebar.header("Navigation")
    custom_topic = st.sidebar.text_input("Direct Topic Search")
    model_choice = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate & Sync Case"):
        topic = custom_topic if custom_topic else (df.sample(1).iloc[0]['title'] if df is not None else "Achalasia")
        st.session_state.current_title = topic
        
        with st.spinner(f"Agent generating case and finding visual stacks for: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, "General", model_choice, "v1beta", "Board Level")
        st.session_state.reveal = False

    # Main Interface Split
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        # Robust Parsing
        try:
            audit_log = raw.split("RADIOPAEDIA_CASE_URL:")[0].replace("AUDIT_REPORT:", "").strip()
            case_url = raw.split("RADIOPAEDIA_CASE_URL:")[1].split("FINAL_OSCE_TEXT:")[0].strip()
            case_text = raw.split("FINAL_OSCE_TEXT:")[1].strip()
        except:
            audit_log = "Audit performed."
            case_url = None
            case_text = raw

        # Create two columns: Left for text, Right for the Scrollable Case
        col_text, col_viewer = st.columns([1, 1])

        with col_text:
            st.subheader(f"📝 Case: {st.session_state.current_title}")
            with st.expander("🛡️ Clinical Audit Report"):
                st.info(audit_log)
            
            # Show Questions
            main_parts = case_text.split("### MARKING GUIDE")
            st.markdown(main_parts[0])
            
            st.divider()
            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                if len(main_parts) > 1:
                    st.success("### MARKING GUIDE" + main_parts[1])
            
            rating = st.feedback("stars")
            if rating is not None:
                save_to_sheets(st.session_state.current_title, case_text, rating+1)
                st.toast("Success: Case saved to database.")

        with col_viewer:
            if case_url and "radiopaedia.org/cases" in case_url:
                st.subheader("🖼️ Radiopaedia Case Viewer")
                st.caption(f"Linked Case: {case_url}")
                # The scrollable window for images
                components.iframe(case_url, height=900, scrolling=True)
            else:
                st.warning("Case URL not found or blocked. Try a more specific diagnosis.")
                if case_url: st.write(f"Attempted: {case_url}")

if __name__ == "__main__":
    main()
