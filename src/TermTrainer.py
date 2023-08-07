import json
import tensorflow as tf
from keras.models import Sequential
from keras.layers import Embedding, LSTM, Dense, Flatten, Dropout, BatchNormalization
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from keras.regularizers import l2
from sklearn.model_selection import train_test_split
import numpy as np
from TrainedModels import TrainedModels

class TermTrainer:
    def __init__(self, training_files):
        self.training_files = training_files
        self.trained_models = TrainedModels()
        self.keywords_by_term = {}

    # Getters
    def get_trained_models(self):
        return self.trained_models

    def get_keywords_by_term(self):
        return self.keywords_by_term

    def create_input_arrays(self, files_input):
        texts = []
        keywords_by_text = []

        for file_path, file_input in files_input.items():
            try:
                file = json.load(open(file_path))
                texts.append(file['text'])
                keywords_by_text.append(file_input)
            except:
                print("Error trying to load file with path: ", file_path)

        return texts, keywords_by_text
    
    '''
        Creates the input data for the training as two arrays:
        - texts: array of texts for traning
        - keywords_by_text: array of arrays of keywords for each text. 1 if it matches the keyword, 0 if not
    '''
    def create_data_input(self, term_id, group_of_term_files):
        # The index of the keyword matches the position of the training input { 'term_id': index }
        # E.g. { '54': 0, '23': 1, '457': 2, '241': 3 }
        keywords_indexes = {}
        for i in range(len(group_of_term_files)):
            keywords_indexes[group_of_term_files[i]] = i
        self.keywords_by_term[term_id] = keywords_indexes

        files_input = {}
        for term_files in group_of_term_files:
            files_paths = term_files.get_files_paths()
            for file_path in files_paths:
                # If the file_path is not in files_input dictionary, creates a new item with the path as the key and an input array filled with 0s
                if file_path not in files_input:
                    files_input[file_path] = [0] * len(group_of_term_files)
                files_input[file_path][keywords_indexes[term_files]] = 1

        texts, keywords_by_text = self.create_input_arrays(files_input)
        return texts, keywords_by_text, keywords_indexes

    def generate_model_for_group_of_terms(self, texts, keywords_by_text, keywords_indexes):
        number_of_categories = len(keywords_by_text[0])
        # Tokenización
        tokenizer = Tokenizer()
        tokenizer.fit_on_texts(texts)
        sequences = tokenizer.texts_to_sequences(texts)

        # Convertir secuencias a vectores de longitud fija (rellenando con ceros si es necesario)
        max_sequence_length = 12
        sequences_padded = pad_sequences(sequences, maxlen=max_sequence_length)

        train_data, test_data, train_labels, test_labels = train_test_split(sequences_padded, keywords_by_text, test_size=0.2,
                                                                            random_state=42)
        # Conversión de datos
        train_labels = np.array(train_labels)
        test_labels = np.array(test_labels)

        # Construir el modelo de la red neuronal
        vocab_size = len(tokenizer.word_index) + 1
        embedding_dim = 128

        model = Sequential()
        model.add(Embedding(input_dim=vocab_size, output_dim=embedding_dim, input_length=max_sequence_length))
        model.add(LSTM(128, return_sequences=True))
        model.add(LSTM(32))
        model.add(Dense(64, activation='relu'))
        model.add(BatchNormalization())
        model.add(Dropout(0.5))
        model.add(Dense(number_of_categories, activation='sigmoid'))  # Salida multi-etiqueta

        optimizer = tf.keras.optimizers.Adam(learning_rate=0.001)
        model.compile(loss='binary_crossentropy', optimizer=optimizer, metrics=['accuracy'])

        # Entrenar el modelo
        epochs = 50
        batch_size = 8
        model.fit(train_data, train_labels, epochs=epochs, batch_size=batch_size,
                  validation_data=(test_data, test_labels), verbose=0)

        # Evaluar el modelo
        loss, accuracy = model.evaluate(test_data, test_labels)
        print("Loss:", loss)
        print("Accuracy:", accuracy)

        return model


    def train_group(self, term_id, group_of_term_files):
        texts, keywords_by_text, keywords_indexes = self.create_data_input(term_id, group_of_term_files)

        model = self.generate_model_for_group_of_terms(texts, keywords_by_text, keywords_indexes)

        self.trained_models.add_model_for_term_children(term_id, model)

    def train_model_by_thesaurus(self, thesaurus, term_id):
        children = thesaurus.get_by_id(term_id).get_children()
        if not children:
            return
        group_of_term_files = []
        for child_id in children:
            term_file = self.training_files.get_term_file_with_children_files(child_id)
            group_of_term_files.append(term_file)

        self.train_group(term_id, group_of_term_files)

        for child_id in children:
            self.train_model_by_thesaurus(thesaurus, child_id)

