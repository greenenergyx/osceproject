import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Exam Generator", page_icon="🩺", layout="wide")

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
        return None, f"Erreur de connexion Drive : {e}"

def generate_osce_content(case_title, system_name):
    """Demande à Gemini de créer un cas OSCE structuré complet"""
    if not GEMINI_KEY: return None
    
    prompt = f"""
    Tu es un examinateur expert en radiologie pour un examen OSCE (type RANZCR/Radiopaedia).
    Génère un cas d'examen complet basé sur le diagnostic suivant : {case_title} (Système : {system_name}).
    
    Structure ta réponse exactement comme suit :
    
    ### CLINICAL PRESENTATION
    (Donne une courte phrase de présentation clinique pour l'étudiant)
    
    ### EXAMINATION QUESTIONS
    1. Quelles sont les observations radiologiques majeures ?
    2. Quel est le diagnostic principal ?
    3. Citez deux diagnostics différentiels.
    4. Question de connaissance (ex: association syndromique ou complication).
    5. Quelle est la conduite à tenir (Management) ?
    
    ### MARKING GUIDE (CORRECTION)
    - Observations (1.0 pt) : [Mots-clés attendus]
    - Diagnostic (1.0 pt) : [Diagnostic précis]
    - Différentiels (0.5 pt) : [2 alternatives]
    - Knowledge (0.5 pt) : [La réponse à la question 4]
    - Management (0.5 pt) : [Prochaine étape]
    
    Réponds en Français.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return "Erreur lors de la génération du contenu par l'IA."

def main():
    st.title("🩺 Radiology OSCE Case Generator")
    st.markdown("Génération de cas réels avec Marking Guide (Format Radiopaedia)")

    df, error = load_data()
    if error:
        st.error(error)
        return

    # Sidebar
    st.sidebar.header("Paramètres")
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("Système", systems)

    if st.sidebar.button("🎲 Générer un nouveau Cas"):
        subset = df if choice == "Tous" else df[df[system_col] == choice]
        if not subset.empty:
            selected_row = subset.sample(1).iloc[0]
            st.session_state.case_info = selected_row.to_dict()
            with st.spinner("L'IA prépare l'examen..."):
                st.session_state.full_osce = generate_osce_content(
                    st.session_state.case_info.get('title', 'Pathologie'),
                    st.session_state.case_info.get(system_col, 'Radiologie')
                )
            st.session_state.reveal = False
        else:
            st.warning("Aucun cas trouvé.")

    # Affichage
    if 'full_osce' in st.session_state:
        osce_text = st.session_state.full_osce
        
        # On sépare l'énoncé de la correction
        parts = osce_text.split("### MARKING GUIDE")
        enonce = parts[0]
        correction = "### MARKING GUIDE" + parts[1] if len(parts) > 1 else "Correction non générée."

        st.divider()
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown(enonce)
        
        with col2:
            st.write("### 🛠️ Outils Examinateur")
            with st.expander("Description brute (Excel)"):
                st.write(st.session_state.case_info.get('content', 'Pas de description.'))
            
            if st.button("🔓 Révéler la Correction"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal'):
                st.success("### Grille de Correction")
                st.markdown(correction)
                if 'url' in st.session_state.case_info:
                    st.caption(f"[Lien Source]({st.session_state.case_info['url']})")

if __name__ == "__main__":
    main()
