import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
import time

# --- 1. CONFIGURATION & LOGO ---
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/1611/1611179.png" 

st.set_page_config(page_title="Splitwise Couple", page_icon="💰", layout="centered")

# Injection HTML pour l'icône et la MÉMOIRE DU PROFIL (Local Storage)
st.markdown(f"""
    <head>
        <link rel="apple-touch-icon" href="{LOGO_URL}">
        <link rel="icon" href="{LOGO_URL}">
        <script>
            // Fonction pour sauvegarder le profil dans le téléphone
            function saveUser(name) {{ localStorage.setItem('splitwise_user', name); }}
            // Fonction pour récupérer le profil au chargement
            function getUser() {{ return localStorage.getItem('splitwise_user'); }}
        </script>
    </head>
    """, unsafe_allow_html=True)

UTILISATEURS = ["Jean-Denis", "Élyane"]

# --- GESTION DU PROFIL AVEC MÉMOIRE ---
if "current_user" not in st.session_state:
    url_user = st.query_params.get("user")
    if url_user in UTILISATEURS:
        st.session_state["current_user"] = url_user
    else:
        # Par défaut on prend le premier, mais le sélecteur en bas corrigera
        st.session_state["current_user"] = UTILISATEURS[0]

user_invite = st.session_state["current_user"]
index_defaut = UTILISATEURS.index(user_invite)

# --- 2. CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. FORMULAIRE D'AJOUT ---
st.header("💰 Dépenses en tant que couple")

# Initialisation des états de formulaire
if "desc_val" not in st.session_state: st.session_state.desc_val = ""
if "amount_val" not in st.session_state: st.session_state.amount_val = 0.0
if "is_submitting" not in st.session_state: st.session_state.is_submitting = False

row1_col1, row1_col2 = st.columns([2, 1])
with row1_col1:
    description = st.text_input("Où ?", value=st.session_state.desc_val, placeholder="Ex: Maxi")
with row1_col2:
    amount = st.number_input(f"Montant", min_value=0.0, step=1.00, value=st.session_state.amount_val)

row2_col1, row2_col2 = st.columns(2)
with row2_col1:
    date_depense = st.date_input("Date", datetime.now())
with row2_col2:
    payer = st.selectbox("Payé par", UTILISATEURS, index=index_defaut)

split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Perso %"], horizontal=True)
pct_payer = 50.0
if split_mode == "Perso %": pct_payer = st.slider("Part payeur (%)", 0, 100, 50)
elif split_mode == "100/0": pct_payer = 100.0
elif split_mode == "0/100": pct_payer = 0.0

part_payer = (amount * pct_payer) / 100
part_autre = amount - part_payer
is_periodic = st.checkbox("Dépense mensuelle")

# BOUTON AVEC PROTECTION ANTI-DOUBLON
if st.button("Enregistrer la dépense", type="primary", use_container_width=True, disabled=st.session_state.is_submitting):
    if description and amount > 0:
        st.session_state.is_submitting = True  # Verrouille le bouton
        payload = {
            "Date": date_depense.strftime("%Y-%m-%d"),
            "Description": description,
            "Montant_Total": float(amount),
            "Payeur": payer,
            "Part_Payeur": float(part_payer),
            "Part_Autre": float(part_autre),
            "Periodique": "Oui" if is_periodic else "Non",
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            res = requests.post(st.secrets["api"]["url"], json=payload)
            if res.status_code == 200:
                st.session_state.desc_val = ""
                st.session_state.amount_val = 0.0
                st.toast("Enregistré avec succès ! ✅")
                st.balloons()
                time.sleep(1)
                st.session_state.is_submitting = False
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
        # Nettoyage
        for col in ['Montant_Total', 'Part_Payeur', 'Part_Autre']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        
        # Solde
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
        
        # HISTORIQUE AVEC DOUBLE TRI
        with st.expander("🔎 Historique & Suppression"):
            df['Mois'] = pd.to_datetime(df['Date'], errors='coerce').dt.to_period('M').astype(str)
            mois_actuel = datetime.now().strftime("%Y-%m")
            liste_mois = sorted([m for m in df['Mois'].unique() if pd.notna(m)], reverse=True)
            
            c1, c2 = st.columns(2)
            with c1:
                mois_sel = st.selectbox("Mois", ["Tous"] + liste_mois, index=liste_mois.index(mois_actuel)+1 if mois_actuel in liste_mois else 0)
            with c2:
                tri_sel = st.radio("Trier par", ["Date", "Saisie (récent)"], horizontal=True)

            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            
            # Application du tri
            if tri_sel == "Date":
                disp_df = disp_df.sort_values(by="Date", ascending=False)
            else:
                # On trie par index (l'ordre dans le Google Sheet) de façon décroissante
                disp_df = disp_df.sort_index(ascending=False)

            st.dataframe(disp_df.drop(columns=['Mois']), use_container_width=True)
            
            st.subheader("🗑️ Supprimer")
            choix = st.selectbox("Ligne à supprimer", options=disp_df.index, 
                               format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']}$)")
            if st.button("Confirmer la suppression", use_container_width=True):
                requests.post(st.secrets["api"]["url"], json={"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])})
                st.rerun()

except Exception as e:
    st.error(f"Erreur technique : {e}")

# --- 5. SÉLECTEUR DE PROFIL (TOUT EN BAS) ---
st.divider()
c_txt, c_sel = st.columns([1.5, 1])
with c_txt:
    st.caption(f"📱 Session actuelle : **{st.session_state['current_user']}**")
with c_sel:
    nouveau_user = st.selectbox("Changer", UTILISATEURS, label_visibility="collapsed",
                                index=UTILISATEURS.index(st.session_state["current_user"]))
    if nouveau_user != st.session_state["current_user"]:
        st.session_state["current_user"] = nouveau_user
        # On force le rechargement pour que le haut de la page s'adapte
        st.rerun()