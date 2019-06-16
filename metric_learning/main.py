import optparse
import os

import cv2
import dlib
import numpy as np
import tensorflow as tf
from imutils.face_utils import FaceAligner
from keras.utils import to_categorical
from skimage.io import imread
from skimage.transform import resize
from sklearn.model_selection import train_test_split
from tensorflow.python.keras import Model
from tensorflow.python.keras import backend as K
from tensorflow.python.keras import optimizers, losses
from tensorflow.python.keras.backend import l2_normalize
from tensorflow.python.keras.callbacks import ModelCheckpoint
from tensorflow.python.keras.layers import Layer, Input, Lambda, Dense

from helpers.helpers import get_image
from metric_learning.generator import Generator
from metric_learning.resnet34 import Resnet34

output_len = 128
input_image_size = 128

K.clear_session()


def create_resnet(image_size=None):
    resnet = Resnet34(image_size or input_image_size, output_len, drop=drop, arch=arch)
    return resnet.create_model()


class ArcFace(Layer):
    def __init__(self, m_param=0.5, s_param=16, max_class=10, **kwargs):
        self.m = m_param
        self.s = s_param
        self.max_class = max_class
        super(ArcFace, self).__init__(**kwargs)

    def build(self, input_shape):
        self.W = self.add_weight(name='W',
                                 shape=(output_len, self.max_class),
                                 initializer='glorot_uniform',
                                 trainable=True)
        super(ArcFace, self).build(input_shape)

    def call(self, input, mask=None):
        x, y = input
        x = K.l2_normalize(x, axis=1)
        w = K.l2_normalize(self.W, axis=0)
        logits = x @ w
        theta = tf.acos(K.clip(logits, -1.0 + K.epsilon(), 1.0 - K.epsilon()))
        target_logits = tf.cos(theta + self.m)
        logits = logits * (1 - y) + target_logits * y
        logits *= self.s
        self.result = tf.nn.softmax(logits)
        return self.result

    def compute_output_shape(self, input_shape):
        return K.int_shape(self.result)


def verify(class_count):
    resnet = create_resnet()
    input_target = Input(shape=(class_count,))
    arcface = ArcFace(m_param=m, s_param=s, name='centerlosslayer', max_class=class_count)(
        [resnet.output, input_target])
    model = Model(inputs=[resnet.input, input_target], outputs=[arcface])
    model.load_weights(options.weights, by_name=True)
    data_features, data_labels = get_files(data)
    global class_name_max
    class_name_max = np.max([np.max(data_labels)]) + 1
    x_train, x_test, y_train, y_test = train_test_split(data_features, data_labels, test_size=0.07, random_state=42)
    training_generator = Generator(x_train, y_train, batch_size, class_count)
    test_generator = Generator(x_test, y_test, batch_size, class_count)
    res = model.evaluate_generator(training_generator)
    print('training')
    print(res[0])
    print(res[1])
    res = model.evaluate_generator(test_generator)
    print('test')
    print(res[0])
    print(res[1])


def train_cnn():
    data_features, data_labels = get_files(data)

    global class_name_max
    class_name_max = np.max([np.max(data_labels)]) + 1

    x_train, x_test, y_train, y_test = train_test_split(data_features, data_labels, test_size=0.07, random_state=42)
    if aug is not None:
        for folder in aug:
            augment_data_features, augment_data_labels = get_files(folder, percent=percent)
            print("###################################################", flush=True)
            print("augmentated data count ", len(augment_data_features), flush=True)
            print("###################################################", flush=True)
            x_train = np.append(x_train, augment_data_features)
            y_train = np.append(y_train, augment_data_labels)
    training_generator = Generator(x_train, y_train, batch_size, class_name_max)

    test_generator = Generator(x_test, y_test, batch_size, class_name_max)

    resnet = create_resnet()
    input_target = Input(shape=(class_name_max,))
    arcface = ArcFace(m_param=m, s_param=s, name='centerlosslayer', max_class=class_name_max)(
        [resnet.output, input_target])
    model = Model(inputs=[resnet.input, input_target], outputs=[arcface])
    optim = optimizers.RMSprop()
    model.compile(optimizer=optim,
                  loss=losses.categorical_crossentropy,
                  metrics=['accuracy'])

    filepath = "weights-improvement-{val_loss:.2f}-epch = {epoch:02d}- acc={val_acc:.2f}.hdf5"
    checkpoint = ModelCheckpoint(filepath, monitor='val_loss', verbose=0, save_best_only=False, mode='max')
    callbacks = [checkpoint]

    if options.weights and os.path.exists(options.weights):
        model.load_weights(options.weights)

    model.fit_generator(
        training_generator,
        epochs=epochs,
        verbose=verbose,
        validation_data=test_generator,
        callbacks=callbacks
    )


def get_files(path, percent=100):
    files_count = 0
    all_files = []
    all_labels = []
    folders = os.listdir(path)
    count = int(len(folders) * (percent / 100))
    folders = folders[:count]
    for _, folder in enumerate(folders):
        current_label = folder[1:]
        current_label = int(current_label)
        if current_label >= class_name_max:
            continue
        cur = path + os.path.sep + folder
        files = os.listdir(cur)
        for idx, val in enumerate(files):
            files[idx] = cur + os.path.sep + files[idx]
        current_folder_files_count = len(files)

        current_folder_labels = [current_label] * current_folder_files_count
        all_labels.extend(current_folder_labels)

        files_count += current_folder_files_count
        all_files.extend(files)
    return np.array(all_files), np.array(all_labels)


