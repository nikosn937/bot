import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import re # Χρειάζεται για τον έλεγχο εγκυρότητας

# --------------------------------------------------------------------------------
# 0. ΡΥΘΜΙΣΕΙΣ (CONNECTION & FORMATS)
# --------------------------------------------------------------------------------

@st.cache_resource
def get_gspread_client():
    """Δημιουργεί και επιστρέφει τον gspread client."""
    try:
        service_account_info = dict(st.secrets["gcp_service_account"])
        service_account_info['private_key'] = service_account_info['private_key'].replace('\\n', '\n')
        gc = gspread.service_account_from_dict(service_account_info)
        return gc
    except Exception as e:
        st.error(f"Σφάλμα σύνδεσης gspread. Ελέγξτε τα secrets.toml και τα δικαιώματα. Λεπτομέρειες: {e}")
        return None

gc = get_gspread_client()
SHEET_NAME = st.secrets["sheet_name"] 
DATE_FORMAT = '%d/%m/%Y'

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_text(text):
    """Μετατρέπει κείμενο σε πεζά, αφαιρεί τα κενά και τους τόνους."""
    if pd.isna(text): return ''
    normalized = str(text).lower().strip()
    return normalized.translate(TONES_MAP)

def get_tags_from_keyword(keyword):
    """Διαχωρίζει μια φράση-κλειδί σε μεμονωμένα, ομαλοποιημένα tags."""
    if not keyword or pd.isna(keyword): return []
    return [normalize_text(word) for word in str(keyword).split() if word]

@st.cache_data(ttl=600)
def load_data():
    """Φορτώνει, καθαρίζει και ταξινομεί δεδομένα από το ενιαίο Google Sheet."""
    if gc is None:
        return pd.DataFrame(), [], []

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0)
        data = ws.get_all_values()
        
        headers = data[0] if data else []
        df = pd.DataFrame(data[1:], columns=headers) 
        df.columns = df.columns.str.strip()
        
        required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date', 'School', 'Tmima']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet: Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return pd.DataFrame(), [], []
        
        # Καθαρισμός/Επεξεργασία δεδομένων
        df = df.dropna(subset=['Keyword', 'Date', 'School', 'Tmima'], how='any') 
        df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
        df = df.dropna(subset=['Date'])
        
        # Εξαγωγή διαθέσιμων Σχολείων και Τμημάτων δυναμικά
        available_schools = sorted(df['School'].unique().tolist()) if 'School' in df.columns else []
        available_tmimata = sorted(df['Tmima'].unique().tolist()) if 'Tmima' in df.columns else []
        
        return df, available_schools, available_tmimata
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Σφάλμα: Δεν βρέθηκε το Google Sheet με όνομα: '{SHEET_NAME}'. Ελέγξτε το όνομα στα secrets.")
        return pd.DataFrame(), [], []
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης/επεξεργασίας δεδομένων. Λεπτομέρειες: {e}")
        return pd.DataFrame(), [], []

def create_search_maps(df):
    """Δημιουργεί τους χάρτες αναζήτησης μετά το φιλτράρισμα."""
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
    
    # Το zip περιλαμβάνει 6 στοιχεία (Info, URL, Type, Date, School, Tmima)
    keyword_to_data_map = df_sorted.groupby('Keyword').apply(
        lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date'], x['School'], x['Tmima']))
    ).to_dict()

    tag_to_keyword_map = {}
    unique_keywords = df_sorted['Keyword'].unique()
    for keyword in unique_keywords:
        normalized_tags = get_tags_from_keyword(keyword)
        for tag in normalized_tags:
            if tag not in tag_to_keyword_map:
                tag_to_keyword_map[tag] = set()
            tag_to_keyword_map[tag].add(keyword)
            
    return tag_to_keyword_map, keyword_to_data_map


# --------------------------------------------------------------------------------
# 2. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ
# --------------------------------------------------------------------------------

def submit_entry(new_entry_list):
    """Προσθέτει μια νέα σειρά στο Google Sheet."""
    if gc is None:
        st.error("Η σύνδεση με το Google Sheets απέτυχε.")
        return

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0)
        
        ws.append_row(new_entry_list)
        
        st.cache_data.clear() 
        st.success("🎉 Η καταχώρηση έγινε επιτυχώς! Η εφαρμογή ανανεώνεται...")
        st.balloons()
        st.rerun() 
        
    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση. Ελέγξτε τα δικαιώματα. Λεπτομέρειες: {e}")

