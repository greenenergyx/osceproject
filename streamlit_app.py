import streamlit as st
import pandas as pd
import requests
import io

# --- CONFIGURATION ---
FILE_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Diagnostic", page_icon="🩺", layout="wide")

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

def list_available_models(api_version):
    """Interroge l'API pour lister les modèles accessibles avec votre clé"""
    if not GEMINI_KEY: return ["Clé manquante"]
    url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={GEMINI_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            models_data = res.json().get('models', [])
            # On récupère le nom court (ex: gemini-1.5-flash)
            return [m['name'].split('/')[-1] for m in models_data]
        else:
            return [f"Erreur {res.status_code}: {res.text}"]
    except Exception as e:
        return [f"Erreur technique : {str(e)}"]

def generate_osce_content(case_title, model_name, api_version):
    """Génère le cas OSCE"""
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    Tu es un examinateur expert en radiologie (OSCE). 
    Crée un cas d'examen réel pour le diagnostic : {case_title}.
    
    Réponds en Français avec ce plan :
    ### CLINICAL PRESENTATION
    ### EXAMINATION QUESTIONS (5 questions)
    ### MARKING GUIDE (Barème 0.5/1.0 pt)
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if response.status_code != 200:
            msg = res_json.get('error', {}).get('message', 'Inconnu')
            return f"Erreur API {response.status_code} : {msg}"
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Generator & Diagnostic")
    
    df, error = load_data()
    if error: st.error(error)

    # --- SIDEBAR DIAGNOSTIC ---
    st.sidebar.header("🔍 Diagnostic API")
    api_v = st.sidebar.radio("Version API", ["v1", "v1beta"], index=0)
    
    if st.sidebar.button("📋 Lister les modèles disponibles"):
        models = list_available_models(api_v)
        st.sidebar.info("Modèles détectés :")
        for m in models:
            st.sidebar.code(m)

    st.sidebar.divider()
    
    # Champ de saisie manuel pour le modèle
    selected_model = st.sidebar.text_input("Copier ici le nom du modèle (ex: gemini-1.5-flash)", "gemini-1.5-flash")
    
    # --- LOGIQUE DE GÉNÉRATION ---
    if df is not None:
        system_col = 'system' if 'system' in df.columns else df.columns[0]
        systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
        choice = st.sidebar.selectbox("Filtrer par système", systems)

        if st.sidebar.button("🎲 Générer un nouveau Cas"):
            subset = df if choice == "Tous" else df[df[system_col] == choice]
            if not subset.empty:
                row = subset.sample(1).iloc[0]
                st.session_state.case_info = row.to_dict()
                with st.spinner(f"Interrogation de {selected_model}..."):
                    res = generate_osce_content(row.get('title', 'Pathologie'), selected_model, api_v)
                    st.session_state.full_osce = res
                st.session_state.reveal = False
            else:
                st.warning("Aucun cas trouvé.")
    
    # --- AFFICHAGE ---
    if 'full_osce' in st.session_state:
        st.markdown(st.session_state.full_osce)
        st.divider()
        if st.button("🔓 Voir les infos sources"):
            st.write(f"**Diagnostic original :** {st.session_state.case_info.get('title')}")
            st.write(f"**URL :** {st.session_state.case_info.get('url', 'Pas d'URL disponible')}")

if __name__ == "__main__":
    main()
