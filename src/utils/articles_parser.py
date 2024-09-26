import fitz
import re
import os
import json
from sklearn.feature_extraction.text import TfidfVectorizer

equation_fonts = ["TimesLTStd-Roman",
                   "STIXTwoMath", 
                   "TimesLTStd-Italic", 
                   "EuclidSymbol", 
                   "AdvTTec1d2308.I+03", 
                   "STIXGeneral-Regular", 
                   "EuclidSymbol-Italic",
                   "AdvTTab7e17fd+22",
                   "EuclidMathTwo"
                   ]

# TODO: Delete this function
def save_string_to_file(string, filename):
  """Saves a string to a file.

  Args:
    string: The string to be saved.
    filename: The name of the file to be created.
  """

  try:
    with open(filename, 'w') as file:
      file.write(string)
    #print(f"String saved to file: {filename}")
  except Exception as e:
    print(f"Error saving string to file: {e}")
    
# Retrieves the text from a page and returns it filtered by different criteria
def get_text_from_page(page):
    blocks = page.get_text("dict")["blocks"]

    page_spans = []
    bold_text = []
    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    page_spans.append(span)
                    text = span["text"]
                    font_name = span["font"]

                    if "Bold" in font_name or ".B" in font_name or "Black" in font_name:
                        bold_text.append(text)
    
    # Guarda los spans en un archivo
    objects_string = json.dumps(page_spans, indent=2)
    #save_string_to_file(objects_string, 'spans.txt')

    # First filter using the full span element (more properties)
    # comentar esto para ver diferencias
    page_spans = clean_spans_from_page(page_spans)

    # The text is reconstructed from the spans without any line breaks
    text = ""
    for span in page_spans:
        text += span["text"] + " "

    return text, bold_text

# Retrieve the full text from an article removing the unnecessary information
def get_full_text_from_file(file_path):
    pdf_document = fitz.open('data/' + file_path)
    full_text = ""
    bold_text = []
    for page_number in range(len(pdf_document)):
        # Numero de pagina - 1 que el pdf
        page = pdf_document[page_number]
        text, bold_text_from_page = get_text_from_page(page)
        # text = page.get_text()

        # ctrl+shift+p: toggle word wrap para evitar scroll

        bold_text = bold_text + bold_text_from_page
        full_text += text + "\n\n"

    pdf_document.close()
    save_string_to_file(full_text, 'text1.txt')

    # Second filter using the only the text
    # comentar esto para ver diferencias
    full_text = clean_plain_text(full_text, bold_text)
    #save_string_to_file(full_text, 'text1.txt')

    return full_text

#Retrieve the title form an article
def get_title_from_file(file_path):
    pdf_document = fitz.open('data/' + file_path)
    page = pdf_document[0]
    blocks = page.get_text("dict")["blocks"]
    spans = []
    bold_text = []
    title = ""
    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    spans.append(span)
                    text = span["text"]
                    font_name = span["font"]

                    if "Bold" in font_name or ".B" in font_name or "Black" in font_name:
                        bold_text.append(text)

    i = 0
    while i < len(spans):
        start_index = None
        end_index = None

        for j in range(i, len(spans)):
            if spans[j]["size"] == 13.947600364685059:
                start_index = j
                break

        # Find the ending of the title 
        if start_index is not None:
            for k in range(start_index, len(spans)):
                if spans[k]["size"] != 13.947600364685059:
                    end_index = k
                    break

        # If both elements were found, remove the elements between them
        if start_index is not None and end_index is not None:
            for index in range(start_index, end_index):
                if not index == end_index:
                    title += spans[index]["text"] + ' '
                else:
                    title += spans[index]["text"] + '\n'
            break

    pdf_document.close()
    return title


# Retrieve the abstract from an article
def get_abstract_from_file(file_path, get_title=False):
    full_text = get_full_text_from_file(file_path)
    regex_pattern = r'Abstract([\s\S]*?)Unified Astronomy Thesaurus concepts:'
    extracted_text = ''
    match = re.search(regex_pattern, full_text)

    if match:
        extracted_text += match.group(1) 

    extracted_text = extracted_text.replace('\n', ' ').strip()

    if get_title:
        extracted_text = get_title_from_file(file_path) + extracted_text
        
    return extracted_text

