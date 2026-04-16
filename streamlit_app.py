import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION DES SECRETS ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Generator", page_icon="🩺", layout="wide")

@st.cache_data(ttl=600)
def load_data():
    if not FILE_ID: return None, "ID Excel manquant dans les Secrets Streamlit."
    url = f'https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx'
    try:
        response = requests.get(url)
        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df, None
    except Exception as e:
        return None, f"Erreur Drive : {e}"

def generate_osce_content(case_title, system_name):
    """Génère le cas OSCE via l'API Gemini 1.5 Flash"""
    if not GEMINI_KEY:
        return "Erreur : Clé API Gemini manquante dans les secrets."
    
    # URL pour Gemini 1.5 Flash (plus rapide et souvent gratuit selon quota)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    Tu es un examinateur expert en radiologie (OSCE). 
    Crée un cas d'examen réel pour le diagnostic : {case_title} (Système : {system_name}).
    
    Structure ta réponse ainsi :
    ### CLINICAL PRESENTATION
    (Une phrase de contexte clinique pour l'étudiant)
    
    ### EXAMINATION QUESTIONS
    1. Observations radiologiques ?
    2. Diagnostic principal ?
    3. Deux différentiels ?
    4. Une question de connaissance 'High-yield' ?
    5. Management ?
    
    ### MARKING GUIDE
    - Observations (1.0 pt) : [mots-clés]
    - Diagnostic (1.0 pt)
    - Différentiels (0.5 pt)
    - Knowledge (0.5 pt)
    - Management (0.5 pt)
    
    Réponds en Français.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response_data = response.json()
        
        if response.status_code != 200:
            return f"Erreur API ({response.status_code}) : {response_data.get('error', {}).get('message', 'Erreur inconnue')}"
            
        return response_data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Case Generator")
    
    df, error = load_data()
    if error:
        st.error(error)
        return

    # Sidebar
    st.sidebar.header("Paramètres")
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("Filtrer par système", systems)

    if st.sidebar.button("🎲 Générer un nouveau Cas"):
        subset = df if choice == "Tous" else df[df[system_col] == choice]
        if not subset.empty:
            row = subset.sample(1).iloc[0]
            st.session_state.case_info = row.to_dict()
            with st.spinner("L'IA rédige l'examen..."):
                res = generate_osce_content(row.get('title', 'Pathologie'), row.get(system_col, 'Radiologie'))
                st.session_state.full_osce = res
            st.session_state.reveal = False
        else:
            st.warning("Aucun cas trouvé.")

    # Affichage
    if 'full_osce' in st.session_state:
        text = st.session_state.full_osce
        
        # Séparation Énoncé / Correction
        if "### MARKING GUIDE" in text:
            parts = text.split("### MARKING GUIDE")
            enonce, correction = parts[0], "### MARKING GUIDE" + parts[1]
        else:
            enonce, correction = text, "Grille de correction indisponible."

        st.divider()
        c1, c2 = st.columns([2, 1])

        with c1:
            st.markdown(enonce)
            
        with c2:
            st.write("### 🛠️ Actions")
            if st.button("🔓 Révéler la Correction"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### Grille de Correction")
                st.markdown(correction)
                if 'url' in st.session_state.case_info:
                    st.caption(f"[Article Radiopaedia]({st.session_state.case_info['url']})")

if __name__ == "__main__":
    main()
