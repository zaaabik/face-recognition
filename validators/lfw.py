import optparse
import os

import matplotlib.pyplot as plt
import numpy as np
from skimage.io import imread
from skimage.transform import resize
from tensorflow.python.keras import Model
from tensorflow.python.keras.backend import l2_normalize
from tensorflow.python.keras.layers import Lambda

from helpers.helpers import get_images, mkdir_p
from metric_learning.resnet34 import Resnet34


def read_pairs_file(path):
    pairs = []
    with open(path, 'r') as f:
        for line in f.readlines()[1:]:
            pair = line.strip().split()
            pairs.append(pair)
    return np.array(pairs)


def create_pairs(base_dir, pairs):
    nrof_skipped_pairs = 0
    path_list = []
    issame_list = []
    for pair in pairs:
        try:
            if len(pair) == 3:
                path0 = add_extension(os.path.join(base_dir, pair[0], pair[0] + '_' + '%04d' % int(pair[1])))
                path1 = add_extension(os.path.join(base_dir, pair[0], pair[0] + '_' + '%04d' % int(pair[2])))
                issame = True
            elif len(pair) == 4:
                path0 = add_extension(os.path.join(base_dir, pair[0], pair[0] + '_' + '%04d' % int(pair[1])))
                path1 = add_extension(os.path.join(base_dir, pair[2], pair[2] + '_' + '%04d' % int(pair[3])))
                issame = False
            if os.path.exists(path0) and os.path.exists(path1):  # Only add the pair if both paths exist
                path_list.append((path0, path1))
                issame_list.append(issame)
            else:
                nrof_skipped_pairs += 1
        except:
            continue
    if nrof_skipped_pairs > 0:
        print('Skipped %d image pairs' % nrof_skipped_pairs)

    return path_list, issame_list


def add_extension(path):
    if os.path.exists(path + '.jpg'):
        return path + '.jpg'
    elif os.path.exists(path + '.png'):
        return path + '.png'
    else:
        raise RuntimeError('No file "%s" with extension png or jpg.' % path)


def main():
    pairs = read_pairs_file(options.pairs)
    pairs, positive = create_pairs(options.dataset, pairs)
    resnet = Resnet34(128, 128, arch=arch)
    resnset = resnet.create_model()
    if not os.path.exists(options.weights):
        print('can not find weights')
    else:
        print('weights are found')
        resnset.load_weights(options.weights, by_name=True)
    l2_layer = Lambda(lambda x: l2_normalize(x, 1))(resnset.output)
    resnset = Model(inputs=[resnset.input], outputs=[l2_layer])
    count = len(pairs)
    pairs = np.array(pairs)
    first_images = pairs[:, 0]
    second_images = pairs[:, 1]
    first_images = get_images(first_images, 128)
    second_images = get_images(second_images, 128)

    first_inferences = resnset.predict(first_images)
    second_inferences = resnset.predict(second_images)

    if flipped:
        first_images_flipped = np.flip(first_images, 2)
        second_images_flipped = np.flip(second_images, 2)
        first_inferences_flipped = resnset.predict(first_images_flipped)
        second_inferences_flipped = resnset.predict(second_images_flipped)
        first_inferences = (first_inferences + first_inferences_flipped) / 2
        second_inferences = (second_inferences + second_inferences_flipped) / 2

    distanses = np.linalg.norm(first_inferences - second_inferences, axis=1).flatten()
    positive = np.array(positive).flatten()

    thresholds = np.array(np.arange(0, 2.5, options.step))
    thr = np.zeros((len(thresholds), len(positive)), dtype=float)
    for idx, val in enumerate(thresholds):
        thr[idx, :] = val

    res = (thr - distanses)
    tmp_res = np.copy(res)
    res = np.where(res > 0, True, False)
    thrs_acc = []
    for i in range(0, res.shape[0]):
        right_answers = (res[i] == positive).sum()
        accuracy = right_answers / count
        thrs_acc.append(accuracy)
    thrs_acc = np.array(thrs_acc)

    best_thr_arg = np.argmax(thrs_acc)

    false_answers = res[best_thr_arg] == positive
    tmp_res = tmp_res[best_thr_arg]
    _counter = 0
    _pos_counter = 0
    for idx, false_answer in enumerate(false_answers):
        if not false_answer:
            save_wrong_answers(first_images[idx], second_images[idx], tmp_res[idx], _counter, positive[idx])
            _counter += 1
        else:
            save_right_answers(first_images[idx], second_images[idx], tmp_res[idx], _pos_counter)
            _pos_counter += 1

    plt.ylabel('accuracy')
    plt.xlabel('thr')
    plt.plot(thresholds, thrs_acc)
    plt.savefig('thrs')
    np.savetxt('test.txt', np.array([
        thresholds,
        thrs_acc
    ]))
    print('best thr ', thresholds[best_thr_arg])
    print('best accuracy', np.max(thrs_acc))


def read_images(paths):
    images = []
    for path in paths:
        image = np.array(resize(imread(path), (128, 128)))
        images.append(image)
    return np.array(images)


def save_wrong_answers(img1, img2, dist, count, is_positive):
    folder_name = '/home/root/lfw_errors'
    mkdir_p(folder_name)
    if is_positive:
        positive = 'positive'
    else:
        positive = 'false'
    f = plt.figure()
    f.add_subplot(1, 2, 1)
    plt.axis('off')
    plt.imshow(((img1 / 2 + 0.5) * 255).astype(int))
    f.add_subplot(1, 2, 2)
    plt.axis('off')
    plt.imshow(((img2 / 2 + 0.5) * 255).astype(int))
    name = f'{count} thr {dist} {positive}.jpg'
    plt.savefig(os.path.join(folder_name, name))
    plt.clf()


def save_right_answers(img1, img2, dist, count):
    folder_name = '/home/root/lfw_ok'
    mkdir_p(folder_name)
    f = plt.figure()
    f.add_subplot(1, 2, 1)
    plt.axis('off')
    plt.imshow(((img1 / 2 + 0.5) * 255).astype(int))
    f.add_subplot(1, 2, 2)
    plt.axis('off')
    plt.imshow(((img2 / 2 + 0.5) * 255).astype(int))
    name = f'{count} thr {dist}.jpg'
    plt.savefig(os.path.join(folder_name, name))
    plt.clf()


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('--dataset')
    parser.add_option('--pairs')
    parser.add_option('--weights')
    parser.add_option('--arch', default='resnet')
    parser.add_option('--flipped', default=False)
    parser.add_option('--step', type='float')
    (options, args) = parser.parse_args()
    flipped = bool(options.flipped)
    arch = options.arch
    main()
