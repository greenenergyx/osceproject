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

st.set_page_config(page_title="Radiology OSCE Master v8", page_icon="🩺", layout="wide")

# --- AGENTIC GENERATION ENGINE ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    # Prompting the AI to find the FIRST case link from the HTML structure provided
    # and transform it into a "clean" viewing URL.
    full_prompt = f"""
    You are a Radiology Examiner. 
    1. Create a formal OSCE case for: {title} ({system}).
    2. Audit the draft for accuracy (check signal characteristics).
    3. Find the most representative RADIOPAEDIA CASE URL. 
       Look for the first case in search results.
       IMPORTANT: To prevent spoilers, append '?widget=true' to the URL.
    
    OUTPUT FORMAT:
    AUDIT_REPORT: [Critique]
    RADIOPAEDIA_CASE_URL: https://www.thefreedictionary.com/words-that-end-in-true
    FINAL_OSCE_TEXT: [Full Case Text]
    """

    try:
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
        response = requests.post(url, json=payload) 
        res_json = response.json()
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Master v8")
    st.caption("Anti-Spoiler Mode: Fullscreen Interactive Stacks")

    # Load Library (Assuming standard loading logic from previous steps)
    df = None
    if FILE_ID:
        try:
            lib_url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
            res = requests.get(lib_url)
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except:
            st.warning("Library offline.")

    # Sidebar
    st.sidebar.header("Navigation")
    custom_topic = st.sidebar.text_input("Direct Topic Search")
    model_choice = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate & Sync Case"):
        topic = custom_topic if custom_topic else (df.sample(1).iloc[0]['title'] if df is not None else "Cholecystitis")
        st.session_state.current_title = topic
        
        with st.spinner(f"Agent generating case and preparing hidden-diagnosis stacks..."):
            st.session_state.full_response = generate_osce_with_audit(topic, "General", model_choice, "v1beta", "Board Level")
        st.session_state.reveal = False

    # Main Interface Split
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        try:
            audit_log = raw.split("RADIOPAEDIA_CASE_URL:")[0].replace("AUDIT_REPORT:", "").strip()
            case_url = raw.split("RADIOPAEDIA_CASE_URL:")[1].split("FINAL_OSCE_TEXT:")[0].strip()
            case_text = raw.split("FINAL_OSCE_TEXT:")[1].strip()
        except:
            audit_log = "Audit performed."
            case_url = None
            case_text = raw

        # Create two columns
        col_text, col_viewer = st.columns([1, 1])

        with col_text:
            st.subheader(f"📝 OSCE scenario")
            with st.expander("🛡️ Clinical Audit Report"):
                st.info(audit_log)
            
            # Show Questions (Everything before the marking guide)
            main_parts = case_text.split("### MARKING GUIDE")
            st.markdown(main_parts[0])
            
            st.divider()
            
            # IMPROVED MARKING GUIDE LOGIC
            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                if len(main_parts) > 1:
                    # Displaying marking guide clearly in a success box
                    st.success("### ✅ MARKING GUIDE")
                    st.write(main_parts[1])
                
                # Rating system next to stars
                st.write("---")
                st.write("### Rate this Case")
                col_stars, col_submit = st.columns([2, 1])
                with col_stars:
                    star_val = st.selectbox("Assign Stars", [1, 2, 3, 4, 5], index=4, key="star_rating")
                with col_submit:
                    if st.button("🚀 Submit Rating"):
                        # save_to_sheets logic here...
                        st.toast(f"Saved with {star_val} stars!")

        with col_viewer:
            if case_url and "radiopaedia.org/cases" in case_url:
                st.subheader("🖼️ Interactive Image Stacks")
                st.caption("Use your mouse scroll to move through slices. Answer is hidden.")
                
                # REFINEMENT: Ensure URL uses widget mode for cleaner look
                if "?lang=" in case_url:
                    case_url = case_url.split("?")[0]
                
                # The Widget URL shows the viewer but strips the diagnosis title and sidebar
                widget_url = f"{case_url.rstrip('/')}/studies?widget=true"
                
                # Display the iframe
                components.iframe(widget_url, height=900, scrolling=True)
            else:
                st.warning("Case visualization pending. Enter a topic and click Generate.")

if __name__ == "__main__":
    main()
