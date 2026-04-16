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
    url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={GEMINI_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            models = res.json().get('models', [])
            return [m['name'].replace('models/', '') for m in models]
        else:
            return [f"Erreur {res.status_code}: {res.text}"]
    except Exception as e:
        return [f"Erreur technique : {str(e)}"]

def generate_osce_content(case_title, system_name, model_name, api_version):
    """Génère le cas OSCE"""
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"Tu es un examinateur expert en radiologie. Crée un cas OSCE structuré pour le diagnostic : {case_title}. Réponds en Français avec Clinical Presentation, Questions, et Marking Guide."
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if response.status_code != 200:
            return f"Erreur API {response.status_code} : {res_json.get('error', {}).get('message', 'Inconnu')}"
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Generator & Diagnostic")
    
    df, error = load_data()
    
    # --- SIDEBAR DIAGNOSTIC ---
    st.sidebar.header("🔍 Diagnostic API")
    api_v = st.sidebar.radio("Version API", ["v1", "v1beta"], index=0)
    
    if st.sidebar.button("📋 Lister les modèles disponibles"):
        models = list_available_models(api_v)
        st.sidebar.write(models)

    st.sidebar.divider()
    
    # Choix manuel du modèle (vous pouvez copier-coller un nom de la liste ici)
    selected_model = st.sidebar.text_input("Nom du modèle (ex: gemini-1.5-flash)", "gemini-1.5-flash")
    
    # --- LOGIQUE DE JEU ---
    if df is not None:
        system_col = 'system' if 'system' in df.columns else df.columns[0]
        systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
        choice = st.sidebar.selectbox("Filtrer par système", systems)

        if st.sidebar.button("🎲 Générer un nouveau Cas"):
            subset = df if choice == "Tous" else df[df[system_col] == choice]
            if not subset.empty:
                row = subset.sample(1).iloc[0]
                st.session_state.case_info = row.to_dict()
                with st.spinner(f"Appel de {selected_model}..."):
                    st.session_state.full_osce = generate_osce_content(
                        row.get('title', 'Pathologie'), 
                        row.get(system_col, 'Radiologie'),
                        selected_model, api_v
                    )
                st.session_state.reveal = False
    
    # Affichage
    if 'full_osce' in st.session_state:
        st.markdown(st.session_state.full_osce)
        if st.button("🔓 Révéler la source Radiopaedia"):
            st.write(st.session_state.case_info.get('url', 'Pas d'URL'))

if __name__ == "__main__":
    main()
