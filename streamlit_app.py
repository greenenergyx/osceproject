import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import io
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master v6", page_icon="🩺", layout="wide")

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
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{st.secrets['GCP_CLIENT_EMAIL'].replace('@', '%40')}"
        }
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Credentials Error: {e}")
        return None

def save_to_sheets(title, content, rating):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open_by_key(DB_ID).sheet1
            sheet.append_row([title, content, rating])
            return True
        except Exception as e:
            st.error(f"Sheet Access Error: {e}")
    return False

# --- AGENTIC GENERATION ENGINE ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    # Step 1: Draft
    gen_prompt = f"Create a Radiopaedia-style OSCE case for: {title} ({system}). Include History, 5 Questions, and Marking Guide."
    
    try:
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}, timeout=20).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']

        # Step 2: Audit & URL Discovery
        audit_prompt = f"""
        You are a Senior Radiology Consultant. Audit this case for factual errors.
        
        TASK:
        1. Check signal characteristics (e.g. Lipoma = T1 Hyper).
        2. Provide a direct URL to a representative Radiopaedia case for this diagnosis.
        
        CASE: {draft}
        
        OUTPUT FORMAT:
        AUDIT_SCORE: [1-10]
        AUDIT_FINDINGS: [List errors]
        RADIOPAEDIA_URL: [A direct https://radiopaedia.org/cases/... link]
        FINAL_CASE: [The complete corrected version]
        """
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}, timeout=20).json()
        return res2['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Master v6")
    st.caption("Now with Integrated Radiopaedia Case Visualizer")

    # Load Library
    df = None
    if FILE_ID:
        url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
        try:
            res = requests.get(url)
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except:
            st.error("Library Excel not found.")

    # Sidebar
    st.sidebar.header("Case Selection")
    custom_topic = st.sidebar.text_input("Custom Topic (Optional)")
    model = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate & Audit Case"):
        topic = custom_topic if custom_topic else (df.sample(1).iloc[0]['title'] if df is not None else "Radiology Case")
        st.session_state.current_title = topic
        
        with st.spinner(f"🔍 Drafting & Finding Visual Reference for: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, "General", model, "v1beta", "Intermediate")
        st.session_state.reveal = False

    # Display Logic
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        if "FINAL_CASE:" in raw:
            # Parse the Multi-Agent response
            try:
                report_part = raw.split("RADIOPAEDIA_URL:")[0]
                url_part = raw.split("RADIOPAEDIA_URL:")[1].split("FINAL_CASE:")[0].strip()
                case_part = raw.split("FINAL_CASE:")[1].strip()
            except:
                url_part = None
                case_part = raw
                report_part = "Internal Audit complete."

            # 1. Show Audit Report
            with st.expander("🛡️ Clinical Audit Report", expanded=False):
                st.info(report_part)

            # 2. Show Case Text
            st.markdown(case_part.split("### MARKING GUIDE")[0])

            # 3. CASE VISUALIZER (The scrollable case)
            if url_part and "radiopaedia.org" in url_part:
                st.subheader("🖼️ Case Visualizer")
                st.write(f"Compare with this actual case: [{url_part}]({url_part})")
                
                # We use a container for the IFrame to ensure responsiveness
                with st.container(border=True):
                    components.iframe(url_part, height=800, scrolling=True)
                    st.caption("Note: If the viewer is blank, click the link above to view in a new tab.")

            st.divider()
            # ... (Rest for Feedback/Marking Guide)
            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            if st.session_state.get('reveal'):
                st.success(case_part.split("### MARKING GUIDE")[1] if "### MARKING GUIDE" in case_part else "Check full text above.")

if __name__ == "__main__":
    main()
