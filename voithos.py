import streamlit as st
import pandas as pd

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ (ΑΦΑΙΡΕΣΗ ΤΟΝΩΝ ΚΑΙ TAGGING)
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_text(text):
    """Μετατρέπει κείμενο σε πεζά, αφαιρεί τα κενά και τους τόνους."""
    if pd.isna(text):
        return ''
    normalized = str(text).lower().strip()
    return normalized.translate(TONES_MAP)

def get_tags_from_keyword(keyword):
    """Διαχωρίζει μια φράση-κλειδί σε μεμονωμένα, ομαλοποιημένα tags."""
    if not keyword or pd.isna(keyword):
        return []
    # Χρησιμοποιεί το normalize_text και μετά σπάει σε λέξεις
    return [normalize_text(word) for word in str(keyword).split() if word]


# --------------------------------------------------------------------------------
# 2. ΦΟΡΤΩΣΗ ΚΑΙ ΕΠΕΞΕΡΓΑΣΙΑ ΔΕΔΟΜΕΝΩΝ ΑΠΟ CSV (TAGGING LOGIC)
# --------------------------------------------------------------------------------

DATA_FILE = 'class_data.csv' 
DATE_FORMAT = '%d/%m/%Y' 

try:
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    df.columns = df.columns.str.strip()
    
    required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Σφάλμα: Το CSV πρέπει να περιέχει τις ακριβείς επικεφαλίδες: {', '.join(required_cols)}.")
    
    # Μετατροπή της στήλης Date και ταξινόμηση
    df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
    
    # Δημιουργία χάρτη Tags προς Καταχωρήσεις (Data Source Dictionary)
    # Θα χρησιμοποιήσουμε το Tag (π.χ. 'εκδρομη') για να βρούμε όλες τις σχετικές σειρές (rows)
    
    # 1. Δημιουργούμε μια μοναδική λίστα με όλα τα keywords (ως strings)
    unique_keywords = df_sorted['Keyword'].unique()
    
    # 2. Δημιουργούμε ένα λεξικό όπου το κλειδί είναι το Keyword (π.χ. 'σχολικη εκδρομη')
    # και η τιμή είναι η λίστα με όλα τα δεδομένα της γραμμής
    keyword_to_data_map = df_sorted.groupby('Keyword').apply(
        lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date']))
    ).to_dict()

    # 3. Δημιουργούμε το τελικό λεξικό αναζήτησης: Tag -> [Keyword1, Keyword2, ...]
    tag_to_keyword_map = {}
    for keyword in unique_keywords:
        normalized_tags = get_tags_from_keyword(keyword)
        for tag in normalized_tags:
            if tag not in tag_to_keyword_map:
                tag_to_keyword_map[tag] = set() # Χρησιμοποιούμε set για να αποφύγουμε διπλοκαταχωρήσεις
            tag_to_keyword_map[tag].add(keyword)
            
    available_keys_display = sorted(unique_keywords)
    
except Exception as e:
    st.error(f"Κρίσιμο Σφάλμα Φόρτωσης Δεδομένων: {e}")
    tag_to_keyword_map = {}
    keyword_to_data_map = {}
    available_keys_display = []

# --------------------------------------------------------------------------------
# 3. UI / ΛΟΓΙΚΗ ΑΝΑΖΗΤΗΣΗΣ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης (Μερική Αντιστοίχιση)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης (Αναζήτηση με Λέξεις-Κλειδιά)")
st.markdown("---")

info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(available_keys_display)}**"
st.info(info_message)

user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. εκδρομη, εργασια, βιβλια...'
)

if user_input:
    # Παίρνουμε το tag από την είσοδο του χρήστη (π.χ. 'εκδρομη')
    search_tag = normalize_text(user_input)
    
    # Βρίσκουμε όλα τα Keywords που περιέχουν αυτό το tag (π.χ. {'σχολικη εκδρομη', 'εκδρομη ενημερωσεις'})
    matching_keywords = tag_to_keyword_map.get(search_tag, set())
    
    if matching_keywords:
        # Συλλέγουμε όλες τις απαντήσεις από όλα τα Keywords που ταιριάζουν
        all_results = []
        for keyword in matching_keywords:
             # Προσθέτουμε κάθε tuple (Info, URL, Type, Date)
            all_results.extend(keyword_to_data_map.get(keyword, [])) 

        st.success(f"Βρέθηκαν **{len(all_results)}** πληροφορίες από **{len(matching_keywords)}** φράσεις-κλειδιά για το θέμα: **{user_input}**")

        # Εμφάνιση αποτελεσμάτων (ο κώδικας εμφάνισης παραμένει ίδιος)
        for i, (info, url, item_type, date_obj) in enumerate(all_results, 1):
            
            date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
            header = f"**Καταχώρηση {i}** (Ημ/νία: {date_str})"
            
            if item_type.strip().lower() == 'file':
                link_description = info.strip()
                link_url = url.strip()
                if link_url:
                    st.markdown(f"{header}: 📂 [{link_description}](<{link_url}>)")
                else:
                    st.markdown(f"{header}: 💬 **Προσοχή:** Καταχώρηση αρχείου χωρίς σύνδεσμο. Περιγραφή: {link_description}")
            
            elif item_type.strip().lower() == 'text':
                st.markdown(f"{header}: 💬 {info}")
            
            else:
                st.markdown(f"{header}: Άγνωστος Τύπος Καταχώρησης. {info}")
                
    else:
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκίμασε μια λέξη από τις διαθέσιμες φράσεις-κλειδιά: **{', '.join(available_keys_display)}**."
        )

st.markdown("---")
st.caption("Η εφαρμογή υποστηρίζει πλέον αναζήτηση με μερικές λέξεις-κλειδιά.")
