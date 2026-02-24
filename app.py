import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import requests
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Splitwise gratuit", page_icon="💰")
DEVISE = "CAD"
UTILISATEURS = ["Jean-Denis", "Élyane"]

# 1. FONCTION POUR VIDER LES CHAMPS (Callback)
def clear_form():
    st.session_state["input_desc"] = ""
    st.session_state["input_amount"] = None

# Gestion des utilisateurs via l'URL
query_params = st.query_params
user_invite = query_params.get("user", UTILISATEURS[0])
index_defaut = UTILISATEURS.index(user_invite) if user_invite in UTILISATEURS else 0

st.title("💰 Dépenses en tant que couple")

# --- CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SECTION 1 : AJOUTER UNE DÉPENSE ---st.header("📝 Ajouter une dépense")
col1, col2 = st.columns(2)

with col1:
    description = st.text_input("Où ?", placeholder="Ex: Maxi", key="input_desc")
    amount = st.number_input(f"Montant ({DEVISE})", min_value=0.0, step=1.00, value=None, placeholder="0.00", key="input_amount")
    date_depense = st.date_input("Date", datetime.now(), key="input_date")

with col2:
    payer = st.selectbox("Qui a payé ?", UTILISATEURS, index=index_defaut)
    split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Perso %"])
    
    if split_mode == "100/0": pct_payer = 100.0
    elif split_mode == "0/100": pct_payer = 0.0
    elif split_mode == "Perso %": pct_payer = st.slider("Part payeur (%)", 0, 100, 50)
    else: pct_payer = 50.0

amount_val = amount if amount is not None else 0.0
part_autre = amount_val - ((amount_val * pct_payer) / 100)
is_periodic = st.checkbox("Dépense mensuelle")

# 2. BOUTON AVEC CALLBACK
if st.button("Enregistrer la dépense", type="primary"):
    if description and amount_val > 0:
        payload = {
            "Date": date_depense.strftime("%Y-%m-%d"),
            "Description": description,
            "Montant_Total": float(amount_val),
            "Payeur": payer,
            "Part_Payeur": float(amount_val - part_autre),
            "Part_Autre": float(part_autre),
            "Periodique": "Oui" if is_periodic else "Non"
        }
        try:
            res = requests.post(st.secrets["api"]["url"], json=payload)
            if res.status_code == 200:
                st.balloons()
                st.success("🎉 Enregistré !")
                # On vide manuellement avant le rerun pour cette fois-ci
                clear_form()
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Erreur d'envoi : {e}")

# --- CHARGEMENT ET NETTOYAGE ---
try:
    raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = raw_url.split('/edit')[0] + '/export?format=csv'
    df = pd.read_csv(csv_url)

    if not df.empty:
        # Nettoyage des virgules
        for col in ['Montant_Total', 'Part_Payeur', 'Part_Autre']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df['Mois'] = pd.to_datetime(df['Date']).dt.to_period('M').astype(str)
        
        # --- SECTION 2 : ÉTAT & HISTORIQUE ---
        st.markdown("---")
        st.header("📈 État & Historique")
        
        solde_global = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum() - df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()

        if solde_global > 0:
            st.warning(f"💰 **SOLDE :** Élyane doit **{abs(solde_global):.2f} {DEVISE}** à Jean-Denis")
        elif solde_global < 0:
            st.success(f"💰 **SOLDE :** Jean-Denis doit **{abs(solde_global):.2f} {DEVISE}** à Élyane")
        else:
            st.info("✅ Équilibre parfait !")

        mois_actuel = datetime.now().strftime("%Y-%m")
        liste_mois = sorted([m for m in df['Mois'].unique() if pd.notna(m)], reverse=True)
        default_idx = liste_mois.index(mois_actuel) if mois_actuel in liste_mois else 0

        with st.expander("🔎 Détails & Suppression"):
            mois_sel = st.selectbox("Filtrer par mois", ["Tous"] + liste_mois, index=default_idx + 1 if "Tous" in ["Tous"] else default_idx)
            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            
            # Affichage trié (plus récent en haut)
            st.dataframe(disp_df.drop(columns=['Mois']).sort_values(by="Date", ascending=False), use_container_width=True)
            
            st.subheader("🗑️ Supprimer une ligne")
            index_dernier = len(disp_df) - 1 if len(disp_df) > 0 else 0
            choix = st.selectbox(
                "Choisir la dépense", 
                options=disp_df.index, 
                index=index_dernier,
                format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']})"
            )
            if st.button("Confirmer la suppression"):
                p_del = {"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])}
                requests.post(st.secrets["api"]["url"], json=p_del)
                st.rerun()

        # --- SECTION 3 : RÉCURRENCES ---
        st.markdown("---")
        st.header("⚙️ Récurrences")
        
        df_modeles = df[(df['Periodique'] == 'Oui') & (~df['Description'].str.contains("\[AUTO\]", na=False))]
        df_rec = df_modeles.drop_duplicates(subset=['Description', 'Montant_Total'])
        
        if not df_rec.empty:
            with st.expander(f"📋 Gestion des récurrences", expanded=True):
                deja_faites_ce_mois = df[(df['Mois'] == mois_actuel) & (df['Description'].str.contains("\[AUTO\]", na=False))]['Description'].unique().tolist()
                manquantes = [row for _, row in df_rec.iterrows() if f"[AUTO] {row['Description']}" not in deja_faites_ce_mois]
                
                if manquantes:
                    df_man = pd.DataFrame(manquantes)
                    st.warning(f"⚠️ Il manque **{len(manquantes)}** récurrences pour {mois_actuel}")
                    st.table(df_man[['Description', 'Montant_Total', 'Payeur']])
                    
                    if st.button(f"🔄 Générer les {len(manquantes)} manquantes"):
                        for m_row in manquantes:
                            p_auto = {"Date": datetime.now().strftime("%Y-%m-%d"), "Description": f"[AUTO] {m_row['Description']}", "Montant_Total": float(m_row['Montant_Total']), "Payeur": m_row['Payeur'], "Part_Payeur": float(m_row['Part_Payeur']), "Part_Autre": float(m_row['Part_Autre']), "Periodique": "Oui"}
                            requests.post(st.secrets["api"]["url"], json=p_auto)
                        st.success("🎉 Récurrences ajoutées !")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.success(f"✅ Toutes les récurrences sont à jour pour {mois_actuel}.")
except Exception as e:
    st.error(f"Erreur technique : {e}")