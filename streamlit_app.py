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
            "type": st.secrets.get("GCP_TYPE"),
            "project_id": st.secrets.get("GCP_PROJECT_ID"),
            "private_key_id": st.secrets.get("GCP_PRIVATE_KEY_ID"),
            "private_key": st.secrets.get("GCP_PRIVATE_KEY"),
            "client_email": st.secrets.get("GCP_CLIENT_EMAIL"),
            "client_id": st.secrets.get("GCP_CLIENT_ID"),
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

# --- AGENTIC GENERATION ENGINE ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    # Combined Prompt for reliability
    full_prompt = f"""
    You are a Radiology Examiner and Consultant.
    STEP 1: Create a formal OSCE case for: {title} ({system}). Include History, 5 Questions, and Marking Guide.
    STEP 2: Audit for factual accuracy (MRI/CT signals).
    STEP 3: Provide a Radiopaedia URL for a similar case.
    
    OUTPUT FORMAT (STRICT):
    AUDIT_REPORT: [Your critique]
    RADIOPAEDIA_URL: [Link]
    FINAL_CASE: [Full Case Text]
    """

    try:
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
        response = requests.post(url, json=payload, timeout=25)
        res_json = response.json()
        
        if 'candidates' in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"API_ERROR: {res_json.get('error', {}).get('message', 'Unknown Error')}"
    except Exception as e:
        return f"CONN_ERROR: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Master v6")
    
    # Load Library
    df = None
    if FILE_ID:
        try:
            lib_url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
            res = requests.get(lib_url)
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except:
            st.warning("Library connection failed. Use Custom Topic below.")

    # Sidebar
    st.sidebar.header("Case Selection")
    custom_topic = st.sidebar.text_input("Custom Topic (Optional)")
    model = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate Board Case"):
        topic = custom_topic if custom_topic else (df.sample(1).iloc[0]['title'] if df is not None else "Renal Cell Carcinoma")
        st.session_state.current_title = topic
        
        with st.spinner(f"🔍 Generating & Auditing: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, "General", model, "v1beta", "Intermediate")
        st.session_state.reveal = False

    # Display Logic
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        if "API_ERROR" in raw or "CONN_ERROR" in raw:
            st.error(raw)
        else:
            # Flexible Parsing
            url_found = None
            case_text = raw
            report_text = "Standard Audit performed."

            if "RADIOPAEDIA_URL:" in raw and "FINAL_CASE:" in raw:
                try:
                    report_text = raw.split("RADIOPAEDIA_URL:")[0].replace("AUDIT_REPORT:", "").strip()
                    url_found = raw.split("RADIOPAEDIA_URL:")[1].split("FINAL_CASE:")[0].strip()
                    case_text = raw.split("FINAL_CASE:")[1].strip()
                except:
                    pass

            # 1. Audit Report
            with st.expander("🛡️ Clinical Audit & Accuracy Check"):
                st.info(report_text)

            # 2. Case Display
            main_parts = case_text.split("### MARKING GUIDE")
            st.markdown(main_parts[0])

            # 3. Visualizer
            if url_found and "http" in url_found:
                st.subheader("🖼️ Case Visualizer (Radiopaedia)")
                st.markdown(f"🔗 [Open Reference Case in New Tab]({url_found})")
                components.iframe(url_found, height=700, scrolling=True)

            st.divider()
            
            # Feedback & Reveal
            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                if len(main_parts) > 1:
                    st.success("### MARKING GUIDE" + main_parts[1])
                else:
                    st.warning("Marking guide not found in AI response. Check the full text above.")
            
            rating = st.feedback("stars")
            if rating is not None:
                save_to_sheets(st.session_state.current_title, case_text, rating+1)
                st.toast("Rating saved!")

if __name__ == "__main__":
    main()
