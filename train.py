#!/usr/bin/env python
# -*- coding: utf-8 -*-
import tensorflow as tf
import model
import bcolz
import os
import numpy as np
import threading
import random

NUM_CLASSES = 33
DATASET_ROOT = 'camvid'


class BatchIndices(object):
    def __init__(self, n, bs, shuffle=False):
        self.n, self.bs, self.shuffle = n, bs, shuffle
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.idxs = (np.random.permutation(self.n)
                     if self.shuffle else np.arange(0, self.n))
        self.curr = 0

    def __next__(self):
        with self.lock:
            if self.curr >= self.n:
                self.reset()
            ni = min(self.bs, self.n - self.curr)
            res = self.idxs[self.curr:self.curr + ni]
            self.curr += ni
            return res


class segm_generator(object):
    def __init__(self, x, y, bs=64, out_sz=(64, 64), train=True):
        self.x, self.y, self.bs, self.train = x, y, bs, train
        self.n, self.rowi, self.coli = x.shape
        self.idx_gen = BatchIndices(self.n, self.bs, train)
        self.rowo, self.colo = out_sz
        self.ych = self.y.shape[-1] if len(y.shape) == 4 else 1

    def get_slice(self, i, o):
        start = random.randint(0, i - o) if self.train else (i - o)
        return slice(start, start + o)

    def get_item(self, idx):
        slice_r = self.get_slice(self.rowi, self.rowo)
        slice_c = self.get_slice(self.coli, self.colo)
        x = self.x[idx, slice_r, slice_c]
        y = self.y[idx, slice_r, slice_c]
        if self.train and (random.random() > 0.5):
            # horizontal flipping
            y = y[:, ::-1]
            x = x[:, ::-1]
        return x, y

    def __next__(self):
        idxs = next(self.idx_gen)
        items = (self.get_item(idx) for idx in idxs)
        xs, ys = zip(*items)
        return np.stack(xs), np.stack(ys).reshape(len(ys), -1, self.ych)


def load_array(fname):
    return bcolz.open(fname)


def standardize(imgs):
    avg = np.mean(imgs)
    sd = np.std(imgs)
    imgs -= avg
    imgs /= sd
    return imgs


def main():
    # load dataset
    imgs = load_array(os.path.join(DATASET_ROOT, 'results/imgs.bc'))
    labels_int = load_array(
        os.path.join(DATASET_ROOT, 'results/labels_int.bc'))

    # standardize values of image data
    imgs = standardize(imgs)

    # Split dataset
    n_data = len(imgs)
    n_trn_imgs = int(0.7 * n_data)
    trn_imgs = imgs[:n_trn_imgs]
    trn_labels = labels_int[:n_trn_imgs]
    test_imgs = imgs[n_trn_imgs:]
    test_labels = labels_int[n_trn_imgs:]
    print('Training data:', trn_imgs.shape, trn_labels.shape)
    print('Test data:', test_imgs.shape, test_labels.shape)

    # input image: [batch_size, image height, image width, image channel]
    x = tf.placeholder(tf.float32, shape=(None, 224, 224, 3))
    # output labels: [batch_size, image height * image width]
    y = tf.placeholder(tf.int64, shape=(None, 224 * 224, 1))

    # logits shape: [None, NUM_CLASSES]
    logits = model.create_tiramisu(
        NUM_CLASSES,
        x,
        nb_layers_per_block=[4, 5, 7, 10, 12, 15],
        keep_prob=0.2,
        scale=1e-4)
    print(logits)

    cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(
        labels=tf.reshape(y, [-1]), logits=logits, name='x_entropy')
    loss = tf.reduce_mean(cross_entropy, name='x_entropy_mean')
    train_step = tf.train.RMSPropOptimizer(1e-3).minimize(loss)


if __name__ == '__main__':
    main()
