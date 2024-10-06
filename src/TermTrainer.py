import gc
import os
import logging
import shutil
import json
import numpy as np
import tensorflow as tf
import keras_tuner as kt
from gensim.models import Word2Vec
from sklearn.preprocessing import LabelEncoder
from memory_profiler import profile
from sklearn.model_selection import train_test_split
from tensorflow.keras import backend as backend

from Model import MyHyperModel
from Database.Keyword import Keyword

tf.get_logger().setLevel(logging.ERROR)
logging.getLogger('gensim').setLevel(logging.ERROR)

class TermTrainer:
    def __init__(self, thesaurus, database):
        self.thesaurus = thesaurus
        # { 'term_id': { 'child_term_id': keyword_index } }. This is for retrieving the index of the term_id children id in the training input for the term_id
        self.keywords_by_term = {}
        # Quantity of models created
        self.models_created = 0
        #Flag for making hyperparameter tuning
        self.hyperparameter_tuning = True
        # db connection
        self.database = database

        # Logging, change log level if needed
        logging.basicConfig(filename='trainer.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        self.log = logging.getLogger('my_logger')

    # Getters
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
    def create_data_input(self, term_id, children, training_input_creator):
        # keywords_indexes: The index of the keyword matches the position of the training input { 'term_id': index }
        # E.g. with term_id 104: {'102': 0, '1129': 1, '1393': 2, '661': 3}
        keywords_indexes = {}
        keywords = []

        for i in range(len(children)):
            child = children[i]
            # Check if the term_files is None. If it is, it means that the term doesn't have files
            if children[i] is not None:
                keywords_indexes[child] = i

                keyword = self.thesaurus.get_by_id(child).get_name()
                keywords.append(keyword)

        self.log.info(f"Keywords indexes: {json.dumps(keywords_indexes)}")
        self.keywords_by_term[term_id] = keywords_indexes

        # If it doesnt have keywords, the term id is not trainable
        if len(keywords) == 0:
            return [], [], {}

        keyword_db = Keyword(self.database)
        # files_input: { 'file_path': [0, 0, 1, 0] }. The array of 0s and 1s represents the keywords for the file
        files_input = {}
        for child in children:
            # Get all children recursively from the child term (To associate all child files to the term child)
            term_children = self.thesaurus.get_branch_children(child)
            term_children_ids = [term.get_id() for term in term_children]
            term_children_ids.insert(0, child)

            files_paths = keyword_db.get_file_ids_by_keyword_ids(term_children_ids)

        # keywords_by_texts is an array where each document represents, on the set of children that is being trained, 
        # a 1 if it belongs to the category of the child of that position, or a 0 if it doesn't belong
        texts, keywords_by_text = training_input_creator.create_input_arrays(files_paths, children)
        return texts, keywords_by_text

    def get_embedding(self, text, word2vec_model):
        words = text.split()
        word_vectors = [word2vec_model.wv[word] for word in words if word in word2vec_model.wv]
        return np.mean(word_vectors, axis=0) if word_vectors else np.zeros(word2vec_model.vector_size)

    # Print memory usage in function
    # @profile
    def generate_model_for_group_of_terms(self, texts, keywords_by_text, term_id, training_input_creator):
        self.log.info(f"Training with {len(texts)} files")

        # Resets all state generated by Keras for memory consumption
        tf.keras.backend.clear_session()
        tf.get_logger().setLevel('ERROR')

        number_of_categories = len(keywords_by_text[0])

        # Convert sequences to fixed length vectors (padding with zeros if necessary)
        tokenized_texts = [text.split() for text in texts]
        word2vec_model = Word2Vec(sentences=tokenized_texts, vector_size=200, window=5, min_count=5, workers=4, sg=1, negative=10)
        embeddings = np.array([self.get_embedding(text, word2vec_model) for text in texts])

        labels = np.array(keywords_by_text)

        # Verify if you have enough data to split
        if len(texts) <= 2 or len(keywords_by_text) <= 2:            
            print("Warning: Not enough data to perform a meaningful train-test split.")
            self.log.warning(f"Not enough data to perform a meaningful train-test split for term ID: {term_id}")
        else:
            # If you have enough data, perform the split
            train_data, test_data, train_labels, test_labels = train_test_split(embeddings, labels, test_size=0.2, random_state=42)

            # Convert the data to numpy arrays
            train_labels = np.array(train_labels)
            test_labels = np.array(test_labels)

            # Build the model
            #vocab_size = len(tokenizer.word_index) + 1
            embedding_dim = 128

            if (self.hyperparameter_tuning):
                model, hypermodel = self.tune_hp(term_id, training_input_creator, number_of_categories, train_data, test_data, train_labels, test_labels)
            else:
                hypermodel = None
                model = self.create_model(number_of_categories, train_data, test_data, train_labels, test_labels)
            
            # Save the trained model
            model_to_save = hypermodel if hypermodel is not None else model
            self.save_trained_model(term_id, model_to_save, training_input_creator.get_folder_name())

            # Clear TensorFlow session again to free memory
            tf.keras.backend.clear_session()

            # Remove the models from memory
            del model
            del hypermodel
            del train_data
            del test_data
            del train_labels
            del test_labels

            gc.collect()

    def create_model(self, number_of_categories, train_data, test_data, train_labels, test_labels):
        my_model = MyHyperModel(number_of_categories)
        model = my_model.build_without_hyperparameters()

        # Train model
        epochs = 50
        batch_size = 8
        model.fit(train_data, train_labels, epochs=epochs, batch_size=batch_size,
                validation_data=(test_data, test_labels), verbose=0)

        # Evaluate model
        loss, accuracy = model.evaluate(test_data, test_labels)
        self.log.info(f"[test loss, test accuracy]: [{loss}, {accuracy}]")

        return model

    @profile
    def tune_hp(self, term_id, training_input_creator, number_of_categories, train_data, test_data, train_labels, test_labels):
        self.log.info(f"Started hyperparameters tuning: {term_id}")

        # Search for the best hyperparameters
        my_hyper_model = MyHyperModel(number_of_categories)
        tuner = self.get_tuner_strategy('bayesian', my_hyper_model, term_id+'-'+training_input_creator.get_folder_name())

        batch_size = 256
            
        tuner.search(train_data, train_labels, epochs=50, validation_split=0.2, batch_size=batch_size)

        # Get the optimal hyperparameters
        best_hps=tuner.get_best_hyperparameters(num_trials=1)[0]

        self.log.info(f"""
            The hyperparameter search is complete. The optimal number of units in the first densely-connected
            layer is {best_hps.get('units')} and the optimal learning rate for the optimizer
            is {best_hps.get('learning_rate')}.
            """)

        # Build the model with the optimal hyperparameters and train it on the data for 50 epochs
        model = tuner.hypermodel.build(best_hps)
        history = model.fit(train_data, train_labels, epochs=50, validation_data=(test_data, test_labels), verbose=0, batch_size=batch_size)

        val_acc_per_epoch = history.history['val_accuracy']
        best_epoch = val_acc_per_epoch.index(max(val_acc_per_epoch)) + 1
        self.log.info('Best epoch: %d' % (best_epoch,))

        hypermodel = tuner.hypermodel.build(best_hps)

        # Retrain the model
        hypermodel.fit(train_data, train_labels, epochs=best_epoch, validation_data=(test_data, test_labels), verbose=0, batch_size=batch_size)

        eval_result = hypermodel.evaluate(test_data, test_labels)
        self.log.info(f"[test loss, test accuracy]: [{eval_result[0]}, {eval_result[1]}]")

        # Delete tuner folder
        subdir = "tuner" + '/' + term_id+'-'+training_input_creator.get_folder_name()
        shutil.rmtree(subdir)
        
        # Delete the tuner to free memory
        del tuner
        gc.collect()

        return model, hypermodel
    
    def get_tuner_strategy(self, type, hyper_model, project_name):
        match type:
            case 'hyperband':
                return kt.Hyperband(hyper_model, objective="val_accuracy", max_epochs = 10, 
                     factor = 3, directory='tuner', project_name=project_name)
            case 'bayesian':
                return kt.BayesianOptimization(
                    hyper_model,
                    objective='val_accuracy',
                    max_trials=20,
                    max_retries_per_trial=2,
                    alpha=0.001,
                    beta=2.5,
                    seed=42,
                    directory='tuner',
                    project_name=project_name
                )

    def get_max_texts_length(self, texts):
        # Count words in each text
        max_sequence_length = 0
        for text in texts:
            words = text.split()
            if len(words) > max_sequence_length:
                max_sequence_length = len(words)
        return max_sequence_length

    def train_group(self, term_id, children, training_input_creator):
        texts, keywords_by_text = self.create_data_input(term_id, children, training_input_creator)

        if len(keywords_by_text):
            self.generate_model_for_group_of_terms(texts, keywords_by_text, term_id, training_input_creator)
            self.models_created += 1

    # Entrypoint method
    def train_model(self, term_id, training_input_creator):
        self.log.info(f"---------------------------------")
        self.log.info(f"Started training for term ID: {term_id}")
        # Check if the term is already trained
        term_is_trained = False
        folder_name = training_input_creator.get_folder_name()
        if os.path.exists('./models/' + folder_name):
            if os.path.exists(f"./models/{folder_name}/{term_id}.keras"):
                self.log.info(f"Model for term {term_id} already exists")
                term_is_trained = True

        children = self.thesaurus.get_by_id(term_id).get_children()
        if not children:
            self.log.info(f"Term {term_id} has no children")
            return
        
        if (not term_is_trained):
            self.train_group(term_id, children, training_input_creator)
            

    def save_trained_model(self, term_id, model, folder_name):
        # Create folder if it doesn't exist
        if not os.path.exists('./models/' + folder_name):
            os.makedirs('./models/' +  folder_name)

        if model is not None:
            model_save_path = f"./models/{folder_name}/{term_id}.keras"
            model.save(model_save_path)

        self.log.info(f"Model saved at: {model_save_path}")