def get_keywords_from_file(file_path):
    regex = r'Unified Astronomy Thesaurus concepts:\s*((?:[^;)]+\(\d+\);\s*)+[^;)]+\(\d+\))' # regex pattern to find URLs
    text = get_full_text_from_file(file_path)
    terms = re.findall(regex, text)
    ids = []
    if len(terms) > 0:
        concepts = terms[0]  # Assuming there's only one match per page

        # Find the IDs in the terms
        ids = re.findall(r'\((\d+)\)', concepts)
    return ids

# Retrieve the top 50 words from an article based on TF-IDF
# keywords_by_word is a list of words that will be given a higher TF-IDF value, [] if not used
def get_tf_idf_words_from_file(file_path, keywords_by_word):
    full_text = get_full_text_from_file(file_path)

    COMMON_WORDS = ['et', 'al', 'in', 'be', 'at', 'has', 'that', 'can', 'was', 'its', 'both', 'may', 'we', 'not', 'will', 'or', 'it', 'they', 'than', 'these', 'however', 'co', 'from', 'an', 'ah', 'for', "by", "would", "also", "to", 'and', 'the', 'this', "of", "the", "on", "as", "with", "our", "are", "is"]
    words_quantity = 50

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform([full_text])
    terms = vectorizer.get_feature_names_out()
    common_indices = [terms.tolist().index(word) for word in COMMON_WORDS if word in terms]

    # Set the TF-IDF values of the common words to 0
    for i in range(len(X.toarray())):
        for idx in common_indices:
            X[i, idx] = 0.0

    # If keywords_by_word is not empty, increase the TF-IDF value of the words in the list
    X_modified = X.toarray()
    for i in range(len(full_text)):
        for word in keywords_by_word:
            word_lower = word.lower() 
            if word_lower in terms:
                idx = terms.tolist().index(word_lower)
                tfidf_value = X_modified[i, idx]
                new_tfidf_value = tfidf_value * 2
                X_modified[i, idx] = new_tfidf_value

    top_words_per_document = []
    for doc_tfidf in X_modified:
        top_word_indices = doc_tfidf.argsort()[-words_quantity:][::-1]
        top_words = [(terms[i], doc_tfidf[i]) for i in top_word_indices]
        top_words_per_document.append(top_words)

    top_words_strings = []
    for doc_tfidf in X_modified:
        top_word_indices = doc_tfidf.argsort()[-words_quantity:][::-1]
        top_words = [terms[i] for i in top_word_indices]
        top_words_string = ' '.join(top_words)
        top_words_strings.append(top_words_string)

    return top_words_strings

''' Cleans the text by applying a series of text processing functions 
    Params: The plain text of the full article and an array of bold texts
'''
def clean_plain_text(text, bold_text):
    text = replace_special_characters(text)
    text = join_apostrophes(text)
    text = clean_header_from_text(text)
    text = clean_orcidIds_from_text(text)
    text = clean_authors_from_text(text, bold_text)
    text = clean_references_from_text(text)
    return text

def join_apostrophes(text):
    text = re.sub(r'(\S)\s’\ss', r"\1's", text) # Join the word with ’ followed by s, converting to 's
    text = re.sub(r'(\S)\s’', r"\1'", text) # Join the word with ’ when it's not followed by s
    return text

def replace_special_characters(text):
    # Join to the previous and next word if there's a single space around "ﬁ"
    text = re.sub(r'(\S)\sﬁ\s(\S)', r'\1fi\2', text)
    
    # Handle case of two spaces after "ﬁ", keep as separate words and remove extra space
    text = re.sub(r'(\S)\sﬁ(\s{2,})(\S)', r'\1fi \3', text)
    
    # Handle case of two spaces before "ﬁ", keep as separate words and remove extra space
    text = re.sub(r'(\s{2,})ﬁ\s(\S)', r' fi\2', text)

    # Join to the previous and next word if there's a single space around "ﬂ"
    text = re.sub(r'(\S)\sﬂ\s(\S)', r'\1fl\2', text)
    
    # Handle case of two spaces after "ﬂ", keep as separate words and remove extra space
    text = re.sub(r'(\S)\sﬂ(\s{2,})(\S)', r'\1fl \3', text)
    
    # Handle case of two spaces before "ﬂ", keep as separate words and remove extra space
    text = re.sub(r'(\s{2,})ﬂ\s(\S)', r' fl\2', text)
    return text


