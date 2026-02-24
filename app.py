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

# Paramètres URL pour le lien personnalisé
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
    amount = st.number_input(f"Montant ({DEVISE})", min_value=0.0, step=0.01, value=None, placeholder="0.00")
    date_depense = st.date_input("Date", datetime.now())

with col2:
    payer = st.selectbox("Qui a payé ?", UTILISATEURS, index=index_defaut)
    split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Perso %"])
    
    if split_mode == "100/0": pct_payer = 100.0
    elif split_mode == "0/100": pct_payer = 0.0
    elif split_mode == "Perso %": pct_payer = st.slider("Part payeur (%)", 0, 100, 50)
    else: pct_payer = 50.0

amount_val = amount if amount is not None else 0.0
autre_personne = UTILISATEURS[1] if payer == UTILISATEURS[0] else UTILISATEURS[0]
part_payer = (amount_val * pct_payer) / 100
part_autre = amount_val - part_payer

st.write(f"**Part de {payer} :** {part_payer:.2f} | **Part de {autre_personne} :** {part_autre:.2f}")
is_periodic = st.checkbox("Dépense périodique (mensuelle)")

if st.button("🚀 Enregistrer la dépense", type="primary"):
    if description and amount_val > 0:
        payload = {
            "Date": date_depense.strftime("%Y-%m-%d"),
            "Description": description,
            "Montant_Total": float(amount_val),
            "Payeur": payer,
            "Part_Payeur": float(part_payer),
            "Part_Autre": float(part_autre),
            "Periodique": "Oui" if is_periodic else "Non"
        }
        res = requests.post(st.secrets["api"]["url"], json=payload)
        if res.status_code == 200:
            st.balloons()
            st.success("🎉 Enregistré !")
            time.sleep(1)
            st.rerun()

# --- CHARGEMENT DES DONNÉES ---
try:
    raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    csv_url = raw_url.split('/edit')[0] + '/export?format=csv'
    df = pd.read_csv(csv_url)

    if not df.empty:
        # Nettoyage
        df['Part_Autre'] = pd.to_numeric(df['Part_Autre'], errors='coerce').fillna(0)
        df['Montant_Total'] = pd.to_numeric(df['Montant_Total'], errors='coerce').fillna(0)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Mois'] = df['Date'].dt.to_period('M').astype(str)
        
        # --- SECTION 2 : ÉTAT & HISTORIQUE ---
        st.markdown("---")
        st.header("📈 État & Historique")
        
        solde = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum() - df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()
        if solde > 0: st.warning(f"Élyane doit **{abs(solde):.2f} {DEVISE}** à Jean-Denis")
        elif solde < 0: st.success(f"Jean-Denis doit **{abs(solde):.2f} {DEVISE}** à Élyane")
        else: st.info("✅ Équilibre parfait")

        mois_actuel = datetime.now().strftime("%Y-%m")
        liste_mois = sorted(df['Mois'].unique(), reverse=True)
        default_idx = liste_mois.index(mois_actuel) if mois_actuel in liste_mois else 0

        with st.expander("🔎 Détails & Suppression"):
            mois_sel = st.selectbox("Mois", ["Tous"] + liste_mois, index=default_idx + 1 if "Tous" in ["Tous"] else default_idx)
            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            st.dataframe(disp_df.drop(columns=['Mois']), use_container_width=True)
            
            st.subheader("🗑️ Supprimer")
            choix = st.selectbox("Ligne", options=disp_df.index, format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']})")
            if st.button("Confirmer suppression"):
                p_del = {"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])}
                requests.post(st.secrets["api"]["url"], json=p_del)
                st.rerun()

        # --- SECTION 3 : RÉCURRENCES ---
        st.markdown("---")
        st.header("⚙️ Récurrences")
        
        # On filtre les uniques qui ont été marquées 'Oui' (n'importe quand dans l'historique)
        df_rec = df[df['Periodique'] == 'Oui'].drop_duplicates(subset=['Description', 'Montant_Total'])
        
        if not df_rec.empty:
            with st.expander("📋 Liste des récurrences", expanded=True):
                st.write(f"Vous avez {len(df_rec)} dépenses récurrentes :")
                st.table(df_rec[['Description', 'Montant_Total', 'Payeur']])
                
                # Check si déjà fait ce mois-ci
                deja_genere = df[(df['Mois'] == mois_actuel) & (df['Description'].str.contains("\[AUTO\]"))]
                
                if not deja_genere.empty:
                    st.info(f"✅ Récurrences déjà injectées pour {mois_actuel}.")
                    bloque = not st.checkbox("Forcer un nouvel ajout")
                else:
                    bloque = False

                if st.button("🔄 Générer pour ce mois-ci", disabled=bloque):
                    bar = st.progress(0)
                    for i, (_, row) in enumerate(df_rec.iterrows()):
                        p_auto = {
                            "Date": datetime.now().strftime("%Y-%m-%d"),
                            "Description": f"[AUTO] {row['Description']}",
                            "Montant_Total": float(row['Montant_Total']),
                            "Payeur": row['Payeur'],
                            "Part_Payeur": float(row['Part_Payeur']),
                            "Part_Autre": float(row['Part_Autre']),
                            "Periodique": "Oui"
                        }
                        requests.post(st.secrets["api"]["url"], json=p_auto)
                        bar.progress((i + 1) / len(df_rec))
                    st.success("🎉 Les récurrences ont été ajoutées à l'historique !")
                    time.sleep(1)
                    st.rerun()
        else:
            st.info("Cochez 'Dépense périodique' lors d'un achat pour le voir ici.")
    else:
        st.info("Aucune donnée trouvée.")

except Exception as e:
    st.error(f"Erreur technique : {e}")