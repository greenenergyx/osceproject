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

# --- DATABASE CONNECTION ---
def get_gspread_client():
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

def save_to_sheets(title, content, rating):
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(DB_ID).sheet1
        sheet.append_row([title, content, rating])
        return True
    except Exception as e:
        st.error(f"Database Error: {e}")
        return False

# --- SEEDING ENGINE ---
def seed_abdominal_cases():
    cases = [
        ("Case 1: VHL", "### 📝 CLINICAL PRESENTATION\n30yo Male, abdominal pain.\n\n### ❓ QUESTIONS\n1. Observations?\n2. Diagnosis?\n3. List 4 RCC subtypes.\n4. 2 other associations of RCC?\n5. Counseling & Genetics?\n\n### ✅ MARKING GUIDE\n- Observations (3.0 pts): Bilateral solid-cystic renal masses [1.0], cortical cysts [0.5], pancreatic cysts [0.5].\n- Diagnosis (2.0 pts): Von Hippel-Lindau disease [2.0].\n- Pathology (2.0 pts): Clear cell, papillary, chromophobe, collecting duct [0.5 each].\n- Associations (1.0 pt): Tuberous sclerosis, Birt-Hogg-Dube [0.5 each].\n- Management (2.0 pts): Regular surveillance [1.0], AD inheritance [1.0]."),
        ("Case 2: Focal Nodular Hyperplasia", "### 📝 CLINICAL PRESENTATION\n35yo Female, RUQ pain.\n\n### ❓ QUESTIONS\n1. Observations?\n2. Diagnosis?\n3. Management?\n4. Contrast agent & delay?\n5. MRI Contraindications?\n\n### ✅ MARKING GUIDE\n- Observations (4.0 pts): Central scar [0.5], avid arterial enhancement [0.5], portal venous isointensity [0.5].\n- Diagnosis (1.0 pt): Focal nodular hyperplasia [1.0].\n- Management (2.0 pts): Benign, surgery only if symptomatic [2.0]."),
        ("Case 3: GIST", "### 📝 CLINICAL PRESENTATION\n65yo Male, palpable mass.\n\n### ❓ QUESTIONS\n1. Observations?\n2. Diagnosis & DDx?\n3. Management?\n4. Malignancy features?\n5. Syndromes?\n\n### ✅ MARKING GUIDE\n- Diagnosis (3.0 pts): GIST [1.0]. DDx: Lymphoma, Carcinoid [1.0 each].\n- Pathology (2.0 pts): Diameter >5cm, necrosis, organ infiltration [0.5 each]."),
        ("Case 4: ADPKD", "### 📝 CLINICAL PRESENTATION\n45yo Male, hypertension.\n\n### ❓ QUESTIONS\n1. Findings? 2. Diagnosis? 3. Extra-renal? 4. Cause of death? 5. Inheritance?\n\n### ✅ MARKING GUIDE\n- Observations (2.0 pts): Enlarged kidneys with innumerable cysts [1.0], hepatic cysts [1.0].\n- Knowledge (1.5 pts): Liver cysts, Berry aneurysms, Diverticulosis [0.5 each]."),
        ("Case 5: Sigmoid Volvulus", "### 📝 CLINICAL PRESENTATION\n80yo Female, nursing home, distended abdomen.\n\n### ❓ QUESTIONS\n1. Plain film? 2. Diagnosis? 3. Sign name? 4. Common sites? 5. Management?\n\n### ✅ MARKING GUIDE\n- Observations (2.0 pts): Coffee bean sign [1.0], dilated loop arising from pelvis [1.0].\n- Management (2.0 pts): Endoscopic detorsion [1.0], surgery if gangrenous [1.0]."),
        ("Case 6: Horseshoe Kidney", "### 📝 CLINICAL PRESENTATION\n25yo Female, trauma.\n\n### ❓ QUESTIONS\n1. Findings? 2. Diagnosis? 3. Artery responsible? 4. Complications? 5. Chromosomes?\n\n### ✅ MARKING GUIDE\n- Knowledge (2.0 pts): IMA prevents migration [1.0], risk of stones/trauma [1.0].\n- Pathology (1.0 pt): Turner Syndrome (45, XO) [1.0]."),
        ("Case 7: Emphysematous Cholecystitis", "### 📝 CLINICAL PRESENTATION\n70yo Diabetic Male, septic.\n\n### ❓ QUESTIONS\n1. CT findings? 2. Diagnosis? 3. Risk factor? 4. Organism? 5. Management?\n\n### ✅ MARKING GUIDE\n- Observations (2.0 pts): Gas in GB wall/lumen [1.0], stranding [1.0].\n- Knowledge (2.0 pts): Diabetes [1.0], Clostridium welchii [1.0]."),
        ("Case 8: Porcelain Gallbladder", "### 📝 CLINICAL PRESENTATION\n55yo Female, incidental finding.\n\n### ❓ QUESTIONS\n1. Radiograph findings? 2. Diagnosis? 3. Malignancy risk? 4. Management? 5. Calcification types?\n\n### ✅ MARKING GUIDE\n- Knowledge (3.0 pts): GB Carcinoma risk [1.0], selective calcification higher risk than diffuse [2.0].")
    ]
    for title, content in cases:
        save_to_sheets(title, content, 5)
    st.sidebar.success("8 Abdominal Golden Cases seeded!")