def clean_header_from_text(text):
    header_pattern = r"\.[^.]*The (Astrophysical Journal Supplement Series|Astronomical Journal|Astrophysical Journal Letters|Astrophysical Journal)[^.]*\."
    matches = re.finditer(header_pattern, text)
    sections_to_remove = []
    
    for match in matches:
        section = match.group(0)
        # If the match does NOT contain "Unified Astronomy Thesaurus concepts", add it to remove list
        if "Unified Astronomy Thesaurus concepts" not in section:
            sections_to_remove.append(re.escape(section))  # Escape the section for use in the regular expression
    
    if sections_to_remove:
        remove_pattern = "|".join(sections_to_remove)
        text = re.sub(remove_pattern, ".", text)
    return text


def clean_authors_from_text(text, bold_texts):
    # Find the index of "Abstract" in bold_texts
    try:
        abstract_index = bold_texts.index('Abstract')
    except ValueError:
        # If "Abstract" is not in bold_texts, return the original text
        return text

    # Find the bold text immediately before "Abstract"
    if abstract_index > 0:
        previous_bold_text = bold_texts[abstract_index - 1]
    else:
        # If "Abstract" is the first item, there is no previous bold text
        return text

    # Find the start index of the previous bold text in the text
    start_index = text.find(previous_bold_text)
    if start_index == -1:
        # If the previous bold text is not found in the text, return the original text
        return text

    # Find the start index of "Abstract"
    abstract_start_index = text.find('Abstract', start_index)
    if abstract_start_index == -1:
        # If "Abstract" is not found after the previous bold text, return the original text
        return text

    # Remove text between the end of the previous bold text and the start of "Abstract"
    end_of_previous_bold = start_index + len(previous_bold_text)

    result_text = text[:end_of_previous_bold] + "\n" + text[abstract_start_index:]

    return result_text


def clean_references_from_text(text):
    #Removes all content from the last occurrence of 'References' to the end.
    last_occurrence = text.rfind("References")
    if last_occurrence != -1:
        return text[:last_occurrence]
    else:
        return text
    

def clean_orcidIds_from_text(text):
    #Removes all content from the last occurrence of 'ORCID iDs' to the end."
    last_occurrence = text.rfind("ORCID iDs")
    if last_occurrence != -1:
        return text[:last_occurrence]
    else:
        return text

''' Cleans the text as spans by applying a series of text processing functions 
    Params: The spans from each page
'''
def clean_spans_from_page(spans):
    spans = clean_tables_from_text(spans)
    spans = clean_urls_from_text(spans)
    spans = clean_equations_from_text(spans)
    spans = clean_years_from_text(spans)
    spans = clean_example_years_from_text(spans)
    spans = clean_parenthesis_with_years_from_text(spans)
    spans = clean_small_references_from_text(spans)
    
    return spans

# Removes the tables from the text (Between "Table _number_" and "Note.")
# TODO: Improve the table detection if Note. is not present (Using position?)
def clean_tables_from_text(spans):
    # We have to iterate through the spans to find the start and end of the tables
    i = 0
    while i < len(spans):
        start_index = None
        end_index = None

        # Find an element that matches "Table _number_"
        for j in range(i, len(spans)):
            if re.match(r'^Table \d+', spans[j]['text']) and ".B" in spans[j]["font"]:
                start_index = j
                break

        # Find an element that matches "Note. (This usually indicates the end of the table)"
        if start_index is not None:        
            for k in range(start_index + 1, len(spans)):
                if (('References.' in spans[k]['text'] or 'Note.' in spans[k]['text'] or 'Notes.' in spans[k]['text']) and ".B" in spans[j]["font"]):
                    #End table with Note or references
                    end_index = k + 1
                    break

                if re.match(r'^Table \d+', spans[k]['text']) and ".B" in spans[k]["font"]:
                    # Another table
                    end_index = k-1
                    break

                if re.match(r'^Figure \d+\.', spans[k]['text']) and ".B" in spans[k]["font"]:
                    # A figure
                    end_index = k
                    break
            
                if ('The Astrophysical' in spans[k]['text'] or 'The Astronomical' in spans[k]['text']):
                    # A figure
                    end_index = k
                    for index in range(1,10):
                        if ('et al' in spans[k+index]['text']):
                            end_index = k + index
                            break
                    break


        # If both elements were found, remove the elements between them
        if start_index is not None and end_index is not None:
            del spans[start_index:end_index]
            i = start_index
        else:
            i += 1
        
    return spans

