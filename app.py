import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
import time

# --- 1. CONFIGURATION ---
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1611/1611179.png" 
st.set_page_config(page_title="Splitwise Couple", page_icon="💰", layout="centered")

st.markdown(f"""<head><link rel="apple-touch-icon" href="{LOGO_URL}"><link rel="icon" href="{LOGO_URL}"></head>""", unsafe_allow_html=True)

UTILISATEURS = ["Jean-Denis", "Élyane"]

# --- GESTION DU PROFIL & RESET ---
if "current_user" not in st.session_state:
    url_user = st.query_params.get("user")
    st.session_state["current_user"] = url_user if url_user in UTILISATEURS else UTILISATEURS[0]

if "form_id" not in st.session_state:
    st.session_state["form_id"] = 0

if "is_submitting" not in st.session_state:
    st.session_state["is_submitting"] = False

form_suffix = f"_{st.session_state['form_id']}"

# --- 2. CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. FORMULAIRE D'AJOUT ---
st.header("💰 Dépense couple")

# UTILISATEUR (Boutons horizontaux)
nouveau_user = st.radio(
    "Session de :", 
    UTILISATEURS, 
    index=UTILISATEURS.index(st.session_state["current_user"]), 
    horizontal=True, 
    key=f"session_top{form_suffix}"
)

if nouveau_user != st.session_state["current_user"]:
    st.session_state["current_user"] = nouveau_user
    st.session_state["form_id"] += 1
    st.rerun()

#st.divider()

# DESCRIPTION
description = st.text_input("Où ?", placeholder="Ex: Maxi", key=f"desc{form_suffix}")

# MONTANT
amount = st.number_input("Montant ($)", min_value=0.0, step=1.00, value=None, placeholder="0.00", key=f"amount{form_suffix}")

# PAYÉ PAR (Boutons horizontaux)
payer = st.radio(
    "Payé par :", 
    UTILISATEURS, 
    index=UTILISATEURS.index(st.session_state["current_user"]), 
    horizontal=True, 
    key=f"payer{form_suffix}"
)

# DATE (Remise en vue directe)
date_depense = st.date_input("Date", value=datetime.now(), key=f"date{form_suffix}")

# RÉPARTITION (Remise en vue directe)
split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Perso %"], horizontal=True, key=f"split{form_suffix}")

pct_payer = 50.0
if split_mode == "Perso %":
    pct_payer = st.slider("Part payeur (%)", 0, 100, 50, key=f"slider{form_suffix}")
elif split_mode == "100/0": 
    pct_payer = 100.0
elif split_mode == "0/100": 
    pct_payer = 0.0

is_periodic = st.checkbox("Dépense mensuelle", key=f"periodic{form_suffix}")

# Calculs
val_amount = amount if amount is not None else 0.0
part_payer = (val_amount * pct_payer) / 100
part_autre = val_amount - part_payer

# ENREGISTREMENT
if st.button("🚀 Enregistrer la dépense", type="primary", use_container_width=True, disabled=st.session_state.is_submitting):
    if description and val_amount > 0:
        st.session_state.is_submitting = True
        payload = {
            "Date": date_depense.strftime("%Y-%m-%d"),
            "Description": description,
            "Montant_Total": float(val_amount),
            "Payeur": payer,
            "Part_Payeur": float(part_payer),
            "Part_Autre": float(part_autre),
            "Periodique": "Oui" if is_periodic else "Non",
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            res = requests.post(st.secrets["api"]["url"], json=payload)
            if res.status_code == 200:
                st.toast("C'est enregistré ! ✅")
                st.session_state["form_id"] += 1
                st.session_state.is_submitting = False
                time.sleep(0.5)
                st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
            st.session_state.is_submitting = False

# --- 4. CALCUL DU SOLDE & HISTORIQUE ---
try:
    raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = raw_url.split('/edit')[0] + '/export?format=csv'
    df = pd.read_csv(csv_url)

    if not df.empty:
        for col in ['Montant_Total', 'Part_Payeur', 'Part_Autre']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        
        jd_du = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum()
        el_du = df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()
        solde_net = jd_du - el_du 

        if st.session_state["current_user"] == "Jean-Denis":
            if solde_net > 0: st.success(f"💰 Élyane te doit **{abs(solde_net):.2f}$**")
            elif solde_net < 0: st.warning(f"💸 Tu dois **{abs(solde_net):.2f}$** à Élyane")
            else: st.info("✅ Vous êtes quitte !")
        else:
            if solde_net < 0: st.success(f"💰 Jean-Denis te doit **{abs(solde_net):.2f}$**")
            elif solde_net > 0: st.warning(f"💸 Tu dois **{abs(solde_net):.2f}$** à Jean-Denis")
            else: st.info("✅ Vous êtes quitte !")

        st.markdown("---")
        
        with st.expander("🔎 Historique & Suppression"):
            df['Mois'] = pd.to_datetime(df['Date'], errors='coerce').dt.to_period('M').astype(str)
            mois_actuel = datetime.now().strftime("%Y-%m")
            liste_mois = sorted([m for m in df['Mois'].unique() if pd.notna(m)], reverse=True)
            
            c1, c2 = st.columns(2)
            with c1:
                mois_sel = st.selectbox("Mois", ["Tous"] + liste_mois, index=liste_mois.index(mois_actuel)+1 if mois_actuel in liste_mois else 0)
            with c2:
                tri_sel = st.radio("Trier par", ["Date", "Saisie"], horizontal=True)

            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            disp_df = disp_df.sort_values(by="Date", ascending=False) if tri_sel == "Date" else disp_df.sort_index(ascending=False)
            st.dataframe(disp_df.drop(columns=['Mois']), use_container_width=True)
            
            st.subheader("🗑️ Supprimer")
            choix = st.selectbox("Ligne", options=disp_df.index, format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']}$)")
            if st.button("Confirmer la suppression"):
                requests.post(st.secrets["api"]["url"], json={"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])})
                st.rerun()

        with st.expander("⚙️ Récurrences mensuelles"):
            mois_actuel = datetime.now().strftime("%Y-%m")
            df_rec_m = df[(df['Periodique'] == 'Oui') & (~df['Description'].str.contains("\[AUTO\]", na=False))].drop_duplicates(subset=['Description', 'Montant_Total'])
            if not df_rec_m.empty:
                deja_faites = df[(df['Mois'] == mois_actuel) & (df['Description'].str.contains("\[AUTO\]", na=False))]['Description'].tolist()
                manquantes = [row for _, row in df_rec_m.iterrows() if f"[AUTO] {row['Description']}" not in deja_faites]
                if manquantes:
                    if st.button("🔄 Générer les manquantes", use_container_width=True):
                        for m_row in manquantes:
                            requests.post(st.secrets["api"]["url"], json={"Date": datetime.now().strftime("%Y-%m-%d"), "Description": f"[AUTO] {m_row['Description']}", "Montant_Total": float(m_row['Montant_Total']), "Payeur": m_row['Payeur'], "Part_Payeur": float(m_row['Part_Payeur']), "Part_Autre": float(m_row['Part_Autre']), "Periodique": "Oui"})
                        st.rerun()
                else: st.success("À jour.")
except Exception as e:
    st.error(f"Erreur technique : {e}")