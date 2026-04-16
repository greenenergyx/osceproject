import streamlit as st
import pandas as pd
import requests
import io
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master", page_icon="🩺", layout="wide")

@st.cache_data(ttl=600)
def load_library():
    if not FILE_ID: return None
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    try:
        res = requests.get(url)
        df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error loading library: {e}")
        return None

def get_golden_standard():
    """Explicitly feeds the Abdominal OSCER style to the AI"""
    return """
    ### GOLDEN STANDARD EXAMPLE (5-STARS)
    CLINICAL PRESENTATION: 72yo Male. Sudden onset of back pain and hypotension.
    
    QUESTIONS:
    1. Describe the findings on this CT.
    2. What is the most likely diagnosis?
    3. Provide two differential diagnoses.
    4. What is the most common associated risk factor?
    5. What is the immediate management?
    
    MARKING GUIDE:
    - Observations (1.0 pt): Retroperitoneal hematoma [0.5], aneurysmal dilatation of the infrarenal aorta >3cm [0.5].
    - Diagnosis (1.0 pt): Ruptured Abdominal Aortic Aneurysm (AAA).
    - DDx (0.5 pt): Aortic dissection, perforated viscus.
    - Knowledge (0.5 pt): Smoking or Hypertension.
    - Management (0.5 pt): Vascular surgery consult/Emergency laparotomy.
    """

def generate_osce(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    standard = get_golden_standard()
    
    prompt = f"""
    You are a Radiology Examiner. 
    Use this EXACT formatting and medical rigor:
    {standard}
    
    TOPIC TO ADAPT: {title} ({system})
    DIFFICULTY: {difficulty}
    
    INSTRUCTIONS:
    - Strictly English.
    - If '{title}' is just an organ, pick a 'Board-level' pathology for it.
    - Keep clinical history to ONE short sentence.
    - Ensure the Marking Guide uses the [0.5] or [1.0] point distribution.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if response.status_code != 200:
            return f"API Error {response.status_code}: {res_json.get('error', {}).get('message')}"
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Simulator v3")
    st.caption("Learning from Golden Standards & User Feedback")

    df = load_library()
    if df is None:
        st.error("Library not found. Check EXCEL_DRIVE_ID.")
        return

    # Sidebar
    st.sidebar.header("Settings")
    api_v = st.sidebar.radio("API Version", ["v1", "v1beta"], index=0)
    # Using text_input for model so you can change it to gemini-2.5-flash-lite as requested
    model = st.sidebar.text_input("Model ID", "gemini-2.0-flash-lite")
    difficulty = st.sidebar.select_slider("Specificity", ["High-Yield", "Intermediate", "Advanced"])
    
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["All"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("System", systems)

    if st.sidebar.button("🎲 Generate Board Case"):
        subset = df if choice == "All" else df[df[system_col] == choice]
        if not subset.empty:
            row = subset.sample(1).iloc[0]
            
            # --- FIXED STATE ASSIGNMENT ---
            st.session_state.current_case_title = row.get('title', 'Pathology')
            st.session_state.case_info = row.to_dict()
            
            with st.spinner(f"AI is applying Golden Standard logic for {st.session_state.current_case_title}..."):
                st.session_state.full_osce = generate_osce(
                    st.session_state.current_case_title, 
                    row.get(system_col, 'General'), 
                    model, api_v, difficulty
                )
            st.session_state.reveal = False
            st.session_state.rated = False
        else:
            st.warning("No cases found.")

    # Main Display
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        parts = text.split("### MARKING GUIDE") if "### MARKING GUIDE" in text else [text, ""]
        
        st.markdown(parts[0])
        st.divider()
        
        # Rating
        st.subheader("⭐ Rate Quality")
        rating = st.feedback("stars")
        if rating is not None and not st.session_state.rated:
            st.toast(f"Thank you! Rating recorded.")
            st.session_state.rated = True

        if st.button("🔓 Reveal Answer"):
            st.session_state.reveal = True
        
        if st.session_state.get('reveal'):
            st.success("### MARKING GUIDE" + parts[1])
            
            # Reference section with safety checks
            with st.expander("Reference Source"):
                topic = st.session_state.get('current_case_title', 'Unknown')
                info = st.session_state.get('case_info', {})
                url = info.get('url', 'No URL available')
                
                st.write(f"**Topic:** {topic}")
                st.write(f"**Source:** [Radiopaedia Link]({url})")

if __name__ == "__main__":
    main()