def data_entry_form(available_schools, available_tmimata):
    """Δημιουργεί τη φόρμα εισαγωγής νέων δεδομένων."""
    
    with st.expander("➕ Νέα Καταχώρηση"):
        
        st.markdown("### Εισαγωγή Νέας Πληροφορίας")
        
        # 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ & ΤΜΗΜΑΤΟΣ
        new_school = st.selectbox(
            "Σχολείο:", 
            options=sorted(list(set(available_schools))),
            key="form_school"
        )
        
        # Χρησιμοποιούμε text_input για το Τμήμα ώστε να μπορεί να βάλει και νέα τμήματα
        new_tmima_input = st.text_input(
            "Τμήμα (Tmima):", 
            placeholder="Π.χ. Α1, Β2, Γ3",
            key="form_tmima"
        )
        
        # 2. Το Radio Button ΕΞΩ από το Form (Για άμεσο rerun/UX fix)
        if 'entry_type' not in st.session_state:
            st.session_state['entry_type'] = 'Text'
            
        st.session_state.entry_type = st.radio(
            "Τύπος Καταχώρησης", 
            ('Text', 'Link'), 
            horizontal=True,
            key="radio_type_key"
        )
        
        new_url = ""
        
        # 3. Άμεση εμφάνιση του πεδίου URL αν επιλεγεί
        if st.session_state.entry_type == 'Link':
            st.session_state['new_url_value'] = st.text_input(
                "Σύνδεσμος (URL)", 
                key="u1_link_input",
                placeholder="Προσθέστε έναν URL, σύνδεσμο Google Drive, κλπ."
            )
            new_url = st.session_state.get('new_url_value', "")
        
        # 4. ΦΟΡΜΑ ΥΠΟΒΟΛΗΣ (με τα υπόλοιπα πεδία)
        with st.form("new_entry_form", clear_on_submit=True):
            
            new_keyword = st.text_input("Φράση-Κλειδί (Keyword, π.χ. 'εργασια μαθηματικα')", key="k1_form")

            if st.session_state.entry_type == 'Text':
                new_info = st.text_area("Περιγραφή (Info)", key="i1_text_area")
            else: 
                new_info = st.text_input("Περιγραφή Συνδέσμου (Info)", key="i2_text_input")

            new_date_obj = st.date_input("Ημερομηνία Καταχώρησης (Date)", value=datetime.today().date(), key="d1_date")
            new_date_str = new_date_obj.strftime(DATE_FORMAT)
            
            submitted = st.form_submit_button("Καταχώρηση 💾")
            
            if submitted:
                final_url = new_url.strip() if st.session_state.entry_type == 'Link' else ""
                
                # Αυτόματη Προσθήκη https://
                if final_url and st.session_state.entry_type == 'Link':
                    if not final_url.lower().startswith(('http://', 'https://', 'ftp://')):
                        final_url = 'https://' + final_url
                
                # --------------------------------------------------------
                # ΝΕΟΣ ΚΩΔΙΚΑΣ: ΕΛΕΓΧΟΣ ΕΓΚΥΡΟΤΗΤΑΣ ΤΜΗΜΑΤΟΣ (Tmima)
                # --------------------------------------------------------
                
                tmima_check = new_tmima_input.strip().upper().replace(" ", "")

                # Pattern: Μόνο Ελληνικά Κεφαλαία (Α-Ω) ή Αριθμοί (0-9)
                tmima_pattern = re.compile(r'^[Α-Ω0-9]+$')

                if not tmima_pattern.match(tmima_check):
                    st.error("⚠️ Σφάλμα Τμήματος: Το πεδίο 'Τμήμα' πρέπει να περιέχει μόνο **Ελληνικούς** κεφαλαίους χαρακτήρες (Α, Β, Γ...) και **αριθμούς** (1, 2, 3...), χωρίς κενά.")
                    st.stop() # Σταματά την εκτέλεση αν αποτύχει ο έλεγχος

                final_tmima = tmima_check 
                # --------------------------------------------------------
                
                # Έλεγχος πληρότητας
                if not new_keyword or not new_info or not new_school or not final_tmima or (st.session_state.entry_type == 'Link' and not final_url):
                    st.error("Παρακαλώ συμπληρώστε όλα τα πεδία (Φράση-Κλειδί, Περιγραφή, Σχολείο, Τμήμα και Σύνδεσμο αν είναι Link).")
                else:
                    new_entry_list = [
                        new_keyword.strip(), 
                        new_info.strip(), 
                        final_url, 
                        st.session_state.entry_type, 
                        new_date_str,
                        new_school,  # Σχολείο
                        final_tmima  # Τυποποιημένο (Ελληνικά/Κεφαλαία/χωρίς κενά)
                    ]
                    submit_entry(new_entry_list)
                    
