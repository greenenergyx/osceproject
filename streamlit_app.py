import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION ---
# Récupération de l'ID depuis les secrets
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Generator", page_icon="🩺", layout="wide")

@st.cache_data(ttl=600)
def load_data_from_drive(file_id):
    if not file_id:
        return None, "ID de fichier manquant dans les secrets."
    
    # URL de téléchargement direct pour Google Drive (format export pour Sheets/Excel)
    url = f'https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx'
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Lecture du flux binaire Excel
            df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
            return df, None
        else:
            return None, f"Erreur Google Drive (Code {response.status_code}). Vérifiez que le fichier est en mode 'Tous les utilisateurs disposant du lien'."
    except Exception as e:
        return None, f"Erreur de connexion : {str(e)}"

def ask_gemini(prompt):
    if not GEMINI_KEY: return "Clé IA manquante."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "L'IA n'est pas disponible pour le moment."

# --- INTERFACE ---
def main():
    st.title("🩺 Radiology OSCE Case Generator")
    st.markdown("---")

    # Chargement des données
    df, error = load_data_from_drive(FILE_ID)

    if error:
        st.error(error)
        st.info("💡 Assurez-vous que le fichier sur Drive est partagé en mode 'Lecteur' pour 'Tous les utilisateurs disposant du lien'.")
        return

    if df is not None:
        # Nettoyage des noms de colonnes (enlève les espaces)
        df.columns = [c.strip().lower() for c in df.columns]
        
        # Sidebar
        st.sidebar.header("Options")
        system_col = 'system' if 'system' in df.columns else df.columns[0]
        systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
        choice = st.sidebar.selectbox("Filtrer par système", systems)

        if st.sidebar.button("🎲 Générer un nouveau cas"):
            subset = df if choice == "Tous" else df[df[system_col] == choice]
            if not subset.empty:
                st.session_state.current_case = subset.sample(1).iloc[0]
                st.session_state.reveal = False
            else:
                st.warning("Aucun cas trouvé pour ce système.")

        # Affichage du cas
        if 'current_case' in st.session_state:
            case = st.session_state.current_case
            
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader(f"Système : {case.get('system', 'N/A').upper()}")
                st.write("**Énoncé :**")
                st.info("Analysez les images fournies par l'examinateur. Quel est votre diagnostic et votre conduite à tenir ?")
                
                with st.expander("📝 Description des images (Examinateur)"):
                    st.write(case.get('content', 'Aucune description disponible.'))
            
            with c2:
                if st.button("🔓 Révéler la Solution"):
                    st.session_state.reveal = True
                
                if st.session_state.get('reveal'):
                    diag = case.get('title', 'Inconnu')
                    st.success(f"**Diagnostic :** {diag}")
                    
                    # Appel IA pour les perles
                    with st.spinner("L'IA génère les points clés..."):
                        p = f"En tant qu'expert en radiologie, donne 3 points clés 'high-yield' et 2 diagnostics différentiels pour : {diag}. Réponds en français."
                        hints = ask_gemini(p)
                        st.markdown("#### 💎 Perles High-Yield")
                        st.write(hints)
                    
                    if 'url' in case:
                        st.caption(f"[Lien Radiopaedia]({case['url']})")

if __name__ == "__main__":
    main()
