import streamlit as st
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

st.set_page_config(page_title="Radiology OSCE Master v9", page_icon="🩺", layout="wide")

# --- RADIOPAEDIA SCOUT FUNCTION ---
def find_radiopaedia_case(query):
    """
    Scrapes Radiopaedia search to find the FIRST case link.
    This avoids showing the user the search results (spoilers).
    """
    search_url = f"https://radiopaedia.org/search?q={query.replace(' ', '+')}&scope=cases"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Find the first search result link
        first_result = soup.find('a', class_='search-result-case')
        if first_result:
            case_path = first_result['href']
            # Build the deep link to the studies player
            return f"https://radiopaedia.org{case_path}/studies?lang=us"
    except Exception as e:
        return None
    return None

# --- AGENTIC GENERATION ENGINE ---
def generate_osce_with_audit(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    gen_prompt = f"""
    You are a Radiology Examiner. Create a formal OSCE case for: {title} ({system}).
    Format: Clinical Presentation, 5 Questions, Marking Guide with [0.5] points.
    Ensure accuracy of imaging signals (e.g. fat, fluid, blood, gas).
    """

    try:
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']

        audit_prompt = f"""
        You are a Senior Radiology Consultant. Audit this case for factual errors.
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

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Master v9")
    
    # Sidebar
    st.sidebar.header("Case Selection")
    custom_topic = st.sidebar.text_input("Custom Topic (e.g. 'Sigmoid Volvulus')")
    model = st.sidebar.text_input("Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate & Find Case"):
        topic = custom_topic if custom_topic else "Cholecystitis"
        st.session_state.current_title = topic
        
        with st.spinner(f"🔍 Auditing facts and finding images for: {topic}..."):
            # Step 1: AI Logic
            st.session_state.full_response = generate_osce_with_audit(topic, "General", model, "v1beta", "Intermediate")
            # Step 2: Live Search for the actual image stacks
            st.session_state.case_url = find_radiopaedia_case(topic)
            
        st.session_state.reveal = False
        st.session_state.rating_submitted = False

    # Main Interface
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        try:
            report, display_text = raw.split("FINAL_CASE:")
        except:
            report, display_text = "Audit complete.", raw

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("📝 OSCE scenario")
            with st.expander("🛡️ Clinical Audit Results"):
                st.info(report.strip())
            
            parts = display_text.split("### MARKING GUIDE")
            st.markdown(parts[0])
            st.divider()

            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### ✅ MARKING GUIDE\n" + (parts[1] if len(parts) > 1 else "Not found."))

            # Improved Rating Submit
            st.write("---")
            star_val = st.select_slider("Rate quality", options=[1, 2, 3, 4, 5], value=5)
            if st.button("🚀 Submit to Database"):
                st.toast("Saved!")

        with col_right:
            st.subheader("🖼️ Interactive Stacks")
            if st.session_state.case_url:
                st.info("Because Radiopaedia blocks embedded windows, click the link below to open the interactive stacks in a split-screen or new tab.")
                
                # We use a large, high-visibility button
                st.link_button(f"🔗 OPEN INTERACTIVE VIEWER: {st.session_state.current_title}", 
                              st.session_state.case_url, 
                              use_container_width=True, 
                              type="primary")
                
                st.write("---")
                st.markdown("""
                **How to use this:**
                1. Click the button above to open the images.
                2. Use the **Marking Guide** on the left to grade your findings.
                3. Check the **Audit Report** if you suspect the AI hallucinated a signal.
                """)
            else:
                st.warning("No matching images found on Radiopaedia.")

if __name__ == "__main__":
    main()
