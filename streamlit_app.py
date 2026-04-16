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
        ("Case 4: ADPKD", "### 📝 CLINICAL PRESENTATION\n45yo Male, hypertension.\n\n### ❓ QUESTIONS\n1. Findings? 2. Diagnosis? 3. Extra-renal? 4. Cause of death? 5. Inheritance?\n\n### ✅ MARKING GUIDE\n- Observations (2.0 pts): Enlarged kidneys with innumerable cysts [1.0], hepatic cysts [1.0].\n- Knowledge (1.5 pts): Liver cysts, Berry aneurysms, Diverticulosis
