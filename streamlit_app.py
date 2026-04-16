import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Exam", page_icon="🩺", layout="wide")

@st.cache_data(ttl=600)
def load_data_from_drive(file_id):
    if not file_id: return None, "ID manquant."
    url = f'https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx'
    try:
        response = requests.get(url)
        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df, None
    except Exception as e:
        return None, str(e)

def ask_gemini(prompt):
    if not GEMINI_KEY: return "IA indisponible."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "Erreur de génération."

# --- INTERFACE ---
def main():
    st.title("🩺 Simulateur d'Examen Radiology OSCE")
    st.caption("Format basé sur les standards Radiopaedia / RANZCR")

    df, error = load_data_from_drive(FILE_ID)
    if error:
        st.error(f"Erreur de chargement : {error}")
        return

    # Sidebar
    st.sidebar.header("Paramètres de l'examen")
    system_col = 'system' if 'system' in df.columns else df.columns[0]
    systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
    choice = st.sidebar.selectbox("Filtrer par système", systems)

    if st.sidebar.button("🎲 Générer un nouveau Cas d'Examen"):
        subset = df if choice == "Tous" else df[df[system_col] == choice]
        st.session_state.current_case = subset.sample(1).iloc[0]
        st.session_state.reveal = False

    if 'current_case' in st.session_state:
        case = st.session_state.current_case
        st.divider()

        # Étape 1 : Présentation de l'examen
        st.header(f"Cas Clinique : {case.get('system', 'Radiologie générale').upper()}")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📝 Énoncé pour le candidat")
            st.info(f"**Présentation :** Un patient se présente pour une imagerie concernant : **{case.get('title', 'Cas inconnu')}**.")
            st.write("**Questions de l'examinateur :**")
            st.markdown("""
            1. Quelles sont vos constatations sur ces images ?
            2. Quel est votre diagnostic principal ?
            3. Donnez deux diagnostics différentiels pertinents.
            4. Quelles sont les complications classiques ou associations syndromiques ?
            5. Quelle est la prochaine étape de prise en charge ?
            """)

        with col2:
            with st.expander("👁️ Description Technique (Aide Examinateur)"):
                st.write(case.get('content', 'Aucune donnée.'))

        # Étape 2 : Révélation du Marking Guide
        if st.button("🔓 Afficher le Marking Guide (Correction)"):
            st.session_state.reveal = True

        if st.session_state.get('reveal'):
            diag = case.get('title', 'Inconnu')
            st.divider()
            st.success(f"### SOLUTION : {diag}")

            # Génération de la grille de correction par l'IA
            with st.spinner("Génération de la grille de correction détaillée..."):
                prompt = f"""
                En tant qu'examinateur de radiologie (OSCE), crée une grille de correction (Marking Guide) 
                pour le cas suivant : {diag}. 
                Détaille les points comme ceci :
                - Observations (1.0 pt) : [mots-clés précis]
                - Diagnostic (1.0 pt) : [nom exact]
                - DDx (0.5 pt) : [deux alternatives]
                - Pathologie/Connaissance (0.5 pt) : [complication ou signe classique]
                - Management (0.5 pt) : [action suivante]
                Réponds en français sous forme de tableau ou liste structurée.
                """
                marking_guide = ask_gemini(prompt)
                
            st.markdown("#### 📊 Barème de Correction (Marking Guide)")
            st.write(marking_guide)
            
            if 'url' in case:
                st.caption(f"[Consulter l'article complet sur Radiopaedia]({case['url']})")

if __name__ == "__main__":
    main()
