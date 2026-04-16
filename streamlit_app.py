import streamlit as st
import pandas as pd
import requests
import random

# --- CONFIGURATION ---
EXCEL_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
CSV_ID = st.secrets.get("CSV_DRIVE_ID", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="Radiology OSCE Generator", page_icon="🩺", layout="wide")

@st.cache_data(ttl=3600)
def load_data():
    def get_url(fid): return f"https://docs.google.com/uc?export=download&id={fid}"
    ex_df, cs_df = None, None
    if EXCEL_ID:
        try: ex_df = pd.read_excel(get_url(EXCEL_ID))
        except: pass
    if CSV_ID:
        try: cs_df = pd.read_csv(get_url(CSV_ID))
        except: pass
    return ex_df, cs_df

def ask_gemini(prompt):
    """Appelle l'API Gemini pour enrichir le cas"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except:
        return "L'IA n'a pas pu générer de détails supplémentaires."

# --- INTERFACE ---
def main():
    st.title("🩺 Radiology OSCE Case Generator")
    
    ex_df, cs_df = load_data()
    df = pd.concat([ex_df, cs_df], ignore_index=True) if ex_df is not None else cs_df

    if df is None or df.empty:
        st.error("⚠️ Données non trouvées. Vérifiez les IDs dans les Secrets.")
        return

    st.sidebar.header("Paramètres")
    system_list = ["Tous"] + sorted(df['system'].unique().tolist())
    choice = st.sidebar.selectbox("Système", system_list)
    
    if st.sidebar.button("🎲 Générer un Cas"):
        subset = df if choice == "Tous" else df[df['system'] == choice]
        case = subset.sample(1).iloc[0]
        st.session_state.current_case = case
        st.session_state.reveal = False

    if 'current_case' in st.session_state:
        case = st.session_state.current_case
        st.divider()
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header(f"Cas : {case['system']}")
            st.info(f"**Énoncé :** Un patient présente des symptômes liés à cette imagerie. Analysez les signes et proposez un diagnostic.")
            with st.expander("👁️ Description des images (Aide examinateur)"):
                st.write(case['content'])

        with col2:
            if st.button("🔓 Révéler la Solution"):
                st.session_state.reveal = True
            
            if st.session_state.reveal:
                st.success(f"### {case['title']}")
                
                # Prompt pour l'IA
                prompt = f"Basé sur le diagnostic '{case['title']}', donne 3 perles cliniques 'high-yield' et 2 diagnostics différentiels importants pour un examen de radiologie."
                with st.spinner("L'IA prépare les perles cliniques..."):
                    ai_hints = ask_gemini(prompt)
                
                st.markdown("#### 💎 High-Yield Hints (AI)")
                st.write(ai_hints)
                st.caption(f"[Lien Radiopaedia]({case['url']})")

if __name__ == "__main__":
    main()
