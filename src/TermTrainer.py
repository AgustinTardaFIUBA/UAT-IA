import tensorflow as tf
import os
import numpy as np
import keras_tuner as kt
import logging
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from sklearn.model_selection import train_test_split
from Model import MyHyperModel

class TermTrainer:
    def __init__(self, training_files):
        self.training_files = training_files
        # { 'term_id': { 'child_term_id': keyword_index } }. This is for retrieving the index of the term_id children id in the training input for the term_id
        self.keywords_by_term = {}
        # Quantity of models created
        self.models_created = 0
        # Logging, change log level if needed
        logging.basicConfig(filename='trainer.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        self.log = logging.getLogger('my_logger')


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

        # If it doesnt have keywords, the term id is not trainable
        if len(keywords) == 0:
            return [], [], {}

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

        print("Keywords: ", keywords)
        texts, keywords_by_text = training_input_creator.create_input_arrays(files_input, keywords)
        return texts, keywords_by_text, keywords_indexes

    # Print memory usage in function
    # @profile
    def generate_model_for_group_of_terms(self, texts, keywords_by_text, term_id, training_input_creator):
        number_of_categories = len(keywords_by_text[0])
        self.log.info(f"Training with {len(texts)} files")
        # Tokenization
        tokenizer = Tokenizer()
        tokenizer.fit_on_texts(texts)
        sequences = tokenizer.texts_to_sequences(texts)

        # Convert sequences to fixed length vectors (padding with zeros if necessary)
        max_sequence_length = self.get_max_texts_length(texts)
        sequences_padded = pad_sequences(sequences, maxlen=max_sequence_length)

        # Verify if you have enough data to split
        if len(sequences_padded) <= 2 or len(keywords_by_text) <= 2:
            print("Warning: Not enough data to perform a meaningful train-test split.")
            self.log.warning(f"Not enough data to perform a meaningful train-test split for term ID: {term_id}")
        else:
            # If you have enough data, perform the split
            train_data, test_data, train_labels, test_labels = train_test_split(sequences_padded, keywords_by_text, test_size=0.2, random_state=42)

            # Convert the data to numpy arrays
            train_labels = np.array(train_labels)
            test_labels = np.array(test_labels)

            # Build the model
            vocab_size = len(tokenizer.word_index) + 1
            embedding_dim = 128

            # Resets all state generated by Keras for memory consumption
            tf.keras.backend.clear_session()

            model, hypermodel = self.tune_hp(term_id, training_input_creator, number_of_categories, max_sequence_length, train_data, test_data, train_labels, test_labels, vocab_size, embedding_dim)

            # Save the trained model
            self.save_trained_model(term_id, hypermodel, training_input_creator.get_folder_name())

            # Remove the models from memory
            del model
            del hypermodel

    def tune_hp(self, term_id, training_input_creator, number_of_categories, max_sequence_length, train_data, test_data, train_labels, test_labels, vocab_size, embedding_dim):
        self.log.info(f"Started hyperparameters tuning: {term_id}")

        # Search for the best hyperparameters
        my_hyper_model = MyHyperModel(number_of_categories, vocab_size, embedding_dim, max_sequence_length)
        tuner = kt.Hyperband(my_hyper_model, objective="val_accuracy", max_epochs = 10, 
                     factor = 3, directory='tuner', project_name=term_id+'-'+training_input_creator.get_folder_name())
            
        stop_early = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5)

        tuner.search(train_data, train_labels, epochs=50, validation_split=0.2, callbacks=[stop_early])

        # Get the optimal hyperparameters
        best_hps=tuner.get_best_hyperparameters(num_trials=1)[0]

        self.log.info(f"""
            The hyperparameter search is complete. The optimal number of units in the first densely-connected
            layer is {best_hps.get('units')} and the optimal learning rate for the optimizer
            is {best_hps.get('learning_rate')}.
            """)

        # Build the model with the optimal hyperparameters and train it on the data for 50 epochs
        model = tuner.hypermodel.build(best_hps)
        history = model.fit(train_data, train_labels, epochs=50, validation_data=(test_data, test_labels), verbose=0)

        val_acc_per_epoch = history.history['val_accuracy']
        best_epoch = val_acc_per_epoch.index(max(val_acc_per_epoch)) + 1
        self.log.info('Best epoch: %d' % (best_epoch,))

        hypermodel = tuner.hypermodel.build(best_hps)

        # Retrain the model
        hypermodel.fit(train_data, train_labels, epochs=best_epoch, validation_data=(test_data, test_labels), verbose=0)

        eval_result = hypermodel.evaluate(test_data, test_labels)
        self.log.info(f"[test loss, test accuracy]: [{eval_result[0]}, {eval_result[1]}]")

        return model, hypermodel

    def get_max_texts_length(self, texts):
        # Count words in each text
        max_sequence_length = 0
        for text in texts:
            words = text.split()
            if len(words) > max_sequence_length:
                max_sequence_length = len(words)
        return max_sequence_length

    def train_group(self, term_id, group_of_term_files, training_input_creator):
        texts, keywords_by_text, keywords_indexes = self.create_data_input(term_id, group_of_term_files, training_input_creator)
        
        if len(keywords_by_text):
            print("Training model for term: ", term_id)
            self.log.info("------------------------------------------")
            self.log.info(f"Training model for term ID: {term_id}")
        
            self.generate_model_for_group_of_terms(texts, keywords_by_text, term_id, training_input_creator)
            self.models_created += 1


    # @profile
    def train_model_by_thesaurus(self, thesaurus, term_id, training_input_creator):
        # Check if the term is already trained
        term_is_trained = False
        folder_name = training_input_creator.get_folder_name()
        if os.path.exists('./models/' + folder_name):
            if os.path.exists(f"./models/{folder_name}/{term_id}.keras"):
                self.log.info(f"Model for term {term_id} already exists")
                term_is_trained = True

        children = thesaurus.get_by_id(term_id).get_children()
        if not children:
            return
        
        if (not term_is_trained):
            group_of_term_files = []
            for child_id in children:
                term_file = self.training_files.get_term_file_with_children_files(child_id)
                group_of_term_files.append(term_file)
            # TODO: Remove id (and all it's children) from the thesaurus if it doesn't have files
            
            self.train_group(term_id, group_of_term_files, training_input_creator)
            # Avoid recursivity if the term_id is the root (id = 1)
            if term_id == '1':
                return

        for child_id in children:
            self.train_model_by_thesaurus(thesaurus, child_id, training_input_creator)

    def save_trained_model(self, term_id, model, folder_name):
        # Create folder if it doesn't exist
        if not os.path.exists('./models/' + folder_name):
            os.makedirs('./models/' +  folder_name)

        if model is not None:
            model_save_path = f"./models/{folder_name}/{term_id}.keras"
            model.save(model_save_path)

        self.log.info(f"Model saved at: {model_save_path}")