def clean_urls_from_text(spans):
    # We have to iterate through the spans to find the start and end of the links
    i = 0
    while i < len(spans):
        start_index = None
        end_index = None
        should_skip = False
        text_color = 0

        # Find an element that matches a URL
        for j in range(i, len(spans)):
            if "http" in spans[j]["text"]:
                start_index = j
                text_color = spans[j]["color"]
                break

        # Find the ending of the URL 
        if start_index is not None:
            for k in range(start_index, len(spans)):
                if spans[k]['color'] != text_color:
                    end_index = k
                    break

        if end_index and start_index and (end_index - start_index) >= 8 and text_color == 0 :
            should_skip = True

        if should_skip:
            i = end_index
            start_index = None
            end_index = None
        # If both elements were found, remove the elements between them
        if start_index is not None and end_index is not None:
            del spans[start_index:end_index]
            i = start_index
        else:
            i += 1

    return spans

def clean_equations_from_text(spans):
    # We have to iterate through the spans to find the start and end of the equations
    i = 0
    while i < len(spans):
        start_index = None
        end_index = None

        # Find an element that matches an equation (It has a different font)
        # If it's only one line, it's not an equation
        for j in range(i, len(spans)):
            if spans[j]["font"] in equation_fonts:
                start_index = j
                break

        # Find the ending of the equation 
        if start_index is not None:
            for k in range(start_index, len(spans)):
                if spans[k]["font"] not in equation_fonts:
                    end_index = k
                    if (end_index - start_index) < 2:
                        start_index = None
                        end_index = None
                    break

        # If both elements were found, remove the elements between them
        if start_index is not None and end_index is not None:
            del spans[start_index:end_index]
            i = start_index
        else:
            i += 1

    return spans

def clean_years_from_text(spans):
    # We have to iterate through the spans to find the start and end of the years
    i = 0
    while i < len(spans):
        start_index = None
        end_index = None
        should_skip = False
        # Find an element that matches a "( "
        for j in range(i, len(spans)):
            if (re.match(r'\s?\(', spans[j]['text']) and re.match(r'\d{4}', spans[j+1]['text']) and re.match(r'\s?\)', spans[j+2]['text'])):
                if (spans[j]['color'] == 255):
                    should_skip = True
                start_index = j
                end_index = j + 3
                break

        if should_skip:
            i = end_index
            start_index = None
            end_index = None
            
        # If both elements were found, remove the elements between them
        if start_index is not None and end_index is not None:
            del spans[start_index:end_index]
            i = start_index
        else:
            i += 1

    return spans

def clean_example_years_from_text(spans):
    # We have to iterate through the spans to find the start and end of the years
    i = 0
    while i < len(spans):
        start_index = None
        end_index = None
        # Find an element that matches a "( "
        for j in range(i, len(spans)):
            if(re.match(r'\s?\(', spans[j]['text']) and ("e.g." in spans[j+1]['text'])):
                start_index = j
                break


        if start_index is not None:
            for k in range(start_index, len(spans)):
                if spans[k]["text"] == ")":
                    end_index = k + 1
                    break

        # If both elements were found, remove the elements between them
        if start_index is not None and end_index is not None:
            del spans[start_index:end_index]
            i = start_index
        else:
            i += 1

    return spans

def clean_parenthesis_with_years_from_text(spans):
    i = 0
    while i < len(spans):
        start_index = None
        end_index = None
        should_skip = False
        for j in range(i, len(spans)):
            if "(" in spans[j]["text"]:
                start_index = j
                break

        if start_index is not None:
            for k in range(start_index, len(spans)):
                if ")" in spans[k]['text']:
                    end_index = k + 1
                    if re.search(r'\d{4}', spans[k - 1]['text']):
                        break
                    else:
                        should_skip = True
                        break

        if end_index and start_index and (end_index - start_index) >= 14:
            should_skip = True

        if should_skip:
            i = end_index
            start_index = None
            end_index = None

        if start_index is not None and end_index is not None:
            del spans[start_index:end_index]
            i = start_index
        else:
            i += 1
    return spans

def clean_small_references_from_text(spans):
    i = 0
    while i < len(spans):
        start_index = None
        for j in range(i, len(spans)):
            if spans[j].get('size') == 7.044162273406982 and spans[j].get('color') == 255:
                start_index = j
                break

        if start_index is not None:
            del spans[start_index:start_index + 1]
            i = start_index 
        else:
            i += 1

    return spans
