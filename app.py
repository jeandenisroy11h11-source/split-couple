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

# Gestion des utilisateurs via l'URL (?user=Élyane)
query_params = st.query_params
user_invite = query_params.get("user", UTILISATEURS[0])
index_defaut = UTILISATEURS.index(user_invite) if user_invite in UTILISATEURS else 0

st.title("💰 Dépenses en tant que couple")

# --- CONNEXION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SECTION 1 : AJOUTER UNE DÉPENSE --- st.header("📝 Ajouter une dépense")
col1, col2 = st.columns(2)
with col1:
    description = st.text_input("Ou ?", placeholder="Ex: Maxi")
    amount = st.number_input(f"Montant ({DEVISE})", min_value=0.0, step=1.00, value=None, placeholder="0.00")
    date_depense = st.date_input("Date", datetime.now())

with col2:
    payer = st.selectbox("Qui a payé ?", UTILISATEURS, index=index_defaut)
    split_mode = st.radio("Répartition", ["50/50", "100/0", "0/100", "Perso %"])
    
    if split_mode == "100/0": pct_payer = 100.0
    elif split_mode == "0/100": pct_payer = 0.0
    elif split_mode == "Perso %": pct_payer = st.slider("Part payeur (%)", 0, 100, 50)
    else: pct_payer = 50.0

# Calculs de parts
amount_val = amount if amount is not None else 0.0
autre_personne = UTILISATEURS[1] if payer == UTILISATEURS[0] else UTILISATEURS[0]
part_payer = (amount_val * pct_payer) / 100
part_autre = amount_val - part_payer

st.write(f"**Part de {payer} :** {part_payer:.2f} | **Part de {autre_personne} :** {part_autre:.2f}")
is_periodic = st.checkbox("Dépense mensuelle")

if st.button("Enregistrer la dépense", type="primary"):
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
        try:
            res = requests.post(st.secrets["api"]["url"], json=payload)
            if res.status_code == 200:
                st.balloons()
                st.success("🎉 Enregistré !")
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
        # 1. Nettoyage des virgules (Crucial pour éviter l'erreur de conversion)
        cols_finance = ['Montant_Total', 'Part_Payeur', 'Part_Autre']
        for col in cols_finance:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 2. Formatage Date et Mois (Sans l'heure)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df['Mois'] = pd.to_datetime(df['Date']).dt.to_period('M').astype(str)
        
        # --- SECTION 2 : ÉTAT & HISTORIQUE ---
        st.markdown("---")
        st.header("📈 État & Historique")
        
        # Calcul du solde
        du_a_jean = df[df['Payeur'] == 'Jean-Denis']['Part_Autre'].sum()
        du_a_elyane = df[df['Payeur'] == 'Élyane']['Part_Autre'].sum()
        solde_global = float(du_a_jean) - float(du_a_elyane)

        if solde_global > 0:
            st.warning(f"💰 **SOLDE :** Élyane doit **{abs(solde_global):.2f} {DEVISE}** à Jean-Denis")
        elif solde_global < 0:
            st.success(f"💰 **SOLDE :** Jean-Denis doit **{abs(solde_global):.2f} {DEVISE}** à Élyane")
        else:
            st.info("✅ Équilibre parfait !")

        # Historique filtré
        mois_actuel = datetime.now().strftime("%Y-%m")
        liste_mois = sorted([m for m in df['Mois'].unique() if pd.notna(m)], reverse=True)
        default_idx = liste_mois.index(mois_actuel) if mois_actuel in liste_mois else 0

        with st.expander("🔎 Détails & Suppression"):
            mois_sel = st.selectbox("Filtrer par mois", ["Tous"] + liste_mois, index=default_idx + 1 if "Tous" in ["Tous"] else default_idx)
            disp_df = df if mois_sel == "Tous" else df[df['Mois'] == mois_sel]
            st.dataframe(disp_df.drop(columns=['Mois']), use_container_width=True)
            
            st.subheader("🗑️ Supprimer une ligne")
            
            # On définit l'index sur la dernière ligne (len(disp_df) - 1)
            index_dernier = len(disp_df) - 1 if len(disp_df) > 0 else 0
            
            choix = st.selectbox(
                "Choisir la dépense", 
                options=disp_df.index, 
                index=index_dernier,  # <-- C'est ici que la magie opère
                format_func=lambda x: f"{disp_df.loc[x, 'Description']} ({disp_df.loc[x, 'Montant_Total']})"
            )
            
            if st.button("Confirmer la suppression"):
                p_del = {"action": "delete", "Description": str(disp_df.loc[choix, 'Description']), "Montant_Total": float(disp_df.loc[choix, 'Montant_Total'])}
                requests.post(st.secrets["api"]["url"], json=p_del)
                st.rerun()

        # --- SECTION 3 : RÉCURRENCES (DÉTECTION INTELLIGENTE) ---
        st.markdown("---")
        st.header("⚙️ Récurrences")
        
        # On ne prend que les modèles originaux (pas les [AUTO]) marqués Périodique
        df_modeles = df[(df['Periodique'] == 'Oui') & (~df['Description'].str.contains("\[AUTO\]", na=False))]
        df_rec = df_modeles.drop_duplicates(subset=['Description', 'Montant_Total'])
        
        if not df_rec.empty:
            with st.expander(f"📋 Gestion des récurrences", expanded=True):
                # On regarde ce qui a déjà été créé ce mois-ci en version [AUTO]
                deja_faites_ce_mois = df[(df['Mois'] == mois_actuel) & (df['Description'].str.contains("\[AUTO\]", na=False))]['Description'].unique().tolist()
                
                manquantes = []
                for _, row in df_rec.iterrows():
                    nom_cible = f"[AUTO] {row['Description']}"
                    if nom_cible not in deja_faites_ce_mois:
                        manquantes.append(row)
                
                if manquantes:
                    df_man = pd.DataFrame(manquantes)
                    st.warning(f"⚠️ Il manque **{len(manquantes)}** récurrences à générer pour {mois_actuel}")
                    st.table(df_man[['Description', 'Montant_Total', 'Payeur']])
                    
                    if st.button(f"🔄 Générer les {len(manquantes)} manquantes"):
                        bar = st.progress(0)
                        for i, m_row in enumerate(manquantes):
                            p_auto = {
                                "Date": datetime.now().strftime("%Y-%m-%d"),
                                "Description": f"[AUTO] {m_row['Description']}",
                                "Montant_Total": float(m_row['Montant_Total']),
                                "Payeur": m_row['Payeur'],
                                "Part_Payeur": float(m_row['Part_Payeur']),
                                "Part_Autre": float(m_row['Part_Autre']),
                                "Periodique": "Oui"
                            }
                            requests.post(st.secrets["api"]["url"], json=p_auto)
                            bar.progress((i + 1) / len(manquantes))
                        st.success("🎉 Récurrences ajoutées !")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.success(f"✅ Toutes les récurrences ({len(df_rec)}) sont à jour pour {mois_actuel}.")
        else:
            st.info("Cochez 'Dépense périodique' lors d'un ajout pour qu'elle apparaisse ici.")

except Exception as e:
    st.error(f"Erreur technique : {e}")