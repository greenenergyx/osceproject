import streamlit as st
import pandas as pd
import requests
import random

# --- RÉCUPÉRATION DES SECRETS ---
EXCEL_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
CSV_ID = st.secrets.get("CSV_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Generator", page_icon="🩺", layout="wide")

# --- CHARGEMENT DES DONNÉES ---
def get_drive_url(file_id):
    # Lien de téléchargement direct Google Drive
    return f"https://docs.google.com/uc?export=download&id={file_id}"

@st.cache_data(ttl=600) # Rafraîchissement toutes les 10 minutes
def load_data():
    ex_df, cs_df = None, None
    errors = []
    
    # Tentative Excel
    if EXCEL_ID:
        try:
            ex_df = pd.read_excel(get_drive_url(EXCEL_ID), engine='openpyxl')
        except Exception as e:
            errors.append(f"Erreur Excel : {str(e)}")
            
    # Tentative CSV
    if CSV_ID:
        try:
            cs_df = pd.read_csv(get_drive_url(CSV_ID))
        except Exception as e:
            errors.append(f"Erreur CSV : {str(e)}")
            
    return ex_df, cs_df, errors

# --- FONCTION IA ---
def ask_gemini(prompt):
    if not GEMINI_KEY:
        return "Clé API Gemini manquante dans les Secrets."
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur IA : {str(e)}"

# --- INTERFACE PRINCIPALE ---
def main():
    st.title("🩺 Radiology OSCE Case Generator")
    
    # Chargement
    ex_df, cs_df, load_errors = load_data()
    
    # Debug dans la barre latérale si erreur
    if load_errors:
        with st.sidebar.expander("⚠️ Debug Errors"):
            for err in load_errors:
                st.write(err)

    # Fusion des données
    dfs_to_concat = [df for df in [ex_df, cs_df] if df is not None]
    
    if not dfs_to_concat:
        st.error("❌ Aucune donnée chargée. Vérifiez que vos fichiers Drive sont en mode 'Public (tous ceux avec le lien)'.")
        st.info("💡 Si vos fichiers sont volumineux, privilégiez le format CSV.")
        return

    df = pd.concat(dfs_to_concat, ignore_index=True)

    # Nettoyage minimal des colonnes pour éviter les crashs
    if 'system' not in df.columns: df['system'] = 'Unknown'
    if 'title' not in df.columns: df['title'] = 'No Title'

    # Barre latérale
    st.sidebar.header("Paramètres")
    system_list = ["Tous"] + sorted(df['system'].unique().astype(str).tolist())
    choice = st.sidebar.selectbox("Sélectionner un système", system_list)
    
    if st.sidebar.button("🎲 Générer un Cas Aléatoire"):
        subset = df if choice == "Tous" else df[df['system'] == choice]
        if not subset.empty:
            st.session_state.current_case = subset.sample(1).iloc[0]
            st.session_state.reveal = False
        else:
            st.error("Aucun cas trouvé pour ce filtre.")

    # Affichage du Cas
    if 'current_case' in st.session_state:
        case = st.session_state.current_case
        st.divider()
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header(f"Cas : {case['system']}")
            st.markdown("### 📝 Présentation Clinique")
            st.info("À lire à l'étudiant : 'Analysez l'imagerie pour ce patient et proposez un diagnostic ainsi qu'une conduite à tenir.'")
            
            with st.expander("🔍 Aide pour l'examinateur (Description des images)"):
                st.write(case.get('content', 'Pas de contenu détaillé.'))

        with col2:
            st.markdown("### 🛠️ Actions")
            if st.button("🔓 Révéler la Solution"):
                st.session_state.reveal = True
            
            if st.session_state.get('reveal', False):
                st.success(f"**Diagnostic :** {case['title']}")
                
                # Grille de points dynamique
                st.markdown("#### 📊 Marking Guide")
                st.markdown("- **Observations** (1.0 pt)")
                st.markdown("- **Diagnostic correct** (1.0 pt)")
                st.markdown("- **DDx / Management** (1.0 pt)")
                
                # Appel Gemini pour enrichir
                with st.spinner("L'IA génère les perles cliniques..."):
                    p = f"Diagnosis: {case['title']}. Give 3 radiological 'pearls' and top 2 differentials for a radiology board exam."
                    hints = ask_gemini(p)
                    st.markdown("#### 💎 High-Yield Pearls")
                    st.write(hints)
                
                if 'url' in case:
                    st.caption(f"[Lien vers Radiopaedia]({case['url']})")

if __name__ == "__main__":
    main()
