# -*- coding: utf-8 -*-
__author__ = 'ZFTurbo: https://kaggle.com/zfturbo'


ROOT_FOLDER = 'Y:\\dsb2017\\'
# This is simple script with many limitation due to run on Kaggle CPU server.
# There is used simple CNN with low number of conv layers and filters.
# You can improve this script while run on local GPU just by changing some constants
# It just shows the possible example of dataflow which can be used for solving this problem

conf = dict()
# Change this variable to 0 in case you want to use full dataset
conf['use_sample_only'] = 0
# Save weights
conf['save_weights'] = 1
# How many patients will be in train and validation set during training. Range: (0; 1)
conf['train_valid_fraction'] = 0.5
# Batch size for CNN [Depends on GPU and memory available]
conf['batch_size'] = 200
# Number of epochs for CNN training
conf['nb_epoch'] = 40
# Early stopping. Stop training after epochs without improving on validation
conf['patience'] = 3
# Shape of image for CNN (Larger the better, but you need to increase CNN as well)
conf['image_shape'] = (64, 64)
# Learning rate for CNN. Lower better accuracy, larger runtime.
conf['learning_rate'] = 1e-2
# Number of random samples to use during training per epoch
conf['samples_train_per_epoch'] = 10000
# Number of random samples to use during validation per epoch
conf['samples_valid_per_epoch'] = 1000
# Some variables to control CNN structure
conf['level_1_filters'] = 4
conf['level_2_filters'] = 8
conf['dense_layer_size'] = 32
conf['dropout_value'] = 0.5


import dicom
import os
import cv2
import numpy as np
import pandas as pd
import glob
import random
from keras.models import Sequential
from keras.layers.core import Dense, Dropout, Flatten
from keras.layers.convolutional import Convolution2D, MaxPooling2D, ZeroPadding2D
from keras.optimizers import SGD
from keras.callbacks import EarlyStopping, ModelCheckpoint
import scipy.ndimage
from skimage import data, filters, measure, morphology, feature, segmentation
import time
import json
np.random.seed(2016)
random.seed(2016)

def load_and_normalize_dicom(path, x, y):
    MIN_BOUND = -1000.0
    MAX_BOUND = 400.0
    PIXEL_MEAN = 0.25
    threshold = (-400 - MIN_BOUND) / (MAX_BOUND - MIN_BOUND) - PIXEL_MEAN
    def segment_slice(im):
        binary = im < threshold
        cleared = segmentation.clear_border(binary)
        label_image = measure.label(cleared)

        areas = [r.area for r in measure.regionprops(label_image)]
        areas.sort()
        if len(areas) > 2:
            for region in measure.regionprops(label_image):
                if region.area < areas[-2]:
                    for coordinates in region.coords:
                           label_image[coordinates[0], coordinates[1]] = 0
        binary = label_image > 0
        selem = morphology.disk(2)
        binary =  morphology.binary_erosion(binary, selem)
        selem =  morphology.disk(10)
        binary =  morphology.binary_closing(binary, selem)
        edges = filters.roberts(binary)
        binary = scipy.ndimage.binary_fill_holes(edges)

        return im * binary
    def normalize(im):
        im = (im - MIN_BOUND) / (MAX_BOUND - MIN_BOUND)
        im[im>1] = 1.
        im[im<0] = 0.
        return im
    def zerocenter(im):
        im = im - PIXEL_MEAN
        return im

    dicom1 = dicom.read_file(path)
    dicom_img = dicom1.pixel_array.astype(np.float64)

    dicom_img = normalize(dicom_img)
    dicom_img = zerocenter(dicom_img)
    dicom_img = segment_slice(dicom_img)

    if dicom_img.shape != (x, y):
        dicom_img = cv2.resize(dicom_img, (x, y), interpolation=cv2.INTER_CUBIC)
    return dicom_img

def old_load_and_normalize_dicom(path, x, y):
    dicom1 = dicom.read_file(path)
    dicom_img = dicom1.pixel_array.astype(np.float64)
    mn = dicom_img.min()
    mx = dicom_img.max()
    if (mx - mn) != 0:
        dicom_img = (dicom_img - mn)/(mx - mn)
    else:
        dicom_img[:, :] = 0

    if dicom_img.shape != (x, y):
        dicom_img = cv2.resize(dicom_img, (x, y), interpolation=cv2.INTER_CUBIC)

    return dicom_img

def batch_generator_train(files, train_csv_table, batch_size):
    number_of_batches = np.ceil(len(files)/batch_size)
    counter = 0
    random.shuffle(files)
    while True:
        batch_files = files[batch_size*counter:batch_size*(counter+1)]
        image_list = []
        #Change the call below to load and preprocess the file f with our preprocessing pipeline + lung extraction
        for f in batch_files:
            image = load_and_normalize_dicom(f, conf['image_shape'][0], conf['image_shape'][1])
            image_list.append([image])
        image_list = np.array(image_list)
        #And use our preprocessed segmented array from here
        mask_list = []
        for f in batch_files:
            patient_id = os.path.basename(os.path.dirname(f))
            is_cancer = train_csv_table.loc[train_csv_table['id'] == patient_id]['cancer'].values[0]
            if is_cancer == 0:
                mask = [1, 0]
            else:
                mask = [0, 1]
            mask_list.append(mask)
        counter += 1
        mask_list = np.array(mask_list)
        # print(image_list.shape)
        # print(mask_list.shape)
        yield image_list, mask_list
        if counter == number_of_batches:
            random.shuffle(files)
            counter = 0

