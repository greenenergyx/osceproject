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

# --- DATA LOADING ---
@st.cache_data(ttl=600)
def load_library():
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    res = requests.get(url)
    df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def get_feedback_examples():
    """Fetch 5-star cases from the CaseDatabase to use as 'Few-Shot' examples for the AI"""
    # For now, I'll provide a hardcoded 'Golden Standard' based on your Abdominal doc
    # In the next iteration, we can make this dynamic via gspread
    return """
    Example of a 5-Star Case:
    Clinical: 65yo Male, sudden onset SOB.
    Questions: 1. Findings? 2. Diagnosis? 3. DDx? 4. Genetics/Pathology? 5. Management?
    Marking: Observations (1.0), Diagnosis (1.0), DDx (0.5), Knowledge (0.5), Management (0.5).
    """

# --- AI ENGINE ---
def generate_osce(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    examples = get_feedback_examples()
    
    prompt = f"""
    You are a Senior Radiology Board Examiner. 
    Use this HIGH-QUALITY STANDARD for your output:
    {examples}
    
    TOPIC: {title} ({system})
    DIFFICULTY: {difficulty}
    
    STRICT REQUIREMENTS:
    1. Language: English.
    2. Format: Short Clinical History (Age/Sex/Symptom), 5 Questions, and a Marking Guide.
    3. Specificity: If '{title}' is anatomical, convert to a classic pathology.
    4. Quality: Be precise, medical, and succinct.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Error: {str(e)}"

# --- MAIN INTERFACE ---
def main():
    st.title("🩺 Radiology OSCE Simulator v3")
    st.caption("Now with Learning Feedback Loop")

    df = load_library()
    
    # Sidebar
    st.sidebar.header("Settings")
    api_v = st.sidebar.radio("API", ["v1", "v1beta"])
    model = st.sidebar.text_input("Model ID", "gemini-2.0-flash-lite")
    difficulty = st.sidebar.select_slider("Level", ["High-Yield", "Intermediate", "Advanced"])
    
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["All"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("System", systems)

    if st.sidebar.button("🎲 Generate Case"):
        subset = df if choice == "All" else df[df[system_col] == choice]
        row = subset.sample(1).iloc[0]
        
        st.session_state.current_title = row.get('title')
        st.session_state.case_info = row.to_dict()
        
        with st.spinner("AI is studying your favorites to generate this case..."):
            st.session_state.full_osce = generate_osce(
                st.session_state.current_title, row.get(system_col), model, api_v, difficulty
            )
        st.session_state.reveal = False
        st.session_state.rated = False

    # Display
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        parts = text.split("### ✅ MARKING GUIDE") if "### ✅ MARKING GUIDE" in text else [text, ""]
        
        st.markdown(parts[0])
        st.divider()
        
        # Star Rating
        st.subheader("⭐ Rate Case Quality")
        rating = st.feedback("stars")
        if rating is not None and not st.session_state.rated:
            st.toast(f"Saved! This case will influence future results.")
            # Note: We will connect the actual 'save' to your Database ID here
            st.session_state.rated = True

        if st.button("🔓 Show Answer"):
            st.session_state.reveal = True
        
        if st.session_state.get('reveal'):
            st.success("### ✅ MARKING GUIDE" + parts[1])
            with st.expander("Source Details"):
                st.write(f"Topic: {st.session_state.current_case_title}")
                st.write(f"URL: {st.session_state.case_info.get('url', 'N/A')}")

if __name__ == "__main__":
    main()