# --------------------------------------------------------------------------------
# 3. UI / ΚΥΡΙΑ ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης (gspread)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης (gspread Multi-School/Tmima)")
st.markdown("---")

# Φόρτωση όλων των δεδομένων και των διαθέσιμων επιλογών
full_df, available_schools, available_tmimata = load_data()


# 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ
selected_school = st.selectbox(
    "Επιλέξτε Σχολείο:",
    options=["-- Επιλέξτε --"] + available_schools,
    key="school_selector"
)

# 2. ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΣΧΟΛΕΙΟ
if selected_school and selected_school != "-- Επιλέξτε --" and not full_df.empty:
    
    # Φιλτράρισμα βάσει του επιλεγμένου σχολείου
    filtered_df_school = full_df[full_df['School'] == selected_school].copy()
    
    # Εύρεση διαθέσιμων τμημάτων για το επιλεγμένο σχολείο
    current_tmimata = sorted(filtered_df_school['Tmima'].unique().tolist())
    
    # 3. ΕΠΙΛΟΓΗ ΤΜΗΜΑΤΟΣ
    selected_tmima = st.selectbox(
        "Επιλέξτε Τμήμα:",
        options=["Όλα τα Τμήματα"] + current_tmimata,
        key="tmima_selector"
    )

    # 4. ΤΕΛΙΚΟ ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΤΜΗΜΑ
    if selected_tmima != "Όλα τα Τμήματα":
        filtered_df = filtered_df_school[filtered_df_school['Tmima'] == selected_tmima]
    else:
        filtered_df = filtered_df_school

    # Δημιουργία χαρτών αναζήτησης για τα φιλτραρισμένα δεδομένα
    tag_to_keyword_map, keyword_to_data_map = create_search_maps(filtered_df)
    current_available_keys = sorted(filtered_df['Keyword'].unique().tolist())
    
    
    # 5. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ
    data_entry_form(available_schools, available_tmimata) 
    
    st.markdown("---")
    st.header(f"🔍 Αναζήτηση Πληροφοριών για: {selected_school} ({selected_tmima})")
    
    info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(current_available_keys)}**" if current_available_keys else "Δεν βρέθηκαν διαθέσιμες φράσεις-κλειδιά για αυτά τα κριτήρια."
    st.info(info_message)

    user_input = st.text_input(
        'Τι θέλεις να μάθεις;', 
        placeholder='Πληκτρολόγησε π.χ. εκδρομη, εργασια, βιβλια...'
    )

    if user_input and keyword_to_data_map:
        # Λογική αναζήτησης 
        search_tag = normalize_text(user_input)
        matching_keywords = tag_to_keyword_map.get(search_tag, set())
        
        if matching_keywords:
            all_results = []
            
            for keyword in matching_keywords:
                # Το zip έχει 6 στοιχεία: (Info, URL, Type, Date, School, Tmima)
                all_results.extend(keyword_to_data_map.get(keyword, [])) 

            st.success(f"Βρέθηκαν **{len(all_results)}** πληροφορίες.")

            for i, (info, url, item_type, date_obj, school, tmima) in enumerate(all_results, 1):
                date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
                header = f"**Καταχώρηση {i}** ({school} - {tmima} | Ημ/νία: {date_str})"
                
                if item_type.strip().lower() == 'link': 
                    link_description = info.strip()
                    link_url = url.strip()
                    if link_url:
                        st.markdown(f"{header}: 🔗 [{link_description}](<{link_url}>)") 
                    else:
                        st.markdown(f"{header}: ⚠️ **Προσοχή:** Καταχώρηση συνδέσμου χωρίς URL. Περιγραφή: {link_description}")
                
                elif item_type.strip().lower() == 'text':
                    st.markdown(f"{header}: 💬 {info}")
                
                else:
                    st.markdown(f"{header}: Άγνωστος Τύπος Καταχώρησης. {info}")
                    
        else:
            st.warning(f"Δεν βρέθηκε απάντηση για το: '{user_input}'.")

    st.markdown("---")

elif full_df.empty:
    st.warning("Παρακαλώ συμπληρώστε το Google Sheet με τις στήλες 'School' και 'Tmima'.")
else:
    st.info("Παρακαλώ επιλέξτε Σχολείο για να ξεκινήσει η αναζήτηση.")


st.caption("Τα δεδομένα διαβάζονται και γράφονται στο Google Sheet μέσω της βασικής βιβλιοθήκης gspread.")
