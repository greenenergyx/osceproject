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

st.set_page_config(page_title="Radiology OSCE Master v22", page_icon="🩺", layout="wide")

# --- DATA EXTRACTION AGENT (Widget + Text Scraper) ---
def extract_study_data(base_url):
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
            
            fullscreen_btn = soup.select_one('a.view-fullscreen-link')
            if fullscreen_btn and fullscreen_btn.has_attr('href'):
                clean_path = fullscreen_btn['href'].split('?')[0]
                widget_url = f"https://radiopaedia.org{clean_path}?widget=true"
            else:
                match = re.search(r'(/cases/\d+/studies/\d+)', res.text)
                if match: widget_url = f"https://radiopaedia.org{match.group(1)}?widget=true"

            pres = soup.find(id='case-patient-presentation')
            if pres: scraped_context += f"CLINICAL PRESENTATION:\n{pres.get_text(' ', strip=True)}\n\n"
            
            finds = soup.find(class_='study-findings')
            if finds: scraped_context += f"RADIOLOGY FINDINGS:\n{finds.get_text(' ', strip=True)}\n\n"
            
            disc = soup.find(id='case-discussion')
            if disc: scraped_context += f"CASE DISCUSSION & DIAGNOSIS:\n{disc.get_text(' ', strip=True)}\n\n"
    except Exception: pass
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

    if base_case_url: return extract_study_data(base_case_url)
    return None, ""

# --- TRACEABILITY CONCORDANCE ENGINE ---
def generate_osce_with_traceability(title, system, model, api_v, scraped_case_context, article_content, article_url):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    context_injection = ""
    if scraped_case_context:
        context_injection += f"\n--- SOURCE 1: PATIENT CASE ---\n{scraped_case_context}\n"
    if article_content:
        # Give the AI the article text and the URL from your spreadsheet
        context_injection += f"\n--- SOURCE 2: RADIOPAEDIA ARTICLE ---\nURL: {article_url}\nCONTENT:\n{article_content[:6000]}\n"

    # Agent 1: The Drafter
    gen_prompt = f"""
    You are a Radiology Examiner. Create a formal OSCE case for: {title} ({system}). 
    Format: Clinical Presentation, 5 Questions, and a Marking Guide with [0.5] / [1.0] point allocations.
    
    CRITICAL RULES:
    1. Base Q1 on SOURCE 1 (Patient Case).
    2. Base Q2-Q5 STRICTLY on SOURCE 2 (Radiopaedia Article). 
    3. You MUST append "[Source: {article_url}]" to every answer in the marking guide for Q2-Q5.
    
    {context_injection}
    """
    
    try:
        res1 = requests.post(url, json={"contents": [{"parts": [{"text": gen_prompt}]}]}).json()
        draft = res1['candidates'][0]['content']['parts'][0]['text']
        
        # Agent 2: The Evidence-Based Medicine (EBM) Auditor
        audit_prompt = f"""
        You are the Senior Traceability Auditor. Your job is to ruthlessly eliminate hallucinations.
        
        TASK:
        Read the DRAFT OSCE. Verify that EVERY fact in the Marking Guide answers for Q2-Q5 is explicitly stated in the "SOURCE 2: RADIOPAEDIA ARTICLE" text below.
        If the draft includes outside knowledge (e.g., mentioning "RECIST criteria" when the article does not), you MUST delete that question and rewrite it using ONLY facts present in the text.
        
        ARTICLE TEXT TO VERIFY AGAINST:
        {article_content[:6000]}
        
        DRAFT OSCE:
        {draft}
        
        OUTPUT FORMAT:
        EBM_AUDIT_REPORT: [List any facts you had to remove because they weren't in the text. If perfectly compliant, state "100% Traceable to source".]
        FINAL_CASE: [The fully verified, corrected case with URL citations]
        """
        
        res2 = requests.post(url, json={"contents": [{"parts": [{"text": audit_prompt}]}]}).json()
        return res2['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ERROR_STOP: {str(e)}"

# --- UI LOGIC ---
def main():
    st.title("🩺 Radiology OSCE Simulator v22")
    st.caption("Evidence-Based Mode: Strictly Audited against Library Sources")
    
    df = None
    if FILE_ID:
        try:
            res = requests.get(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx")
            df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            df.columns = [c.strip().lower() for c in df.columns]
        except: pass

    st.sidebar.header("Case Engine")
    custom_topic = st.sidebar.text_input("1. Manual Topic Override")
    direct_url = st.sidebar.text_input("2. Direct Case Link (Optional)")
    model = st.sidebar.text_input("AI Model ID", "gemini-1.5-pro")
    
    if st.sidebar.button("🎲 Generate Board Case"):
        article_content = ""
        article_url = "General Knowledge"
        
        if custom_topic:
            topic = custom_topic
            sys = "Manual"
        elif df is not None:
            row = df.sample(1).iloc[0]
            topic = row['title']
            sys = row.get('system', 'General')
            article_content = str(row.get('content', ''))
            article_url = str(row.get('url', '')) # PULLING URL FROM YOUR EXCEL SCRIPT
        else:
            topic = "Cholecystitis"
            sys = "Gastrointestinal"

        st.session_state.current_title = topic
        
        with st.spinner(f"🔍 Extracting specific patient scan data for: {topic}..."):
            if direct_url and "radiopaedia.org/cases/" in direct_url:
                clean_direct = re.search(r'(https?://radiopaedia\.org/cases/[a-zA-Z0-9-]+)', direct_url)
                if clean_direct: widget_url, scraped_case = extract_study_data(clean_direct.group(1))
                else: widget_url, scraped_case = None, ""
            else:
                widget_url, scraped_case = find_radiopaedia_case(topic)
                
            st.session_state.case_url = widget_url
            st.session_state.scraped_case = scraped_case
            st.session_state.article_content = article_content
            st.session_state.article_url = article_url

        with st.spinner("⚖️ Auditing draft for hallucinations against Library CSV..."):
            st.session_state.full_response = generate_osce_with_traceability(
                topic, sys, model, "v1beta", 
                st.session_state.scraped_case, 
                st.session_state.article_content,
                st.session_state.article_url
            )
            
        st.session_state.reveal = False

    if 'full_response' in st.session_state:
        raw = st.session_state.full_response
        
        try:
            report, display_text = raw.split("FINAL_CASE:")
        except:
            report, display_text = "Traceability Audit complete.", raw

        if "### MARKING GUIDE" in display_text:
            questions, marking_guide = display_text.split("### MARKING GUIDE")
        else:
            questions, marking_guide = display_text, "Guide not generated."

        col_text, col_viewer = st.columns([1, 1.2])

        with col_text:
            st.subheader("📝 Clinical Vignette")
            
            with st.expander("⚖️ Traceability & EBM Audit Report"):
                st.info(report.replace("EBM_AUDIT_REPORT:", "").strip())
                st.divider()
                st.caption(f"📚 TRACED TO ARTICLE URL: {st.session_state.get('article_url', 'N/A')}")
                st.caption("Excerpt used for validation:")
                art_snippet = st.session_state.get("article_content", "")[:400]
                st.write(f"{art_snippet}..." if art_snippet else "No reference library content provided.")
            
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
