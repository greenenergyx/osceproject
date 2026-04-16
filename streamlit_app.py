import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Exam Prep", page_icon="🩺", layout="wide")

@st.cache_data(ttl=600)
def load_data():
    if not FILE_ID: return None, "Excel ID missing in Secrets."
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    try:
        response = requests.get(url)
        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df, None
    except Exception as e:
        return None, f"Drive Error: {e}"

def list_available_models(api_version):
    """Fetches the list of models authorized for your API Key"""
    if not GEMINI_KEY: return ["API Key missing"]
    url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={GEMINI_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            models_data = res.json().get('models', [])
            return [m['name'].split('/')[-1] for m in models_data]
        else:
            return [f"Error {res.status_code}: {res.text}"]
    except Exception as e:
        return [f"Technical Error: {str(e)}"]

def generate_osce_case(raw_title, system_name, model_name, api_version, difficulty):
    """Generates a high-yield OSCE case in English with filtering logic"""
    if not GEMINI_KEY: return "Missing Gemini API Key."
    
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    You are a Radiology Board Examiner. Create a formal OSCE case based on this topic: {raw_title}.
    
    DIFFICULTY SETTING: {difficulty}
    - If set to 'High-Yield': Focus on classic 'must-know' board exam diagnoses (e.g., Sarcoidosis, Lymphoma, RCC, MSK fractures). 
    - CRITICAL: If the source '{raw_title}' is purely anatomical or a procedure, YOU MUST convert it into a common clinical pathology (e.g., 'Radius' becomes 'Colles Fracture').
    
    OUTPUT FORMAT (Strictly English):
    ### 📝 CLINICAL PRESENTATION
    Provide Age, Sex, and one brief clinical symptom (e.g., '42yo Female, acute right-sided pleuritic chest pain'). Do not provide a long history.
    
    ### ❓ EXAMINATION QUESTIONS
    1. Describe the key imaging findings.
    2. What is the most likely diagnosis?
    3. List two relevant differential diagnoses.
    4. Provide one high-yield pathology or clinical association question.
    5. What is the next best step in management?
    
    ### ✅ MARKING GUIDE
    - Observations (1.0 pt): [Key keywords]
    - Diagnosis (1.0 pt): [The correct specific diagnosis]
    - DDx (0.5 pt): [Two valid alternatives]
    - Knowledge/Management (0.5 pt): [Key clinical takeaway]
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if response.status_code != 200:
            return f"API Error {response.status_code}: {res_json.get('error', {}).get('message')}"
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Technical Error: {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Simulator")
    st.subheader("Board Exam Preparation Mode")
    
    df, error = load_data()
    if error:
        st.error(error)
        return

    # --- SIDEBAR ---
    st.sidebar.header("🔍 Model & API Settings")
    
    api_v = st.sidebar.radio("API Version", ["v1", "v1beta"], index=0)
    
    if st.sidebar.button("📋 List Authorized Models"):
        models = list_available_models(api_v)
        st.sidebar.info("Detected Models:")
        for m in models:
            st.sidebar.code(m)

    # Manual model input
    selected_model = st.sidebar.text_input("Model ID (e.g., gemini-2.0-flash-lite)", "gemini-2.0-flash-lite")
    
    st.sidebar.divider()
    
    st.sidebar.header("⚙️ Case Settings")
    difficulty = st.sidebar.select_slider(
        "Case Specificity",
        options=["High-Yield (Classic)", "Intermediate", "Sub-specialty / Anatomy"],
        value="High-Yield (Classic)"
    )
    
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["All Systems"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("Organ System", systems)

    if st.sidebar.button("🎲 Generate Board Case"):
        subset = df if choice == "All Systems" else df[df[system_col] == choice]
        
        if not subset.empty:
            row = subset.sample(1).iloc[0]
            case_title = row.get('title', 'Pathology')
            
            st.session_state.current_case_title = case_title
            st.session_state.case_info = row.to_dict()
            
            with st.spinner(f"Curating {difficulty} case using {selected_model}..."):
                case_output = generate_osce_case(
                    case_title,
                    row.get(system_col, 'General'),
                    selected_model,
                    api_v,
                    difficulty
                )
                st.session_state.full_osce = case_output
            st.session_state.reveal = False
        else:
            st.warning("No cases found.")

    # --- DISPLAY ---
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        
        if "### ✅ MARKING GUIDE" in text:
            parts = text.split("### ✅ MARKING GUIDE")
            exam_part, marking_part = parts[0], "### ✅ MARKING GUIDE" + parts[1]
        else:
            exam_part, marking_part = text, "Marking guide not found."

        st.markdown(exam_part)
        st.divider()
        
        if st.button("🔓 Reveal Marking Guide"):
            st.session_state.reveal = True
        
        if st.session_state.get('reveal'):
            st.success(marking_part)
            with st.expander("Reference Info"):
                st.write(f"**Original Source:** {st.session_state.current_case_title}")
                url_val = st.session_state.case_info.get('url', "No URL available")
                st.write(f"**Link:** {url_val}")

if __name__ == "__main__":
    main()
