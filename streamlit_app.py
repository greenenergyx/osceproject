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
    if not FILE_ID: return None, "ID Excel manquant."
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    try:
        response = requests.get(url)
        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
        df.columns = [c.strip().lower() for c in df.columns]
        return df, None
    except Exception as e:
        return None, f"Erreur Drive : {e}"

def generate_osce_content(raw_title, model_name, api_version):
    """Génère un cas filtré et concis au format OSCE réel"""
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={GEMINI_KEY}"
    
    prompt = f"""
    Tu es un examinateur en radiologie. Ton but est de transformer l'article suivant en un cas d'examen court (OSCE).
    
    ARTICLE ORIGINAL : {raw_title}
    
    CONSIGNES DE FILTRAGE :
    1. Si l'article est un organe (ex: Radius) ou une procédure (ex: Pneumonectomie), transforme-le en une pathologie pertinente (ex: Fracture du radius ou Complication de pneumonectomie).
    2. La présentation clinique doit être TRÈS courte : juste l'âge, le sexe et un motif de consultation (ex: "Homme de 45 ans, dyspnée aiguë").
    
    STRUCTURE DE RÉPONSE :
    ### 📝 CLINICAL PRESENTATION
    [Âge], [Sexe], [1 symptôme court]
    
    ### ❓ QUESTIONS
    1. Observations principales ?
    2. Diagnostic ?
    3. Deux différentiels ?
    4. Une question théorique courte.
    5. Management ?
    
    ### ✅ MARKING GUIDE
    - Observations (1.0) : [Mots-clés]
    - Diagnostic (1.0) : [Le nom de la pathologie]
    - DDx (0.5) : [2 ddx]
    - Knowledge/Management (0.5)
    
    Réponds en Français.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if response.status_code != 200:
            return f"Erreur API : {res_json.get('error', {}).get('message')}"
        return res_json['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def main():
    st.title("🩺 Radiology OSCE Simulator (Short-Case)")
    
    df, error = load_data()
    if error: st.error(error)

    # Sidebar
    st.sidebar.header("⚙️ Configuration")
    api_v = st.sidebar.radio("Version API", ["v1", "v1beta"], index=0)
    selected_model = st.sidebar.text_input("Modèle", "gemini-1.5-flash")
    
    if df is not None:
        system_col = 'system' if 'system' in df.columns else df.columns[0]
        systems = ["Tous"] + sorted(df[system_col].dropna().unique().tolist())
        choice = st.sidebar.selectbox("Système", systems)

        if st.sidebar.button("🎲 Générer un Cas Réel"):
            subset = df if choice == "Tous" else df[df[system_col] == choice]
            if not subset.empty:
                row = subset.sample(1).iloc[0]
                st.session_state.case_info = row.to_dict()
                with st.spinner("L'IA filtre et rédige le cas..."):
                    res = generate_osce_content(row.get('title', 'Pathologie'), selected_model, api_v)
                    st.session_state.full_osce = res
                st.session_state.reveal = False

    if 'full_osce' in st.session_state:
        # Affichage scindé
        text = st.session_state.full_osce
        if "### MARKING GUIDE" in text:
            parts = text.split("### MARKING GUIDE")
            enonce, correction = parts[0], "### MARKING GUIDE" + parts[1]
        else:
            enonce, correction = text, ""

        st.markdown(enonce)
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔓 Révéler le Barème"):
                st.session_state.reveal = True
        
        if st.session_state.get('reveal'):
            st.success(correction)
            with st.expander("Source Radiopaedia"):
                st.write(f"**Titre original :** {st.session_state.case_info.get('title')}")
                st.write(f"**URL :** {st.session_state.case_info.get('url')}")

if __name__ == "__main__":
    main()
