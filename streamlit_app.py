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

st.set_page_config(page_title="Radiology OSCE Master v7", page_icon="🩺", layout="wide")

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
        return None

def save_to_sheets(title, content, rating):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open_by_key(DB_ID).sheet1
            sheet.append_row([title, content, rating])
            return True
        except:
            return False
    return False

# --- AGENTIC GENERATION ENGINE (v5 Auditing Logic) ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    gen_prompt = f"""
    You are a Radiology Examiner. Create a formal OSCE case for: {title} ({system}).
    Format: Clinical Presentation, 5 Questions, Marking Guide with [0.5] points.
    Ensure accuracy of imaging signals (e.g. fat, fluid, blood, gas).
    """

    try:
        # Step 1: Draft
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']

        # Step 2: Audit (Restored v5 Logic)
        audit_prompt = f"""
        You are a Senior Radiology Consultant. Audit this case for factual errors.
        Check specifically for MRI/CT signal characteristics and anatomical logic.
        Example: Fat must be T1 hyperintense. Fluid must be T2 hyperintense.
        
        CASE: {draft}
        
        OUTPUT FORMAT:
        AUDIT_SCORE: [1-10]
        AUDIT_FINDINGS: [List any errors found]
        RADIOPAEDIA_CASE_LINK: [Search keyword for radiopaedia case]
        FINAL_CASE: [The complete corrected version]
        """
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}).json()
        return res2['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Master v7")
    
    # Load Library
    df = None
    if FILE_ID:
        try:
            lib_url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
            res = requests.get(lib_url)
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except:
            st.warning("Library Excel offline.")

    # Sidebar
    st.sidebar.header("Case Control")
    custom_topic = st.sidebar.text_input("Custom Topic (Optional)")
    model = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate & Audit Case"):
        if custom_topic:
            topic = custom_topic
            sys = "Custom"
        else:
            row = df.sample(1).iloc[0] if df is not None else {"title": "Renal Cell Carcinoma", "system": "Abdominal"}
            topic = row['title']
            sys = row.get('system', 'General')
            
        st.session_state.current_title = topic
        with st.spinner(f"🔍 Auditing: {topic}..."):
            st.session_state.full_response = generate_osce_with_audit(topic, sys, model, "v1beta", "Intermediate")
        st.session_state.reveal = False
        st.session_state.rating_submitted = False

    # Main Display
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        # Parsing
        try:
            report_part = raw.split("FINAL_CASE:")[0]
            display_text = raw.split("FINAL_CASE:")[1].strip()
        except:
            report_part = "Audit findings integrated."
            display_text = raw

        # Split Case from Marking Guide
        if "### MARKING GUIDE" in display_text:
            case_body, marking_guide = display_text.split("### MARKING GUIDE")
        else:
            case_body, marking_guide = display_text, "Marking guide not found."

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader(f"Case: {st.session_state.current_title}")
            with st.expander("🛡️ Clinical Audit Results", expanded=False):
                st.info(report_part)
            
            st.markdown(case_body)
            st.divider()

            # Marking Guide Section
            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### MARKING GUIDE\n" + marking_guide)

            # Fixed Rating System
            st.divider()
            st.write("### Rate this Case")
            star_val = st.selectbox("Assign Stars", [1, 2, 3, 4, 5], index=4)
            if st.button("🚀 Submit Rating & Save"):
                if not st.session_state.get('rating_submitted'):
                    success = save_to_sheets(st.session_state.current_title, display_text, star_val)
                    if success:
                        st.toast("✅ Case & Rating Saved!")
                        st.session_state.rating_submitted = True
                    else:
                        st.error("Sheet Error.")
                else:
                    st.warning("Rating already submitted for this case.")

        with col_right:
            st.subheader("🖼️ Radiopaedia Visualizer")
            # Build search URL for Radiopaedia Cases
            search_query = st.session_state.current_title.replace(" ", "+")
            case_url = f"https://radiopaedia.org/search?q={search_query}&scope=cases"
            
            st.link_button("Open Case in New Tab ↗️", case_url)
            
            # Note: Radiopaedia often blocks frames. Using a wide search scope works better.
            components.iframe(case_url, height=900, scrolling=True)

if __name__ == "__main__":
    main()
