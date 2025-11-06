import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
import re 
from typing import List

# --------------------------------------------------------------------------------
# 0. ΡΥΘΜΙΣΕΙΣ (CONNECTION & FORMATS)
# --------------------------------------------------------------------------------

@st.cache_resource
def get_gspread_client():
    """Δημιουργεί και επιστρέφει τον gspread client."""
    try:
        service_account_info = dict(st.secrets["gcp_service_account"])
        # Αντικατάσταση των escape sequences για τη σωστή ανάγνωση του private key
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
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ - ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_text(text):
    """Μετατρέπει κείμενο σε πεζά, αφαιρεί τα κενά και τους τόνους (για την αναζήτηση)."""
    if pd.isna(text): return ''
    normalized = str(text).lower().strip()
    return normalized.translate(TONES_MAP)

def get_tags_from_keyword(keyword):
    """Διαχωρίζει μια φράση-κλειδί σε μεμονωμένα, ομαλοποιημένα tags."""
    if not keyword or pd.isna(keyword): return []
    return [normalize_text(word) for word in str(keyword).split() if word]

@st.cache_data(ttl=600)
def load_data():
    """Φορτώνει, καθαρίζει και ταξινομεί δεδομένα από το ενιαίο Google Sheet (Main Data Sheet)."""
    if gc is None:
        return pd.DataFrame(), [], []

    try:
        sh = gc.open(SHEET_NAME)
        # Χρησιμοποιούμε το πρώτο worksheet (index 0) ως το κύριο φύλλο δεδομένων (ClassBot)
        ws = sh.get_worksheet(0)
        data = ws.get_all_values()
        
        headers = data[0] if data else []
        df = pd.DataFrame(data[1:], columns=headers) 
        df.columns = df.columns.str.strip()
        
        # Προσθήκη 'UserId' στη λίστα των απαιτούμενων στηλών, αν και μπορεί να είναι κενή
        required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date', 'School', 'Tmima']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet 'ClassBot': Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)} (και UserId).")
            return pd.DataFrame(), [], []
        
        # Καθαρισμός/Επεξεργασία δεδομένων
        df = df.dropna(subset=['Keyword', 'Date', 'School', 'Tmima'], how='any') 
        df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
        df = df.dropna(subset=['Date'])
        
        # Εξαγωγή διαθέσιμων Σχολείων δυναμικά (Tmima θα φορτωθούν από το ξεχωριστό sheet)
        available_schools = sorted(df['School'].unique().tolist()) if 'School' in df.columns else []
        
        # Προσθήκη μοναδικού ID για διαγραφή/διόρθωση
        df['Internal_ID'] = df.index + 1
        
        return df, available_schools
        
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης/επεξεργασίας δεδομένων 'ClassBot'. Λεπτομέρειες: {e}")
        return pd.DataFrame(), []

