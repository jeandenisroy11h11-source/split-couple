import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Splitwise Couple", page_icon="💰")
DEVISE = "CAD"
UTILISATEURS = ["Jean-Denis", "Élyane"]

# Récupération de l'utilisateur
query_params = st.query_params
user_invite = query_params.get("user", UTILISATEURS[0])
index_defaut = UTILISATEURS.index(user_invite) if user_invite in UTILISATEURS else 0

st.title("💰 Dépenses du Couple")

# --- CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SECTION 1 : AJOUTER UNE DÉPENSE ---
st.header("📝 Ajouter une dépense")
col1, col2 = st.columns(2)
with col1:
    description = st.text_input("Quoi ?", placeholder="Ex: Épicerie")
    amount = st.number_input(f"Montant ({DEVISE})", min_value=0.0, step=0.01)
    date_depense = st.date_input("Date", datetime.now())

with col2:
    payer = st.selectbox("Qui a payé ?", UTILISATEURS, index=index_defaut)
    split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Personnalisée %"])
    
    if split_mode == "100/0":
        pct_payer = 100.0
    elif split_mode == "0/100":
        pct_payer = 0.0
    elif split_mode == "Personnalisée %":
        pct_payer = st.slider("Part payée par le payeur (%)", 0, 100, 50)
    else:
        pct_payer = 50.0

autre_personne = UTILISATEURS[1] if payer == UTILISATEURS[0] else UTILISATEURS[0]
part_payer = (amount * pct_payer) / 100
part_autre = amount - part_payer

st.write(f"**Part de {payer} :** {part_payer:.2f} {DEVISE} | **Part de {autre_personne} :** {part_autre:.2f} {DEVISE}")
is_periodic = st.checkbox("Dépense périodique (mensuelle)")

if st.button("🚀 Enregistrer la dépense", type="primary"):
    if description and amount > 0:
        payload = {
            "Date": date_depense.strftime("%Y-%m-%d"),
            "Description": description,
            "Montant_Total": float(amount),
            "Payeur": payer,
            "Part_Payeur": float(part_payer),
            "Part_Autre": float(part_autre),
            "Periodique": "Oui" if is_periodic else "Non"
        }
        try:
            url_script = st.secrets["api"]["url"]
            response = requests.post(url_script, json=payload)
            if response.status_code == 200:
                st.balloons()
                st.success("🎉 Enregistré !")
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Erreur d'envoi : {e}")
    else:
        st.error("Remplis la description et le montant !")

# --- SECTION 2 : ÉTAT DES COMPTES & HISTORIQUE ---
st.markdown("---")
st.header("📈 État des comptes & Historique")

try:
    raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = raw_url.split('/edit')[0] + '/export?format=csv'
    df = pd.read_csv(csv_url)

    if not df.empty:
        # --- NETTOYAGE DES DONNÉES (CORRIGE L'ERREUR STR/INT) ---
        df['Part_Autre'] = pd.to_numeric(df['Part_Autre'], errors='coerce').fillna(0)
        df['Montant_Total'] = pd.to_numeric(df['Montant_Total'], errors='coerce').fillna(0)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # 1. Calcul du solde GLOBAL
        du_a_jean = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum()
        du_a_elyane = df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()
        solde_global = float(du_a_jean) - float(du_a_elyane)

        if solde_global > 0:
            st.warning(f"💰 **SOLDE GLOBAL :** Élyane doit **{abs(solde_global):.2f} {DEVISE}** à Jean-Denis")
        elif solde_global < 0:
            st.success(f"💰 **SOLDE GLOBAL :** Jean-Denis doit **{abs(solde_global):.2f} {DEVISE}** à Élyane")
        else:
            st.info("✅ Tout est à jour !")

        # 2. Historique et Suppression
        with st.expander("🔎 Détails & Suppression d'erreurs"):
            df['Mois'] = df['Date'].dt.to_period('M').astype(str)
            liste_mois = sorted(df['Mois'].unique(), reverse=True)
            mois_selectionne = st.selectbox("Filtrer par mois", ["Tous"] + liste_mois)
            
            display_df = df if mois_selectionne == "Tous" else df[df['Mois'] == mois_selectionne]
            st.dataframe(display_df.drop(columns=['Mois']), use_container_width=True)

            st.subheader("🗑️ Supprimer une ligne")
            choix_suppr = st.selectbox("Choisir la dépense à effacer", options=display_df.index, 
                                      format_func=lambda x: f"{display_df.loc[x, 'Description']} ({display_df.loc[x, 'Montant_Total']})")
            
            if st.button("Confirmer la suppression"):
                row = display_df.loc[choix_suppr]
                payload_del = {"action": "delete", "Description": str(row['Description']), "Montant_Total": float(row['Montant_Total'])}
                res = requests.post(st.secrets["api"]["url"], json=payload_del)
                if res.status_code == 200:
                    st.success("Supprimé !")
                    time.sleep(1)
                    st.rerun()

    else:
        st.info("Le document est vide.")

except Exception as e:
    st.error(f"Erreur de lecture : {e}")

# --- SECTION 3 : RÉCURRENCES ---
st.markdown("---")
st.header("⚙️ Gestion des Récurrences")
try:
    if not df.empty:
        df_recurrences = df[df['Periodique'] == 'Oui'].drop_duplicates(subset=['Description', 'Montant_Total'])
        if not df_recurrences.empty:
            with st.expander("📋 Voir et générer"):
                st.dataframe(df_recurrences[['Description', 'Montant_Total', 'Payeur']], use_container_width=True)
                if st.button("🔄 Générer pour ce mois"):
                    for _, row in df_recurrences.iterrows():
                        p_auto = {"Date": datetime.now().strftime("%Y-%m-%d"), "Description": f"[AUTO] {row['Description']}", "Montant_Total": float(row['Montant_Total']), "Payeur": row['Payeur'], "Part_Payeur": float(row['Part_Payeur']), "Part_Autre": float(row['Part_Autre']), "Periodique": "Oui"}
                        requests.post(st.secrets["api"]["url"], json=p_auto)
                    st.rerun()
except:
    pass