def get_custom_CNN():
    model = Sequential()
    model.add(ZeroPadding2D((1, 1), input_shape=(1, conf['image_shape'][0], conf['image_shape'][1]), dim_ordering='th'))
    model.add(Convolution2D(conf['level_1_filters'], 3, 3, activation='relu', dim_ordering='th'))
    model.add(ZeroPadding2D((1, 1), dim_ordering='th'))
    model.add(Convolution2D(conf['level_1_filters'], 3, 3, activation='relu', dim_ordering='th'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2), dim_ordering='th'))

    model.add(ZeroPadding2D((1, 1), dim_ordering='th'))
    model.add(Convolution2D(conf['level_2_filters'], 3, 3, activation='relu', dim_ordering='th'))
    model.add(ZeroPadding2D((1, 1), dim_ordering='th'))
    model.add(Convolution2D(conf['level_2_filters'], 3, 3, activation='relu', dim_ordering='th'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2), dim_ordering='th'))

    model.add(Flatten())
    model.add(Dense(conf['dense_layer_size'], activation='relu'))
    model.add(Dropout(conf['dropout_value']))
    model.add(Dense(conf['dense_layer_size'], activation='relu'))
    model.add(Dropout(conf['dropout_value']))

    model.add(Dense(2, activation='softmax'))

    sgd = SGD(lr=conf['learning_rate'], decay=1e-6, momentum=0.9, nesterov=True)
    model.compile(optimizer=sgd, loss='categorical_crossentropy', metrics=['accuracy'])

    return model

def get_train_single_fold(train_data, fraction):
    ids = train_data['id'].values
    random.shuffle(ids)
    split_point = int(round(fraction*len(ids)))
    train_list = ids[:split_point]
    valid_list = ids[split_point:]
    return train_list, valid_list

def create_single_model():

    train_csv_table = pd.read_csv(ROOT_FOLDER + 'stage1_labels.csv')
    train_patients, valid_patients = get_train_single_fold(train_csv_table, conf['train_valid_fraction'])
    print('Train patients: {}'.format(len(train_patients)))
    print('Valid patients: {}'.format(len(valid_patients)))

    print('Create and compile model...')
    model = get_custom_CNN()
    callbacks = [
        EarlyStopping(monitor='val_loss', patience=conf['patience'], verbose=0),
        # ModelCheckpoint('best.hdf5', monitor='val_loss', save_best_only=True, verbose=0),
    ]

    get_dir = 'stage1'
    if conf['use_sample_only'] == 1:
        get_dir = 'sample_images'

    train_files = []
    for p in train_patients:
        train_files += glob.glob(ROOT_FOLDER + "{}/{}/*.dcm".format(get_dir, p))
    print('Number of train files: {}'.format(len(train_files)))

    valid_files = []
    for p in valid_patients:
        valid_files += glob.glob(ROOT_FOLDER + "{}/{}/*.dcm".format(get_dir, p))
    print('Number of valid files: {}'.format(len(valid_files)))

    print('Fit model...')
    print('Samples train: {}, Samples valid: {}'.format(conf['samples_train_per_epoch'], conf['samples_valid_per_epoch']))
    fit = model.fit_generator(generator=batch_generator_train(train_files, train_csv_table, conf['batch_size']),
                          nb_epoch=conf['nb_epoch'],
                          samples_per_epoch=conf['samples_train_per_epoch'],
                          validation_data=batch_generator_train(valid_files, train_csv_table, conf['batch_size']),
                          nb_val_samples=conf['samples_valid_per_epoch'],
                          verbose=1,
                          callbacks=callbacks)

    return model

def create_submission(model, name='subm'):
    sample_subm = pd.read_csv(ROOT_FOLDER + "stage1_sample_submission.csv")
    ids = sample_subm['id'].values
    for id in ids:
        print('Predict for patient {}'.format(id))
        files = glob.glob(ROOT_FOLDER + "stage1/{}/*.dcm".format(id))
        image_list = []
        #Change the call below to load and preprocess the file f with our preprocessing pipeline + lung extraction
        for f in files:
            image = load_and_normalize_dicom(f, conf['image_shape'][0], conf['image_shape'][1])
            image_list.append([image])
        image_list = np.array(image_list)
        #And use our preprocessed segmented array from here
        batch_size = len(image_list)
        predictions = model.predict(image_list, verbose=1, batch_size=batch_size)
        pred_value = predictions[:, 1].mean()
        sample_subm.loc[sample_subm['id'] == id, 'cancer'] = pred_value
    sample_subm.to_csv(name + ".csv", index=False)


if __name__ == '__main__':
    submlabel = '170301_0852_subm_stage1'
    start = time.time()
    model = create_single_model()
    end = time.time()
    print("Model creation took:" + str(end - start))
    if conf['save_weights'] == 1:
        model.save_weights(submlabel+'_mdl.h5')
        with open(submlabel+'_conf.json', 'w') as fp:
            json.dump(conf, fp)
    start = time.time()
    create_submission(model, submlabel)
    end = time.time()
    print("Submission creation took:" + str(end - start))