@st.cache_data(ttl=600)
def load_users_data():
    """Φορτώνει τα δεδομένα χρηστών (UserId, Username, Password, School) από το sheet 'Χρήστες'."""
    if gc is None:
        return pd.DataFrame()

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("Χρήστες")
        data = ws.get_all_values()

        headers = data[0] if data else []
        df_users = pd.DataFrame(data[1:], columns=headers)
        df_users.columns = df_users.columns.str.strip()

        # Προσθήκη 'UserId'
        required_cols = ['UserId', 'School', 'UserName', 'Password']
        if not all(col in df_users.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet 'Χρήστες': Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return pd.DataFrame()

        df_users = df_users.dropna(subset=required_cols, how='any')

        return df_users

    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης δεδομένων χρηστών. Λεπτομέρειες: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_tmima_data(school_name: str) -> List[str]:
    """Φορτώνει τη λίστα των Τμημάτων για ένα συγκεκριμένο Σχολείο από το sheet 'Σχολεία'."""
    if gc is None:
        return []

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("Σχολεία")
        data = ws.get_all_values()
        
        headers = data[0] if data else []
        df_tmima = pd.DataFrame(data[1:], columns=headers)
        df_tmima.columns = df_tmima.columns.str.strip()
        
        required_cols = ['School', 'Tmima']
        if not all(col in df_tmima.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet 'Σχολεία': Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return []

        # Φιλτράρισμα βάσει Σχολείου και επιστροφή μοναδικών Τμημάτων
        tmimata = df_tmima[df_tmima['School'].astype(str).str.strip() == school_name.strip()]['Tmima'].unique().tolist()
        return sorted([t.strip().upper() for t in tmimata if t.strip()])
        
    except gspread.exceptions.WorksheetNotFound:
        st.warning("⚠️ Προσοχή: Δεν βρέθηκε το worksheet 'Σχολεία'. Η καταχώρηση Τμήματος θα γίνει χειροκίνητα.")
        return [] # Επιστρέφουμε κενή λίστα ώστε να γίνει χειροκίνητη εισαγωγή
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης δεδομένων Τμημάτων από το sheet 'Σχολεία'. Λεπτομέρειες: {e}")
        return []

def create_search_maps(df):
    """Δημιουργεί τους χάρτες αναζήτησης μετά το φιλτράρισμα."""
    # ... (Η λογική παραμένει ίδια)
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
    
    # Το zip περιλαμβάνει 7 στοιχεία: (Info, URL, Type, Date, School, Tmima, Internal_ID)
    keyword_to_data_map = df_sorted.groupby('Keyword').apply(
        lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date'], x['School'], x['Tmima'], x['Internal_ID']))
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
# 2. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ / AUTHENTICATION
# --------------------------------------------------------------------------------

def submit_entry(new_entry_list):
    """Προσθέτει μια νέα σειρά στο Google Sheet (ClassBot)."""
    if gc is None:
        st.error("Η σύνδεση με το Google Sheets απέτυχε.")
        return

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0) # Sheet ClassBot

        # Προσθήκη της νέας σειράς
        ws.append_row(new_entry_list)

        # Καθαρισμός cache και επανεκτέλεση
        st.cache_data.clear() 
        st.success("🎉 Η καταχώρηση έγινε επιτυχώς! Η εφαρμογή ανανεώνεται...")
        st.balloons()
        st.rerun() 
        
    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση. Ελέγξτε τα δικαιώματα. Λεπτομέρειες: {e}")

def data_entry_form(available_schools, logged_in_school, logged_in_userid):
    """Δημιουργεί τη φόρμα εισαγωγής νέων δεδομένων. (Το σχολείο είναι προ-επιλεγμένο)"""
    
    tmimata_list = load_tmima_data(logged_in_school)

    with st.expander(f"➕ Νέα Καταχώρηση για το {logged_in_school}"):
        
        st.markdown("### Εισαγωγή Νέας Πληροφορίας")
        
        # 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ & ΤΜΗΜΑΤΟΣ (Το Σχολείο είναι προεπιλεγμένο/κλειδωμένο)
        st.code(f"Σχολείο Καταχώρησης: {logged_in_school}", language='text')
        new_school = logged_in_school
        
        if tmimata_list:
             # Επιλογή από λίστα (από το sheet 'Σχολεία')
            new_tmima = st.selectbox(
                "Τμήμα (Tmima):", 
                options=["-- Επιλέξτε Τμήμα --"] + tmimata_list,
                key="form_tmima_select"
            )
            new_tmima_input = new_tmima if new_tmima != "-- Επιλέξτε Τμήμα --" else ""
        else:
             # Χειροκίνητη εισαγωγή αν δεν βρεθεί το sheet 'Σχολεία'
            new_tmima_input = st.text_input(
                "Τμήμα (Tmima):", 
                placeholder="Πρέπει να είναι Ελληνικοί Κεφαλαίοι (Π.χ. Α1, Γ2)",
                key="form_tmima_text"
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
                final_tmima = new_tmima_input.strip().upper().replace(" ", "")

                # Αυτόματη Προσθήκη https://
                if final_url and st.session_state.entry_type == 'Link':
                    if not final_url.lower().startswith(('http://', 'https://', 'ftp://')):
                        final_url = 'https://' + final_url
                
                # ΕΛΕΓΧΟΣ ΕΓΚΥΡΟΤΗΤΑΣ ΤΜΗΜΑΤΟΣ (αν δεν έγινε επιλογή)
                tmima_pattern = re.compile(r'^[Α-Ω0-9]+$')

                if not tmima_pattern.match(final_tmima):
                    st.error("⚠️ Σφάλμα Τμήματος: Το πεδίο 'Τμήμα' πρέπει να περιέχει μόνο **Ελληνικούς** κεφαλαίους χαρακτήρες (Α, Β, Γ...) και **αριθμούς** (1, 2, 3...), χωρίς κενά. Διορθώστε την εισαγωγή σας.")
                    st.stop()
                
                # Έλεγχος πληρότητας
                if not new_keyword or not new_info or not new_school or not final_tmima or (st.session_state.entry_type == 'Link' and not final_url):
                    st.error("Παρακαλώ συμπληρώστε όλα τα πεδία (Φράση-Κλειδί, Περιγραφή, Σχολείο, Τμήμα και Σύνδεσμο αν είναι Link).")
                else:
                    # ΠΡΟΣΟΧΗ: Πρέπει να βρούμε τη σωστή σειρά των στηλών του ClassBot sheet
                    # Υποθέτουμε τη σειρά: Keyword, Info, URL, Type, Date, School, Tmima, UserId
                    new_entry_list = [
                        new_keyword.strip(), 
                        new_info.strip(), 
                        final_url, 
                        st.session_state.entry_type, 
                        new_date_str,
                        new_school,  
                        final_tmima,  
                        logged_in_userid # **ΝΕΟ:** Καταχώρηση του UserId
                    ]
                    submit_entry(new_entry_list)

def teacher_login(df_users):
    """Δημιουργεί τη φόρμα σύνδεσης και χειρίζεται την πιστοποίηση."""

    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        st.session_state['logged_in_school'] = None
        st.session_state['logged_in_userid'] = None # **ΝΕΟ**
        st.session_state['login_attempted'] = False

    st.sidebar.markdown("### Σύνδεση Εκπαιδευτικού 🔑")

    if st.session_state.authenticated:
        st.sidebar.success(f"Συνδεδεμένος ως: **{st.session_state.logged_in_school}**")
        if st.sidebar.button("Αποσύνδεση"):
            st.session_state.authenticated = False
            st.session_state.logged_in_school = None
            st.session_state.logged_in_userid = None
            st.cache_data.clear() 
            st.rerun()
        return True

    with st.sidebar.form("login_form"):
        username_input = st.text_input("Όνομα Χρήστη (UserName)", key="login_username")
        password_input = st.text_input("Κωδικός (Password)", type="password", key="login_password")
        submitted = st.form_submit_button("Σύνδεση")

        if submitted:
            st.session_state.login_attempted = True

            user_found = df_users[
                (df_users['UserName'].astype(str).str.strip() == username_input.strip()) &
                (df_users['Password'].astype(str).str.strip() == password_input.strip())
            ]

            if not user_found.empty:
                st.session_state.authenticated = True
                st.session_state.logged_in_school = user_found['School'].iloc[0].strip()
                st.session_state.logged_in_userid = user_found['UserId'].iloc[0].strip() # **ΝΕΟ:** Αποθήκευση UserId
                st.success("Επιτυχής σύνδεση!")
                st.rerun() 
            else:
                st.error("Λάθος όνομα χρήστη ή κωδικός.")
                st.session_state.authenticated = False
                st.session_state.logged_in_school = None
                st.session_state.logged_in_userid = None

    if st.session_state.login_attempted and not st.session_state.authenticated:
        st.sidebar.error("Αποτυχία σύνδεσης.")

    return st.session_state.authenticated

def manage_user_posts(df, logged_in_userid):
    """Εμφανίζει και επιτρέπει τη διαχείριση (διόρθωση/διαγραφή) των καταχωρήσεων του χρήστη."""

    # Φιλτράρισμα καταχωρήσεων βάσει του συνδεδεμένου UserId
    user_posts = df[df.get('UserId', '').astype(str).str.strip() == logged_in_userid]
    
    if user_posts.empty:
        st.info("Δεν βρέθηκαν καταχωρήσεις για τον δικό σας χρήστη (UserId).")
        return

    st.header("✏️ Διαχείριση Καταχωρήσεων")
    st.info(f"Εμφανίζονται οι **{len(user_posts)}** καταχωρήσεις σας. Μπορείτε να τις διαγράψετε (μόνο).")
    
    # Ταξινόμηση ανά ημερομηνία για καλύτερη επισκόπηση
    user_posts = user_posts.sort_values(by='Date', ascending=False)
    
    # Δημιουργία λίστας για την επιλογή διαγραφής
    post_options = []
    for _, row in user_posts.iterrows():
        date_str = row['Date'].strftime(DATE_FORMAT)
        tmima = row['Tmima']
        keyword = row['Keyword']
        info = row['Info'][:50] + "..." if len(row['Info']) > 50 else row['Info']
        post_options.append(f"[{date_str} - {tmima}] {keyword} - {info} (ID: {row['Internal_ID']})")

    with st.form("delete_form"):
        st.subheader("Διαγραφή Καταχώρησης")
        
        selected_post_str = st.selectbox(
            "Επιλέξτε την καταχώρηση προς διαγραφή:",
            options=["-- Επιλέξτε Καταχώρηση --"] + post_options
        )
        
        delete_submitted = st.form_submit_button("Διαγραφή Επιλεγμένης Καταχώρησης 🗑️")

        if delete_submitted and selected_post_str != "-- Επιλέξτε Καταχώρηση --":
            # Εξαγωγή Internal_ID από τη συμβολοσειρά
            try:
                post_id = int(selected_post_str.split('(ID: ')[1].strip(')'))
            except IndexError:
                st.error("Σφάλμα στην ανάγνωση του Internal ID.")
                st.stop()
            
            # Εύρεση της σειράς που αντιστοιχεί στο ID
            row_to_delete = df[df['Internal_ID'] == post_id]
            
            if row_to_delete.empty:
                st.error("Η καταχώρηση δεν βρέθηκε στο DataFrame.")
                st.stop()

            # Η θέση της σειράς στο Google Sheet είναι η 0-based index + 2 (για τις επικεφαλίδες και το 0-index)
            # ΣΗΜΕΙΩΣΗ: Αυτό είναι **πολύ ευαίσθητο** σε αλλαγές στο Sheet. 
            # Η καλύτερη προσέγγιση είναι να χρησιμοποιούμε την index του Pandas DF + 2
            # Επειδή όμως το gspread διαβάζει τα πάντα ως κείμενο, η σωστή θέση είναι η αρχική index.
            # Για λόγους ασφάλειας και επειδή δεν έχουμε τον gspread row index, 
            # χρησιμοποιούμε την πιο ασφαλή μέθοδο της εύρεσης βάσει περιεχομένου, 
            # αλλά για Streamlit, η πιο γρήγορη λύση είναι η index του DF + 2.
            
            # Βρίσκουμε την αρχική 0-based index της γραμμής στο πλήρες DF (χωρίς τα headers)
            # Το gspread row index (1-based) είναι η Pandas index + 2
            gspread_row_index = row_to_delete.index[0] + 2

            try:
                sh = gc.open(SHEET_NAME)
                ws = sh.get_worksheet(0)
                
                # Διαγραφή της σειράς
                ws.delete_rows(gspread_row_index)
                
                st.cache_data.clear() 
                st.success(f"🗑️ Η καταχώρηση (ID: {post_id}) διαγράφηκε επιτυχώς.")
                st.rerun()

            except Exception as e:
                st.error(f"Σφάλμα κατά τη διαγραφή από το Google Sheet. Λεπτομέρειες: {e}")
                
    st.markdown("---")


# --------------------------------------------------------------------------------
# 3. UI / ΚΥΡΙΑ ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης", layout="centered")

# ΟΡΙΣΤΕ ΤΗΝ RAW URL ΓΙΑ ΤΟ ΛΟΓΟΤΥΠΟ
RAW_IMAGE_URL = "https://raw.githubusercontent.com/nikosn937/bot/main/ClassBot.gif"

# Δημιουργία δύο στηλών: η πρώτη (1/5) για το λογότυπο, η δεύτερη (4/5) για τον τίτλο
col1, col2 = st.columns([1, 4])

with col1:
    st.image(RAW_IMAGE_URL, width=200)

with col2:
    st.markdown("## Ψηφιακός Βοηθός Τάξης")
    st.caption("Steam Project")

st.markdown("---") 

# Φόρτωση όλων των δεδομένων και των διαθέσιμων επιλογών
full_df, available_schools = load_data()
df_users = load_users_data() # Φόρτωση δεδομένων χρηστών

# ΕΝΣΩΜΑΤΩΣΗ ΦΟΡΜΑΣ ΣΥΝΔΕΣΗΣ ΣΤΗΝ ΠΛΕΥΡΙΚΗ ΣΤΗΛΗ
is_authenticated = teacher_login(df_users)
st.markdown("---")


# 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ
selected_school = st.selectbox(
    "Επιλέξτε Σχολείο:",
    options=["-- Επιλέξτε --"] + available_schools,
    key="school_selector"
)

# 2. ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΣΧΟΛΕΙΟ
if selected_school and selected_school != "-- Επιλέξτε --" and not full_df.empty:

    logged_in_school = st.session_state.get('logged_in_school')
    logged_in_userid = st.session_state.get('logged_in_userid') # **ΝΕΟ**

    # --------------------------------------------------------------------------
    # ΕΛΕΓΧΟΣ ΠΡΟΣΒΑΣΗΣ ΦΟΡΜΑΣ ΚΑΤΑΧΩΡΗΣΗΣ / ΔΙΑΧΕΙΡΙΣΗΣ
    # --------------------------------------------------------------------------
    if is_authenticated and logged_in_school == selected_school:
        # 1. Εμφάνιση Φόρμας Καταχώρησης
        data_entry_form(available_schools, logged_in_school, logged_in_userid)
        st.markdown("---") 
        
        # 2. Εμφάνιση Φόρμας Διαχείρισης (Διόρθωσης/Διαγραφής)
        manage_user_posts(full_df, logged_in_userid)
        st.markdown("---")
        
    elif is_authenticated:
        st.warning(f"Είστε συνδεδεμένος ως εκπαιδευτικός του **{logged_in_school}**. Για καταχώρηση, πρέπει να επιλέξετε το σχολείο σας ('{logged_in_school}').")
        st.markdown("---")
    else:
        st.info("Για να δείτε/χρησιμοποιήσετε τη φόρμα καταχώρησης, παρακαλώ συνδεθείτε ως εκπαιδευτικός από την πλαϊνή στήλη (sidebar).")
        st.markdown("---")


    # Φιλτράρισμα βάσει του επιλεγμένου σχολείου
    filtered_df_school = full_df[full_df['School'] == selected_school].copy()

    # Εύρεση διαθέσιμων τμημάτων για το επιλεγμένο σχολείο (για την αναζήτηση - από τα δεδομένα)
    current_tmimata = sorted(filtered_df_school['Tmima'].unique().tolist())

    # --------------------------------------------------------------------------
    # ΛΟΓΙΚΗ: ΥΠΟΧΡΕΩΤΙΚΗ ΕΠΙΛΟΓΗ ΤΜΗΜΑΤΟΣ ΓΙΑ ΑΝΑΖΗΤΗΣΗ
    # --------------------------------------------------------------------------

    if not current_tmimata:
        st.warning(f"Το Σχολείο '{selected_school}' δεν έχει καταχωρήσεις τμημάτων στο σύστημα για αναζήτηση.")

    else:
        # 3β. Υποχρεωτική επιλογή Τμήματος για Αναζήτηση
        selected_tmima = st.selectbox(
            "Επιλέξτε Τμήμα (Υποχρεωτικό για Αναζήτηση):",
            options=["-- Επιλέξτε Τμήμα --"] + current_tmimata,
            key="tmima_selector"
        )

        # ΕΚΚΙΝΗΣΗ ΛΟΓΙΚΗΣ ΕΜΦΑΝΙΣΗΣ ΜΟΝΟ ΑΝ ΕΧΕΙ ΕΠΙΛΕΓΕΙ ΕΓΚΥΡΟ ΤΜΗΜΑ
        if selected_tmima and selected_tmima != "-- Επιλέξτε Τμήμα --":

            # 4. ΤΕΛΙΚΟ ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΤΜΗΜΑ
            filtered_df = filtered_df_school[filtered_df_school['Tmima'] == selected_tmima]

            # ----------------------------------------------------------------------
            # ΕΜΦΑΝΙΣΗ ΤΕΛΕΥΤΑΙΩΝ 2 ΗΜΕΡΩΝ
            # ----------------------------------------------------------------------

            two_days_ago = datetime.now() - timedelta(days=2)
            recent_posts = filtered_df[filtered_df['Date'].dt.date >= two_days_ago.date()]

            if not recent_posts.empty:
                st.header(f"📢 Πρόσφατες Ανακοινώσεις ({selected_tmima})")
                st.info("Εμφανίζονται οι καταχωρήσεις των τελευταίων 2 ημερών.")

                recent_posts = recent_posts.sort_values(by='Date', ascending=False)

                for i, row in recent_posts.iterrows():
                    date_str = row['Date'].strftime(DATE_FORMAT)
                    header = f"**Καταχώρηση (Από: {date_str})**"

                    if row['Type'].strip().lower() == 'link':
                        link_description = row['Info'].strip()
                        link_url = row['URL'].strip()
                        st.markdown(f"{header}: 🔗 [{link_description}](<{link_url}>) (Keyword: *{row['Keyword']}*)")

                    elif row['Type'].strip().lower() == 'text':
                        st.markdown(f"{header}: 💬 {row['Info']} (Keyword: *{row['Keyword']}*)")

                st.markdown("---") 
            else:
                st.info(f"Δεν υπάρχουν πρόσφατες ανακοινώσεις (τελευταίες 2 ημέρες) για το τμήμα {selected_tmima}.")
                st.markdown("---")


            st.header("🔍 Αναζήτηση Παλαιότερων Πληροφοριών")
            st.info("Για να βρείτε κάτι συγκεκριμένο ή παλαιότερο, πληκτρολογήστε τη φράση-κλειδί (keyword) παρακάτω.")

            # ----------------------------------------------------------------------
            # ΛΟΓΙΚΗ ΑΝΑΖΗΤΗΣΗΣ
            # ----------------------------------------------------------------------

            tag_to_keyword_map, keyword_to_data_map = create_search_maps(filtered_df)
            current_available_keys = sorted(filtered_df['Keyword'].unique().tolist())

            info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(current_available_keys)}**" if current_available_keys else "Δεν βρέθηκαν διαθέσιμες φράσεις-κλειδιά για αυτά τα κριτήρια."
            st.info(info_message)

            user_input = st.text_input(
                'Τι θέλεις να μάθεις;',
                placeholder='Πληκτρολόγησε π.χ. εκδρομη, εργασια, βιβλια...'
            )

            if user_input and keyword_to_data_map:
                search_tag = normalize_text(user_input)
                matching_keywords = tag_to_keyword_map.get(search_tag, set())

                if matching_keywords:
                    all_results = []

                    for keyword in matching_keywords:
                        # Το zip έχει 7 στοιχεία: (Info, URL, Type, Date, School, Tmima, Internal_ID)
                        all_results.extend(keyword_to_data_map.get(keyword, []))

                    st.success(f"Βρέθηκαν **{len(all_results)}** πληροφορίες για το '{user_input}'.")

                    results_list = []
                    for info, url, item_type, date_obj, school, tmima, _ in all_results:
                        results_list.append((date_obj, info, url, item_type, school, tmima))

                    results_list.sort(key=lambda x: x[0], reverse=True)

                    for i, (date_obj, info, url, item_type, school, tmima) in enumerate(results_list, 1):
                        date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
                        header = f"**Αποτέλεσμα {i}** (Ημ/νία: {date_str})"

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
    st.warning("Παρακαλώ συμπληρώστε το Google Sheet με τις στήλες 'School' και 'Tmima' στο φύλλο 'ClassBot', καθώς και τα φύλλα 'Χρήστες' και 'Σχολεία'.")
else:
    st.info("Παρακαλώ επιλέξτε Σχολείο για να ξεκινήσει η αναζήτηση.")


st.caption("Ψηφιακός Βοηθός Τάξης - Steam Project.")
