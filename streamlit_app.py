import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import io
import urllib.parse
import re
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master v21", page_icon="🩺", layout="wide")

# --- DATA EXTRACTION AGENT (Widget + Text Scraper) ---
def extract_study_data(base_url):
    """Extracts BOTH the fullscreen widget URL and the actual clinical text from the case page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    widget_url = base_url
    scraped_context = ""
    
    try:
        res = requests.get(base_url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # --- 1. Extract Widget URL ---
            fullscreen_btn = soup.select_one('a.view-fullscreen-link')
            if fullscreen_btn and fullscreen_btn.has_attr('href'):
                clean_path = fullscreen_btn['href'].split('?')[0]
                widget_url = f"https://radiopaedia.org{clean_path}?widget=true"
            else:
                match = re.search(r'(/cases/\d+/studies/\d+)', res.text)
                if match: widget_url = f"https://radiopaedia.org{match.group(1)}?widget=true"

            # --- 2. Extract Clinical Text for the AI ---
            pres = soup.find(id='case-patient-presentation')
            if pres: scraped_context += f"CLINICAL PRESENTATION:\n{pres.get_text(' ', strip=True)}\n\n"
            
            finds = soup.find(class_='study-findings')
            if finds: scraped_context += f"RADIOLOGY FINDINGS:\n{finds.get_text(' ', strip=True)}\n\n"
            
            disc = soup.find(id='case-discussion')
            if disc: scraped_context += f"CASE DISCUSSION & DIAGNOSIS:\n{disc.get_text(' ', strip=True)}\n\n"
            
    except Exception: 
        pass
        
    return widget_url, scraped_context

# --- SEARCH SCOUT ---
def find_radiopaedia_case(query):
    search_query = f"site:radiopaedia.org/cases {query}"
    base_case_url = None
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        res = requests.post("https://lite.duckduckgo.com/lite/", data={"q": search_query}, headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = urllib.parse.unquote(a['href'])
            match = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', href)
            if match and '/articles/' not in href:
                base_case_url = match.group(1)
                break
    except: pass

    if not base_case_url:
        try:
            yahoo_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(search_query)}"
            res = requests.get(yahoo_url, headers=headers, timeout=8)
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = urllib.parse.unquote(a['href'])
                match = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', href)
                if match and '/articles/' not in href:
                    base_case_url = match.group(1)
                    break
        except: pass

    if base_case_url:
        return extract_study_data(base_case_url)

    return None, ""

# --- DUAL-CONTEXT CONCORDANCE ENGINE ---
def generate_osce_with_concordance(title, system, model, api_v, scraped_case_context, article_content):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    # Building the Dual-Context Injection
    context_injection = ""
    if scraped_case_context:
        context_injection += f"\n--- 1. SPECIFIC PATIENT CASE (Use this strictly for the 'Clinical History' and 'Imaging Findings' questions) ---\n{scraped_case_context}\n"
    if article_content:
        # Truncate article content to first 6000 chars to avoid token limits
        context_injection += f"\n--- 2. RADIOPAEDIA ARTICLE MASTER DATA (Use this to build robust DDx, Pathology, Associations, and Management questions) ---\n{article_content[:6000]}\n"

    gen_prompt = f"""
    You are a Senior Radiology Board Examiner. Create a rigorous, formal OSCE case for: {title} ({system}). 
    Format: Clinical Presentation, 5 Questions, and a Marking Guide with [0.5] / [1.0] point allocations.
    
    CRITICAL INSTRUCTIONS:
    - Base Question 1 (Findings) and the Clinical Presentation ONLY on the "SPECIFIC PATIENT CASE" data below.
    - Base Questions 2-5 (Pathology, DDx, Syndromes, Management) on the rich "RADIOPAEDIA ARTICLE MASTER DATA" below.
    
    {context_injection}
    """
    
    try:
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']
        
        audit_prompt = f"""
        You are an Audit Agent. Cross-reference this draft OSCE against the Patient Case to ensure no visual findings were hallucinated.
        
        PATIENT CASE: {scraped_case_context}
        DRAFT OSCE: {draft}
        
        OUTPUT FORMAT:
        AUDIT_SCORE: [1-10]
        AUDIT_FINDINGS: [List contradictions fixed]
        FINAL_CASE: [The complete, harmonized version]
        """
        
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}).json()
        return res2['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Simulator v21")
    st.caption("Dual-Context Engine: Grounded in Real Scans & Encyclopedic Articles")
    
    # Load Library
    df = None
    if FILE_ID:
        try:
            res = requests.get(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx")
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except: pass

    # Sidebar Selection
    st.sidebar.header("Case Engine")
    custom_topic = st.sidebar.text_input("1. Manual Topic Override")
    direct_url = st.sidebar.text_input("2. Direct Case Link (Optional)", help="Paste a Radiopaedia case link here.")
    model = st.sidebar.text_input("AI Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate Board Case"):
        
        # Determine Topic and Extract Article Content
        article_content = ""
        if custom_topic:
            topic = custom_topic
            sys = "Manual"
            # If manual, we don't have article content, AI will rely on its internal training for the facts
        elif df is not None:
            row = df.sample(1).iloc[0]
            topic = row['title']
            sys = row.get('system', 'General')
            article_content = str(row.get('content', '')) # Pull the encyclopedia text!
        else:
            topic = "Glioblastoma"
            sys = "Neuro"

        st.session_state.current_title = topic
        
        # 1. SCOUT & SCRAPE PATIENT CASE
        with st.spinner(f"🔍 Extracting images and specific case findings for: {topic}..."):
            if direct_url and "radiopaedia.org/cases/" in direct_url:
                clean_direct = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', direct_url)
                if clean_direct:
                    widget_url, scraped_case = extract_study_data(clean_direct.group(1))
                else:
                    widget_url, scraped_case = None, ""
            else:
                widget_url, scraped_case = find_radiopaedia_case(topic)
                
            st.session_state.case_url = widget_url
            st.session_state.scraped_case = scraped_case
            st.session_state.article_content = article_content

        # 2. GENERATE OSCE USING DUAL-CONTEXT
        with st.spinner("🧠 Merging patient scan findings with encyclopedic article data..."):
            st.session_state.full_response = generate_osce_with_concordance(
                topic, sys, model, "v1beta", 
                st.session_state.scraped_case, 
                st.session_state.article_content
            )
            
        st.session_state.reveal = False

    # Main Display
    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        try:
            report, display_text = raw.split("FINAL_CASE:")
        except:
            report, display_text = "Audit findings integrated.", raw

        if "### MARKING GUIDE" in display_text:
            questions, marking_guide = display_text.split("### MARKING GUIDE")
        else:
            questions, marking_guide = display_text, "Guide not generated."

        col_text, col_viewer = st.columns([1, 1.2])

        with col_text:
            st.subheader("📝 Clinical Vignette")
            
            with st.expander("🛡️ Data Engine Audit Log"):
                st.info(report.strip())
                st.divider()
                st.caption("SOURCE 1: SPECIFIC PATIENT DATA (Scraped from Case)")
                st.write(st.session_state.get("scraped_case", "No case data scraped."))
                st.divider()
                st.caption("SOURCE 2: LIBRARY ARTICLE DATA (Pulled from Database)")
                # Show just a snippet of the article to prove it's working
                art_snippet = st.session_state.get("article_content", "")[:300]
                st.write(f"{art_snippet}..." if art_snippet else "No library article used.")
            
            st.markdown(questions)
            st.divider()

            if st.button("🔓 Reveal Marking Guide"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### ✅ MARKING GUIDE\n" + marking_guide)

            st.write("---")
            st.write("### Rate this Scenario")
            star_val = st.select_slider("Select Stars", options=[1, 2, 3, 4, 5], value=5, key="stars")
            if st.button("🚀 Submit Feedback"):
                st.toast("Feedback Saved!")

        with col_viewer:
            st.subheader("🖼️ Interactive Stacks")
            found_url = st.session_state.get('case_url')
            
            if found_url:
                if "widget=true" in found_url:
                    st.link_button("Open Fullscreen Viewer ↗️", found_url)
                    components.iframe(found_url, height=900, scrolling=True)
                else:
                    st.warning("⚠️ Scout extracted text, but Cloudflare blocked the embedded widget.")
                    st.link_button("Open Case in New Tab ↗️", found_url, type="primary")
            else:
                st.error("⚠️ Stack extraction failed.")

if __name__ == "__main__":
    main()
