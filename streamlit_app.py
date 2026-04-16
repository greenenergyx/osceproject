import streamlit as st
import pandas as pd
import requests
import random

# --- CONFIGURATION ---
EXCEL_ID = st.secrets.get("EXCEL_DRIVE_ID", "")
CSV_ID = st.secrets.get("CSV_DRIVE_ID", "")

st.set_page_config(page_title="Radiology OSCE Generator", page_icon="🩺", layout="wide")

def get_drive_url(file_id):
    return f"https://docs.google.com/uc?export=download&id={file_id}"

@st.cache_data(ttl=3600)
def load_data():
    excel_df, csv_df = None, None
    if EXCEL_ID:
        try: excel_df = pd.read_excel(get_drive_url(EXCEL_ID))
        except: pass
    if CSV_ID:
        try: csv_df = pd.read_csv(get_drive_url(CSV_ID))
        except: pass
    return excel_df, csv_df

# --- INTERFACE ---
def main():
    st.title("🩺 Radiology OSCE Case Generator")
    
    ex_df, cs_df = load_data()
    df = pd.concat([ex_df, cs_df], ignore_index=True) if ex_df is not None else cs_df

    if df is None or df.empty:
        st.error("⚠️ Données non trouvées. Vérifiez les IDs dans les Secrets Streamlit.")
        return

    st.sidebar.header("Paramètres de l'examen")
    system_list = ["Tous"] + sorted(df['system'].unique().tolist())
    choice = st.sidebar.selectbox("Système", system_list)
    
    if st.sidebar.button("🎲 Générer un Cas"):
        subset = df if choice == "Tous" else df[df['system'] == choice]
        case = subset.sample(1).iloc[0]
        
        st.divider()
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header(f"Cas Clinique : {case['system']}")
            st.markdown("### 📝 Présentation pour l'étudiant")
            # On affiche un extrait clinique ou le début du texte
            st.info(f"Un patient se présente pour une imagerie concernant : **{case['title']}**.\n\n"
                    "*(L'examinateur doit fournir les images correspondantes)*")
            
            with st.expander("👁️ Voir la description des images (Aide examinateur)"):
                st.write(case['content'])

        with col2:
            if st.button("🔓 Révéler la Solution"):
                st.success(f"### Diagnostic : {case['title']}")
                st.markdown("#### 📊 Grille de Points")
                st.markdown("- **Observations** (1.0 pt)\n- **Diagnostic correct** (1.0 pt)\n- **DDx pertinents** (0.5 pt)\n- **Management** (0.5 pt)")
                st.caption(f"Lien : [Radiopaedia Article]({case['url']})")

if __name__ == "__main__":
    main()
