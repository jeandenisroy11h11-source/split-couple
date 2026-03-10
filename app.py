import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
import time

# --- 1. CONFIGURATION & LOGO ---
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1611/1611179.png" 

st.set_page_config(
    page_title="Splitwise Couple", 
    page_icon="💰",
    layout="centered"
)

st.markdown(f"""
    <head>
        <link rel="apple-touch-icon" href="{LOGO_URL}">
        <link rel="icon" href="{LOGO_URL}">
    </head>
    """, unsafe_allow_html=True)

DEVISE = "CAD"
UTILISATEURS = ["Jean-Denis", "Élyane"]

# --- GESTION DU PROFIL (LOGIQUE) ---
if "current_user" not in st.session_state:
    url_user = st.query_params.get("user")
    if url_user in UTILISATEURS:
        st.session_state["current_user"] = url_user
    else:
        st.session_state["current_user"] = UTILISATEURS[0]

user_invite = st.session_state["current_user"]
index_defaut = UTILISATEURS.index(user_invite)

# Initialisation formulaire
if "desc_val" not in st.session_state: st.session_state.desc_val = ""
if "amount_val" not in st.session_state: st.session_state.amount_val = None

# --- 2. CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. FORMULAIRE D'AJOUT ---
st.header("💰 Dépenses en tant que couple")

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

amount_input_val = amount if amount is not None else 0.0
part_payer = (amount_input_val * pct_payer) / 100
part_autre = amount_input_val - part_payer
autre_personne = UTILISATEURS[1] if payer == UTILISATEURS[0] else UTILISATEURS[0]

if amount_input_val > 0:
    c1, c2 = st.columns(2)
    c1.caption(f"👤 {payer}: **{part_payer:.2f}$**")
    c2.caption(f"👤 {autre_personne}: **{part_autre:.2f}$**")

is_periodic = st.checkbox("Dépense mensuelle")

if st.button("Enregistrer la dépense", type="primary", use_container_width=True):
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
                st.toast("Dépense enregistrée !", icon="✅")
                st.balloons() 
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Erreur d'envoi : {e}")

# --- 4. CALCUL DU SOLDE ---
try:
    raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = raw_url.split('/edit')[0] + '/export?format=csv'
    df = pd.read_csv(csv_url)

    if not df.empty:
        for col in ['Montant_Total', 'Part_Payeur', 'Part_Autre']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df['Mois'] = pd.to_datetime(df['Date']).dt.to_period('M').astype(str)
        
        jd_du = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum()
        el_du = df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()
        solde_net = jd_du - el_du 

        if user_invite == "Jean-Denis":
            if solde_net > 0: st.success(f"💰 Élyane te doit **{abs(solde_net):.2f}$**")
            elif solde_net < 0: st.warning(f"💸 Tu dois **{abs(solde_net):.2f}$** à Élyane")
            else: st.info("✅ Vous êtes quitte !")
        else:
            if solde_net < 0: st.success(f"💰 Jean-Denis te doit **{abs(solde_net):.2f}$**")
            elif solde_net > 0: st.warning(f"💸 Tu dois **{abs(solde_net):.2f}$** à Jean-Denis")
            else: st.info("✅ Vous êtes quitte !")

        st.markdown("---")
        with st.expander("🔎 Historique & Suppression"):
            mois_actuel = datetime.now().strftime("%Y-%m")
            liste_mois = sorted([m for m in df['Mois'].unique() if pd.notna(m)], reverse=True)
            mois_sel = st.selectbox("Filtrer par mois", ["Tous"] + liste_mois, 
                                   index=liste_mois.index(mois_actuel)+1 if mois_actuel in liste_mois else 0)
            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            st.dataframe(disp_df.drop(columns=['Mois']).sort_values(by="Date", ascending=False), use_container_width=True)
            
            st.subheader("🗑️ Supprimer")
            index_dernier = len(disp_df) - 1 if not disp_df.empty else 0
            choix = st.selectbox("Sélectionner la ligne", options=disp_df.index, index=index_dernier,
                               format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']})")
            if st.button("Confirmer la suppression", use_container_width=True):
                requests.post(st.secrets["api"]["url"], json={"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])})
                st.rerun()

        with st.expander("⚙️ Récurrences mensuelles"):
            df_rec_m = df[(df['Periodique'] == 'Oui') & (~df['Description'].str.contains("\[AUTO\]", na=False))].drop_duplicates(subset=['Description', 'Montant_Total'])
            if not df_rec_m.empty:
                deja_faites = df[(df['Mois'] == mois_actuel) & (df['Description'].str.contains("\[AUTO\]", na=False))]['Description'].tolist()
                manquantes = [row for _, row in df_rec_m.iterrows() if f"[AUTO] {row['Description']}" not in deja_faites]
                if manquantes:
                    if st.button(f"🔄 Générer les manquantes", use_container_width=True):
                        for m_row in manquantes:
                            requests.post(st.secrets["api"]["url"], json={"Date": datetime.now().strftime("%Y-%m-%d"), "Description": f"[AUTO] {m_row['Description']}", "Montant_Total": float(m_row['Montant_Total']), "Payeur": m_row['Payeur'], "Part_Payeur": float(m_row['Part_Payeur']), "Part_Autre": float(m_row['Part_Autre']), "Periodique": "Oui"})
                        st.rerun()
                else: st.success("À jour.")
except Exception as e:
    st.error(f"Erreur technique : {e}")

# --- 5. SÉLECTEUR DE PROFIL (TOUT EN BAS) ---
st.divider()
c_txt, c_sel = st.columns([1.5, 1])
with c_txt:
    st.caption(f"📱 Session actuelle : **{st.session_state['current_user']}**")
with c_sel:
    nouveau_user = st.selectbox("Changer", UTILISATEURS, 
                                label_visibility="collapsed",
                                index=UTILISATEURS.index(st.session_state["current_user"]),
                                key="bottom_user_selector")
    if nouveau_user != st.session_state["current_user"]:
        st.session_state["current_user"] = nouveau_user
        st.rerun()