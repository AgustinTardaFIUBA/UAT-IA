import tensorflow as tf
import sys
import numpy as np
from keras.models import Sequential
from keras.layers import Embedding, LSTM, Dense, Flatten, Dropout, BatchNormalization, Bidirectional, Conv1D, GlobalMaxPooling1D
from sklearn.utils.class_weight import compute_class_weight
from keras.preprocessing.text import Tokenizer
from sklearn.metrics import classification_report
from keras.preprocessing.sequence import pad_sequences
from keras.regularizers import l2
from sklearn.model_selection import train_test_split
from memory_profiler import profile

class TermTrainer:
    def __init__(self, training_files):
        self.training_files = training_files
        # { 'term_id': { 'child_term_id': keyword_index } }. This is for retrieving the index of the term_id children id in the training input for the term_id
        self.keywords_by_term = {}
        # Quantity of models created
        self.models_created = 0


    # Getters
    def get_trained_models(self):
        return self.trained_models

    def get_keywords_by_term(self):
        return self.keywords_by_term
    
    def get_models_created(self):
        return self.models_created
    
    '''
        Creates the input data for the training as two arrays:
        - texts: array of texts for traning
        - keywords_by_text: array of arrays of keywords for each text. 1 if it matches the keyword, 0 if not
        - keywords_indexes: The index of the keyword matches the position of the training input { 'term_id': index }
    '''
    def create_data_input(self, term_id, group_of_term_files, training_input_creator):
        # The index of the keyword matches the position of the training input { 'term_id': index }
        # E.g. { '54': 0, '23': 1, '457': 2, '241': 3 }
        keywords_indexes = {}
        keywords = []
        for i in range(len(group_of_term_files)):
            # Check if the term_files is None. If it is, it means that the term doesn't have files
            if group_of_term_files[i] is not None:
                keywords_indexes[group_of_term_files[i].get_id()] = i
                keywords.append(group_of_term_files[i].get_name())
        self.keywords_by_term[term_id] = keywords_indexes

        files_input = {}
        for term_files in group_of_term_files:
            # Check if the term_files is None. If it is, it means that the term doesn't have files
            if term_files is None:
                continue
            files_paths = term_files.get_files_paths()
            for file_path in files_paths:
                # If the file_path is not in files_input dictionary, creates a new item with the path as the key and an input array filled with 0s
                if file_path not in files_input:
                    files_input[file_path] = [0] * len(group_of_term_files)
                files_input[file_path][keywords_indexes[term_files.get_id()]] = 1

        texts, keywords_by_text = training_input_creator.create_input_arrays(files_input, keywords)
        return texts, keywords_by_text, keywords_indexes

    # Print memory usage in function
    # @profile
    def generate_model_for_group_of_terms(self, texts, keywords_by_text, term_id):
        number_of_categories = len(keywords_by_text[0])
        # Tokenización
        tokenizer = Tokenizer()
        tokenizer.fit_on_texts(texts)
        sequences = tokenizer.texts_to_sequences(texts)

        # Convertir secuencias a vectores de longitud fija (rellenando con ceros si es necesario)
        max_sequence_length = 12
        sequences_padded = pad_sequences(sequences, maxlen=max_sequence_length)

        # Verifica si tienes suficientes datos para dividir
        if len(sequences_padded) < 2 or len(keywords_by_text) < 2:
            print("Advertencia: No hay suficientes datos para realizar una división de entrenamiento y prueba significativa.")
        else:
            # Si tienes suficientes datos, realiza la división
            train_data, test_data, train_labels, test_labels = train_test_split(sequences_padded, keywords_by_text, test_size=0.2, random_state=42)

            # Conversión de datos
            train_labels = np.array(train_labels)
            test_labels = np.array(test_labels)

            # Construir el modelo de la red neuronal
            vocab_size = len(tokenizer.word_index) + 1
            embedding_dim = 128

            # Resets all state generated by Keras for memory consumption
            tf.keras.backend.clear_session()

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

            # Save the trained model
            self.save_trained_model(term_id, model)

            # Remove the model from memory
            del model

    def train_group(self, term_id, group_of_term_files, training_input_creator):
        texts, keywords_by_text, keywords_indexes = self.create_data_input(term_id, group_of_term_files, training_input_creator)
        
        if len(keywords_by_text):
            print("Training model for term: ", term_id)
            self.generate_model_for_group_of_terms(texts, keywords_by_text, term_id)
            self.models_created += 1


    # @profile
    def train_model_by_thesaurus(self, thesaurus, term_id, training_input_creator):
        children = thesaurus.get_by_id(term_id).get_children()
        if not children:
            return
        
        group_of_term_files = []
        for child_id in children:
            term_file = self.training_files.get_term_file_with_children_files(child_id)
            group_of_term_files.append(term_file)
        # TODO: Remove id (and all it's children) from the thesaurus if it doesn't have files
        
        self.train_group(term_id, group_of_term_files, training_input_creator)

        # Avoid recurivity if the term_id is the root (id = 1)
        if term_id == '1':
            return

        for child_id in children:
            self.train_model_by_thesaurus(thesaurus, child_id, training_input_creator)

    def save_trained_model(self, term_id, model):
        if model is not None:
            model_save_path = f"./models/{term_id}.keras"
            model.save(model_save_path)