# --- DATA LOADING ---
@st.cache_data(ttl=600)
def load_library():
    if not FILE_ID: return None
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    try:
        res = requests.get(url)
        df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except:
        return None

# --- AI GENERATION ---
def generate_osce(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    You are a Senior Radiology Board Examiner. 
    INSTRUCTION: Create a high-quality OSCE case following the 'Radiopaedia Abdominal' style.
    
    STRUCTURE:
    - CLINICAL PRESENTATION: One short sentence.
    - QUESTIONS: 5 structured questions (Findings, Diagnosis, DDx, Pathology, Management).
    - MARKING GUIDE: Precise point allocation (e.g., [0.5] or [1.0]).
    
    TOPIC: {title} ({system})
    DIFFICULTY: {difficulty}
    LANGUAGE: English.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Error: {str(e)}"

# --- UI MAIN ---
def main():
    st.title("🩺 Radiology OSCE Master v4")
    
    df = load_library()
    if df is None:
        st.error("Library Excel not found. Check EXCEL_DRIVE_ID.")
        return

    # Sidebar
    st.sidebar.header("📁 Database Tools")
    if st.sidebar.button("🌱 Seed Abdominal Cases (1-8)"):
        seed_abdominal_cases()
    
    st.sidebar.divider()
    st.sidebar.header("⚙️ Generation Settings")
    api_v = st.sidebar.radio("API Version", ["v1", "v1beta"])
    model = st.sidebar.text_input("Model ID", "gemini-2.0-flash-lite")
    difficulty = st.sidebar.select_slider("Level", ["High-Yield", "Intermediate", "Advanced"])
    
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["All"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("System", systems)

    if st.sidebar.button("🎲 Generate Board Case"):
        subset = df if choice == "All" else df[df[system_col] == choice]
        if not subset.empty:
            row = subset.sample(1).iloc[0]
            st.session_state.current_case_title = row.get('title', 'Pathology')
            st.session_state.case_info = row.to_dict()
            
            with st.spinner("Analyzing standards and generating..."):
                st.session_state.full_osce = generate_osce(
                    st.session_state.current_case_title, row.get(system_col, 'General'), model, api_v, difficulty
                )
            st.session_state.reveal = False
            st.session_state.rated = False
        else:
            st.warning("No cases found for this selection.")

    # Display
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        # Handle different potential header formats from AI
        if "### ✅ MARKING GUIDE" in text:
            parts = text.split("### ✅ MARKING GUIDE")
        elif "### MARKING GUIDE" in text:
            parts = text.split("### MARKING GUIDE")
        else:
            parts = [text, ""]
        
        st.markdown(parts[0])
        st.divider()
        
        st.subheader("⭐ Feedback Loop")
        rating = st.feedback("stars")
        if rating is not None and not st.session_state.rated:
            save_to_sheets(st.session_state.current_case_title, text, rating + 1)
            st.toast("Success: Case and rating saved to Google Sheets!")
            st.session_state.rated = True

        if st.button("🔓 Reveal Marking Guide"):
            st.session_state.reveal = True
        
        if st.session_state.get('reveal'):
            st.success("### MARKING GUIDE" + (parts[1] if len(parts)>1 else ""))
            with st.expander("Reference Info"):
                st.write(f"Topic: {st.session_state.current_case_title}")
                st.write(f"Source URL: {st.session_state.case_info.get('url', 'N/A')}")

if __name__ == "__main__":
    main()
