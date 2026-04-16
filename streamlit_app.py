import streamlit as st
import pandas as pd
import requests
import io
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
# We use .get to prevent crashes if a secret is temporarily missing
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master v5", page_icon="🩺", layout="wide")

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
    
    # 1. GENERATION PROMPT
    gen_prompt = f"""
    You are a Radiology Examiner. Create a formal OSCE case for: {title} ({system}).
    Format: Clinical Presentation, 5 Questions, Marking Guide with [0.5] points.
    Ensure accuracy of imaging signals (e.g. fat, fluid, blood).
    """

    try:
        # Step 1: Draft
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}, timeout=20).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']

        # Step 2: Audit
        audit_prompt = f"""
        You are a Senior Radiology Consultant. Audit this case for factual errors.
        Check specifically for MRI/CT signal characteristics and anatomical logic.
        
        CASE: {draft}
        
        OUTPUT FORMAT:
        AUDIT_SCORE: [1-10]
        AUDIT_FINDINGS: [List any errors, e.g. "Lipoma should be T1 hyperintense, not hypo"]
        FINAL_CASE: [The complete corrected version]
        """
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}, timeout=20).json()
        audit_result = res2['candidates'][0]['content']['parts'][0]['text']
        return audit_result

    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Simulator v5")
    st.caption("Agentic Workflow: Draft -> Audit -> Correct")

    # Load Library
    if not FILE_ID:
        st.warning("Please set your EXCEL_DRIVE_ID in Secrets.")
        return

    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    try:
        res = requests.get(url)
        df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
    except:
        st.error("Could not load Library Excel.")
        return

    # Sidebar
    st.sidebar.header("Settings")
    model = st.sidebar.text_input("Model ID", "gemini-1.5-pro") # Pro is better for auditing
    diff = st.sidebar.select_slider("Level", ["High-Yield", "Intermediate", "Advanced"])
    
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    choice = st.sidebar.selectbox("System", ["All"] + sorted(df[system_col].dropna().unique().tolist()))

    if st.sidebar.button("🎲 Generate & Audit Case"):
        subset = df if choice == "All" else df[df[system_col] == choice]
        row = subset.sample(1).iloc[0]
        st.session_state.current_title = row.get('title', 'Pathology')
        
        with st.spinner("🔍 Agent 1: Drafting... Agent 2: Auditing accuracy..."):
            st.session_state.full_response = generate_osce_with_audit(
                st.session_state.current_title, row.get(system_col, 'General'), model, "v1beta", diff
            )
        st.session_state.reveal = False

    # Display Logic
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        if "ERROR_STOP" in raw:
            st.error(raw)
        else:
            # Parse the Audit Report
            if "FINAL_CASE:" in raw:
                report, case = raw.split("FINAL_CASE:")
                with st.expander("🛡️ Clinical Audit Report (Internal Review)", expanded=True):
                    st.info(report.strip())
                display_text = case.strip()
            else:
                display_text = raw

            # Formatting
            parts = display_text.split("### MARKING GUIDE") if "### MARKING GUIDE" in display_text else [display_text, ""]
            st.markdown(parts[0])
            
            st.divider()
            rating = st.feedback("stars")
            if rating is not None:
                save_to_sheets(st.session_state.current_title, display_text, rating+1)
                st.toast("Saved to Database!")

            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### MARKING GUIDE" + parts[1])

if __name__ == "__main__":
    main()
