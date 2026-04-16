import streamlit as st
import pandas as pd
import requests
import io
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
# On utilise .get() pour éviter que l'app plante si un secret est manquant
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
DB_ID = st.secrets.get("DATABASE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Master", page_icon="🩺", layout="wide")

# --- FONCTION DE SAUVEGARDE (Adaptée au format Flat) ---
def save_rating_to_sheets(title, content, rating):
    try:
        # Reconstitution du dictionnaire pour gspread à partir des secrets "Flat"
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
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(DB_ID).sheet1
        sheet.append_row([title, content, rating])
        return True
    except Exception as e:
        st.error(f"Erreur de base de données : {e}")
        return False

# --- CHARGEMENT DES DONNÉES ---
@st.cache_data(ttl=600)
def load_library():
    if not FILE_ID:
        st.error("ID du fichier Excel manquant dans les Secrets.")
        return None
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    try:
        res = requests.get(url)
        df = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement de la bibliothèque : {e}")
        return None

def generate_osce(title, system, model, api_v, difficulty):
    if not GEMINI_KEY:
        return "Clé API Gemini manquante."
    
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    You are a Radiology Board Examiner. 
    Task: Create a formal OSCE case for: {title} ({system}).
    Format: English, clinical presentation (short), 5 questions, and marking guide with points [0.5] or [1.0].
    Reference Level: {difficulty}.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if response.status_code != 200:
            return f"API Error: {res_json.get('error', {}).get('message', 'Unknown error')}"
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur de génération : {str(e)}"

# --- INTERFACE PRINCIPALE ---
def main():
    st.title("🩺 Radiology OSCE Simulator v4")
    st.caption("Système de feedback actif")
    
    df = load_library()
    if df is None:
        return

    # Sidebar
    st.sidebar.header("Paramètres")
    api_v = st.sidebar.radio("Version API", ["v1", "v1beta"])
    model = st.sidebar.text_input("ID du Modèle", "gemini-2.0-flash-lite")
    difficulty = st.sidebar.select_slider("Niveau", ["High-Yield", "Intermediate", "Advanced"])
    
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["All"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("Système Organique", systems)

    if st.sidebar.button("🎲 Générer un Cas"):
        subset = df if choice == "All" else df[df[system_col] == choice]
        if not subset.empty:
            row = subset.sample(1).iloc[0]
            st.session_state.current_case_title = row.get('title', 'Pathology')
            st.session_state.case_info = row.to_dict()
            
            with st.spinner("IA en cours de réflexion..."):
                st.session_state.full_osce = generate_osce(
                    st.session_state.current_case_title, row.get(system_col, 'General'), model, api_v, difficulty
                )
            st.session_state.reveal = False
            st.session_state.rated_value = None
        else:
            st.warning("Aucun cas trouvé pour ce système.")

    # Affichage du Cas
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        parts = text.split("### MARKING GUIDE") if "### MARKING GUIDE" in text else [text, ""]
        
        st.markdown(parts[0])
        st.divider()
        
        # Feedback par étoiles
        st.subheader("⭐ Évaluer la qualité du cas")
        rating = st.feedback("stars")
        
        if rating is not None and st.session_state.get('rated_value') != rating:
            with st.spinner("Enregistrement dans la base de données..."):
                if save_rating_to_sheets(st.session_state.current_case_title, text, rating + 1):
                    st.toast("Succès : Cas enregistré dans le Google Sheet !")
                    st.session_state.rated_value = rating

        if st.button("🔓 Révéler la Correction"):
            st.session_state.reveal = True
        
        if st.session_state.get('reveal'):
            st.success("### MARKING GUIDE" + parts[1])
            with st.expander("Détails de la Source"):
                st.write(f"Titre : {st.session_state.current_case_title}")
                url = st.session_state.case_info.get('url', 'N/A')
                st.write(f"Lien : [Radiopaedia]({url})")

if __name__ == "__main__":
    main()
