import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
import time

# --- CONFIGURATION ---
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1611/1611179.png" 

st.set_page_config(
    page_title="Splitwise gratuit", 
    page_icon="💰",
    layout="centered"
)

# Injection HTML pour l'icône mobile
st.markdown(f"""
    <head>
        <link rel="apple-touch-icon" href="{LOGO_URL}">
        <link rel="icon" href="{LOGO_URL}">
    </head>
    """, unsafe_allow_html=True)

DEVISE = "CAD"
UTILISATEURS = ["Jean-Denis", "Élyane"]

# Gestion user
user_invite = st.query_params.get("user", UTILISATEURS[0])
index_defaut = UTILISATEURS.index(user_invite) if user_invite in UTILISATEURS else 0

# Initialisation session_state
if "desc_val" not in st.session_state: st.session_state.desc_val = ""
if "amount_val" not in st.session_state: st.session_state.amount_val = None

# --- titre ---st.title("💰 Dépenses Couple")

# --- CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SECTION 1 : FORMULAIRE COMPACT ---
# On utilise des colonnes pour tout mettre sur 2 ou 3 lignes max
row1_col1, row1_col2 = st.columns([2, 1])
with row1_col1:
    description = st.text_input("Où ?", value=st.session_state.desc_val, placeholder="Ex: Maxi")
with row1_col2:
    amount = st.number_input(f"Montant", min_value=0.0, step=1.00, value=st.session_state.amount_val, placeholder="0.00")

row2_col1, row2_col2 = st.columns(2)
with row2_col1:
    date_depense = st.date_input("Date", datetime.now())
with row2_col2:
    payer = st.selectbox("Payé par", UTILISATEURS, index=index_defaut)

split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Perso %"], horizontal=True)

if split_mode == "Perso %":
    pct_payer = st.slider("Part payeur (%)", 0, 100, 50)
elif split_mode == "100/0": pct_payer = 100.0
elif split_mode == "0/100": pct_payer = 0.0
else: pct_payer = 50.0

# Calculs
amount_input_val = amount if amount is not None else 0.0
part_payer = (amount_input_val * pct_payer) / 100
part_autre = amount_input_val - part_payer
autre_personne = UTILISATEURS[1] if payer == UTILISATEURS[0] else UTILISATEURS[0]

# --- AFFICHAGE RÉPARTITION ULTRA-COMPACT ---
if amount_input_val > 0:
    c1, c2 = st.columns(2)
    c1.caption(f"👤 {payer}: **{part_payer:.2f}$**")
    c2.caption(f"👤 {autre_personne}: **{part_autre:.2f}$**")

is_periodic = st.checkbox("Dépense mensuelle")

if st.button("🚀 Enregistrer", type="primary", use_container_width=True):
    if description and amount_input_val > 0:
        payload = {
            "Date": date_depense.strftime("%Y-%m-%d"),
            "Description": description,
            "Montant_Total": float(amount_input_val),
            "Payeur": payer,
            "Part_Payeur": float(part_payer),
            "Part_Autre": float(part_autre),
            "Periodique": "Oui" if is_periodic else "Non"
        }
        try:
            res = requests.post(st.secrets["api"]["url"], json=payload)
            if res.status_code == 200:
                st.session_state.desc_val = ""
                st.session_state.amount_val = None
                st.balloons()
                st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

# --- SECTION 2 : HISTORIQUE ET RÉCURRENCES ---
try:
    raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = raw_url.split('/edit')[0] + '/export?format=csv'
    df = pd.read_csv(csv_url)

    if not df.empty:
        # Nettoyage
        for col in ['Montant_Total', 'Part_Payeur', 'Part_Autre']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df['Mois'] = pd.to_datetime(df['Date']).dt.to_period('M').astype(str)
        
        st.markdown("---")
        # Solde en petit format
        jd_du = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum()
        el_du = df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()
        solde = jd_du - el_du

        if solde > 0: st.warning(f"Élyane doit **{abs(solde):.2f}$** à JD")
        elif solde < 0: st.success(f"JD doit **{abs(solde):.2f}$** à Élyane")
        else: st.info("Équilibre parfait !")

        with st.expander("🔎 Historique & Suppression"):
            mois_actuel = datetime.now().strftime("%Y-%m")
            liste_mois = sorted([m for m in df['Mois'].unique() if pd.notna(m)], reverse=True)
            mois_sel = st.selectbox("Mois", ["Tous"] + liste_mois, index=liste_mois.index(mois_actuel)+1 if mois_actuel in liste_mois else 0)
            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            st.dataframe(disp_df.drop(columns=['Mois']).sort_values(by="Date", ascending=False), use_container_width=True)
            
            # Suppression simplifiée
            choix = st.selectbox("Supprimer une ligne", options=disp_df.index, index=len(disp_df)-1 if not disp_df.empty else 0,
                               format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']})")
            if st.button("🗑️ Supprimer"):
                requests.post(st.secrets["api"]["url"], json={"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])})
                st.rerun()

        # Récurrences compactes
        df_rec_m = df[(df['Periodique'] == 'Oui') & (~df['Description'].str.contains("\[AUTO\]", na=False))].drop_duplicates(subset=['Description', 'Montant_Total'])
        if not df_rec_m.empty:
            with st.expander("⚙️ Récurrences"):
                deja_faites = df[(df['Mois'] == mois_actuel) & (df['Description'].str.contains("\[AUTO\]", na=False))]['Description'].tolist()
                manquantes = [row for _, row in df_rec_m.iterrows() if f"[AUTO] {row['Description']}" not in deja_faites]
                if manquantes:
                    if st.button(f"🔄 Générer {len(manquantes)} récurrences"):
                        for m_row in manquantes:
                            requests.post(st.secrets["api"]["url"], json={"Date": datetime.now().strftime("%Y-%m-%d"), "Description": f"[AUTO] {m_row['Description']}", "Montant_Total": float(m_row['Montant_Total']), "Payeur": m_row['Payeur'], "Part_Payeur": float(m_row['Part_Payeur']), "Part_Autre": float(m_row['Part_Autre']), "Periodique": "Oui"})
                        st.rerun()
                else: st.success("À jour !")
except Exception as e:
    st.error(f"Erreur : {e}")