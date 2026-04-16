import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Generator", page_icon="🩺", layout="wide")

@st.cache_data(ttl=600)
def load_data():
    if not FILE_ID: return None, "ID Excel manquant dans les Secrets."
    url = f'https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx'
    try:
        response = requests.get(url)
        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df, None
    except Exception as e:
        return None, f"Erreur Drive : {e}"

def generate_osce_content(case_title, system_name, model_name, api_version):
    """Génère le cas OSCE avec le modèle choisi par l'utilisateur"""
    if not GEMINI_KEY:
        return "Erreur : Clé API manquante."
    
    # URL dynamique selon les choix de l'utilisateur
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    Tu es un examinateur expert en radiologie. 
    Crée un cas d'examen OSCE structuré pour le diagnostic : {case_title} (Système : {system_name}).
    
    Réponds EXACTEMENT avec ce plan :
    
    ### CLINICAL PRESENTATION
    (Une phrase de contexte clinique pour l'étudiant)
    
    ### EXAMINATION QUESTIONS
    1. Quelles sont les observations radiologiques ?
    2. Quel est le diagnostic principal ?
    3. Citez deux diagnostics différentiels.
    4. Question de connaissance spécifique (complication ou association).
    5. Quelle est la conduite à tenir ?
    
    ### MARKING GUIDE
    - Observations (1.0 pt) : [points clés]
    - Diagnostic (1.0 pt) : [nom exact]
    - Différentiels (0.5 pt) : [2 alternatives]
    - Knowledge (0.5 pt) : [réponse question 4]
    - Management (0.5 pt) : [étape suivante]
    
    Réponds en Français.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        
        if response.status_code != 200:
            err_msg = res_json.get('error', {}).get('message', 'Erreur inconnue')
            return f"Erreur API {response.status_code} ({model_name}) : {err_msg}"
            
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Case Generator")
    
    df, error = load_data()
    if error:
        st.error(error)
        return

    # --- SIDEBAR : PARAMÈTRES ET MODÈLES ---
    st.sidebar.header("⚙️ Configuration")
    
    # Choix du modèle IA
    available_models = [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro"
    ]
    selected_model = st.sidebar.selectbox("Modèle Gemini", available_models, index=0)
    
    # Choix de la version API
    api_version = st.sidebar.radio("Version API", ["v1", "v1beta"], index=0, help="Changez si vous avez une erreur 404")
    
    st.sidebar.divider()
    
    # Filtres de données
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("Filtrer par système", systems)

    if st.sidebar.button("🎲 Générer un nouveau Cas"):
        subset = df if choice == "Tous" else df[df[system_col] == choice]
        if not subset.empty:
            row = subset.sample(1).iloc[0]
            st.session_state.case_info = row.to_dict()
            with st.spinner(f"L'IA ({selected_model}) prépare le cas..."):
                st.session_state.full_osce = generate_osce_content(
                    row.get('title', 'Pathologie'), 
                    row.get(system_col, 'Radiologie'),
                    selected_model,
                    api_version
                )
            st.session_state.reveal = False
        else:
            st.warning("Aucun cas trouvé.")

    # --- AFFICHAGE DU CAS ---
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        
        if "### MARKING GUIDE" in text:
            parts = text.split("### MARKING GUIDE")
            enonce, correction = parts[0], "### MARKING GUIDE" + parts[1]
        else:
            enonce, correction = text, "Barème non disponible."

        st.divider()
        c1, c2 = st.columns([2, 1])

        with c1:
            st.markdown(enonce)
            
        with c2:
            st.write("### 🛠️ Outils Examinateur")
            if st.button("🔓 Révéler la Correction"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### Correction & Barème")
                st.markdown(correction)
                with st.expander("Données brutes Radiopaedia"):
                    st.write(st.session_state.case_info.get('content', 'Pas de description.'))
                if 'url' in st.session_state.case_info:
                    st.caption(f"[Lien Source]({st.session_state.case_info['url']})")

if __name__ == "__main__":
    main()