def find_distance(image_urls):
    images = []
    paths = []
    for image_url in image_urls:
        image = imread(image_url)

        image = face_align(image)
        image = np.array(resize(image, (128, 128)))
        images.append(image)
        paths.append(image_url)

    test_distance(np.array(images), paths)


def test_distance(images, paths):
    resnet = create_resnet()
    if (options.weights is not None) and os.path.exists(options.weights):
        resnet.load_weights(options.weights, by_name=True)
    else:
        raise Exception('Cant find weights !')
    inferences = resnet.predict(images)
    for idx, inference in enumerate(inferences):
        for idx2, inference2 in enumerate(inferences):
            if idx != idx2:
                dist = np.linalg.norm(inference - inference2)
                print(f'{idx} {idx2} dist = {dist} {paths[idx]} {paths[idx2]}')


def face_align(img):
    predictor = dlib.shape_predictor("../shape_predictor_68_face_landmarks.dat")
    face_aligner = FaceAligner(predictor=predictor, desiredLeftEye=(0.315, 0.315), desiredFaceWidth=128)
    detector = dlib.get_frontal_face_detector()

    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rects = detector(img_gray, 2)
    aligned_face = face_aligner.align(img, img_gray, rects[0])
    return aligned_face


def integration_test():
    from keras.datasets import cifar10

    num_classes = 10
    model = create_resnet(32)
    main = Dense(num_classes, activation='softmax', name='main_out', kernel_initializer='he_normal')(model.output)
    model = Model(inputs=[model.input], outputs=[main])
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    y_train = to_categorical(y_train, num_classes)
    y_test = to_categorical(y_test, num_classes)
    opt = optimizers.Adam(lr=lr)

    model.compile(loss='categorical_crossentropy',
                  optimizer=opt,
                  metrics=['accuracy'])

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    model.fit(x_train, y_train,
              batch_size=batch_size,
              epochs=epochs,
              verbose=verbose,
              validation_data=(x_test, y_test),
              shuffle=True,
              workers=1,
              use_multiprocessing=False
              )


def evaluate():
    resnet = create_resnet()
    if (options.weights is not None) and os.path.exists(options.weights):
        resnet.load_weights(options.weights, by_name=True)
    else:
        print("###########")
        print("NO WEIGHTS")
        print("###########")
    l2_layer = Lambda(lambda x: l2_normalize(x, 1))(resnet.output)
    resnet = Model(inputs=[resnet.input], outputs=[l2_layer])

    data_features, data_labels = get_files(data)
    images = []
    for data_feature in data_features:
        images.append(get_image(data_feature, 128))
    images = np.array(images)
    embedings = resnet.predict(images)
    n = len(images)
    counter = 0
    right_answers = 0
    fp = 0
    fn = 0
    for i in range(0, n):
        for j in range(i, n):
            dist = np.linalg.norm(embedings[i] - embedings[j])
            is_same = dist < thr
            is_right = data_labels[i] == data_labels[j]
            right_answers += (is_right == is_same)
            if is_right and not is_same:
                fp += 1
            elif not is_right and is_same:
                fn += 1

            counter += 1

    print('accuracy ', (right_answers / counter) * 100)
    print('fp', (fp / counter) * 100)
    print('fn', (fn / counter) * 100)


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('--data', type='string')
    parser.add_option('--classes', type='int', default=16)
    parser.add_option('--lr', type='float', default=1e-2)
    parser.add_option('--m', type='float', default=0.5)
    parser.add_option('--s', type='float', default=64)
    parser.add_option('--k_r', type='float', default=0.)
    parser.add_option('--b_r', type='float', default=0.)
    parser.add_option('--batch', type='int', default=90)
    parser.add_option('--epochs', type='int', default=250)
    parser.add_option('--verbose', type='int', default=2)
    parser.add_option('--alpha', type='float', default=0.5)
    parser.add_option('--arch', default='inception')
    parser.add_option('--weights', type='string')
    parser.add_option('--aug', type='string')
    parser.add_option('--percent', type='int', default=100)
    parser.add_option('--mode', type='string', default='train')
    parser.add_option('--urls', type='string')
    parser.add_option('--thr', type='float')
    parser.add_option('--drop', type='float', default=0.)

    (options, args) = parser.parse_args()

    lr = options.lr
    batch_size = options.batch
    epochs = options.epochs
    class_name_max = options.classes
    verbose = options.verbose
    s = options.s
    m = options.m
    arch = options.arch
    drop = options.drop
    data = options.data
    weights = options.weights
    aug = options.aug
    thr = options.thr
    if aug is not None:
        aug = aug.split(',')
    percent = options.percent

    if options.mode == 'train':
        train_cnn()
    elif options.mode == 'verify':
        verify(class_name_max)
    elif options.mode == 'test':
        urls = options.urls.split(',')
        find_distance(urls)
    elif options.mode == 'integr':
        integration_test()
    elif options.mode == 'evaluate':
        evaluate()
