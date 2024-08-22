import fitz
import re
import json
import os
import logging

from DatabaseModels import File, Keyword
from utils.articles_parser import get_abstract_from_file, get_full_text_from_file, get_keywords_from_file

PDFS_PATH = './PDFs'

# Logging, change log level if needed
logging.basicConfig(filename='file_generation.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('my_logger')

def count_files(pdf_directory):
    count = 0
    for filename in os.listdir(pdf_directory):
        if filename.endswith(".pdf"):
            count += 1
    return count

def write_document(concepts):
    # Specify the output file path
    output_file = "./data/pdfs.json"

    # Write the JSON data to the output file
    with open(output_file, 'w') as json_file:
        json.dump(list(concepts.values()), json_file, indent=4)

    print(f"JSON data saved to {output_file}")

def generate_json(pdf_directory, thesaurus):
    regex = r'Uniﬁed Astronomy Thesaurus concepts:\s*((?:[^;)]+\(\d+\);\s*)+[^;)]+\(\d+\))' # regex pattern to find URLs
    concepts_dict = {}  # Dictionary to store IDs and associated files

    file_count = count_files(pdf_directory)
    log.info(f"Generating new file with {file_count} files.")

    count = 0
    # Loop through all files in the directory
    for filename in os.listdir(pdf_directory):
        if (count % 50 == 0):
            log.info(f"Processing file {count} of {file_count}")
        
        if filename.endswith(".pdf"):
            pdf_file = os.path.join(pdf_directory, filename)
            pdf_file_path = os.path.join(PDFS_PATH, filename)

            # Open the PDF file
            pdf_document = fitz.open(pdf_file)

            for page_number in range(len(pdf_document)):
                page = pdf_document[page_number]
                text = page.get_text()

                # Find all URLs using the regex pattern
                terms = re.findall(regex, text)
                if len(terms) > 0:
                    concepts = terms[0]  # Assuming there's only one match per page

                    # Find the IDs in the terms
                    ids = re.findall(r'\((\d+)\)', concepts)

                    for id in ids:
                        id_str = str(id)

                        # Add the ID to the dictionary if it doesn't exist
                        if id_str not in concepts_dict:
                            concepts_dict[id_str] = {
                                'id': id_str,
                                'files': []
                            }

                        # Add the file to the dictionary if it doesn't exist
                        if pdf_file_path not in concepts_dict[id_str]['files']:
                            concepts_dict[id_str]['files'].append(pdf_file_path)

            # Close the PDF document
            pdf_document.close()
            count += 1

    # If the thesaurus term is not present in any file, add it as an empty term
    for thesaurus_term_id in thesaurus.get_terms():
        concept_term = concepts_dict.get(thesaurus_term_id, None)
        if concept_term == None:
            concepts_dict[thesaurus_term_id] = {
                                'id': thesaurus_term_id,
                                'files': []
                            }
    write_document(concepts_dict)

def upload_data(pdf_directory, thesaurus, database):
    for filename in os.listdir(pdf_directory):
        if filename.endswith(".pdf"):
            file_id = filename.rstrip('.pdf')
            pdf_file_path = os.path.join(pdf_directory, filename)
            file_path = os.path.join("PDFs", filename)

            pdf_document = fitz.open(pdf_file_path)

            full_text = get_full_text_from_file(file_path)
            keywords = get_keywords_from_file(file_path)
            abstract = get_abstract_from_file(file_path)
            new_file = File(file_id=file_id, abstract=abstract, full_text=full_text)
            database.add(new_file)

            for keyword in keywords:
                new_keyword = Keyword(file_id=file_id, keyword_id=keyword, order=1)
                database.add(new_keyword)

            pdf_document.close()

    # Iterates over all the keywords_ids of the thesaurus and if does not exist, saves the keywords with empty documents
    all_keywords_id = list(thesaurus.get_terms().keys())
    for keyword_id in all_keywords_id:
        count = database.session.query(Keyword).filter_by(keyword_id=keyword_id).count()

        if count == 0:
            new_keyword = Keyword(keyword_id=keyword_id, file_id=None, order=2)
            database.add(new_keyword)
