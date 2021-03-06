#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Decode the trained CTC outputs (TIMIT corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import tensorflow as tf
import yaml
import argparse

sys.path.append(abspath('../../../'))
from experiments.timit.data.load_dataset_ctc import Dataset
from models.ctc.ctc import CTC
from utils.io.labels.character import Idx2char
from utils.io.labels.phone import Idx2phone
from utils.io.labels.sparsetensor import sparsetensor2list
from utils.evaluation.edit_distance import wer_align

parser = argparse.ArgumentParser()
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--beam_width', type=int, default=20,
                    help='beam_width (int, optional): beam width for beam search.' +
                    ' 1 disables beam search, which mean greedy decoding.')
parser.add_argument('--eval_batch_size', type=str, default=1,
                    help='the size of mini-batch in evaluation')


def do_decode(model, params, epoch, beam_width, eval_batch_size):
    """Decode the CTC outputs.
    Args:
        model: the model to restore
        params (dict): A dictionary of parameters
        epoch (int): the epoch to restore
        beam_width (int): beam width for beam search.
            1 disables beam search, which mean greedy decoding.
        eval_batch_size (int): the size of mini-batch when evaluation
    """
    # Load dataset
    test_data = Dataset(
        data_type='test', label_type=params['label_type'],
        batch_size=eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        shuffle=False, progressbar=True)

    # Define placeholders
    model.create_placeholders()

    # Add to the graph each operation (including model definition)
    _, logits = model.compute_loss(model.inputs_pl_list[0],
                                   model.labels_pl_list[0],
                                   model.inputs_seq_len_pl_list[0],
                                   model.keep_prob_pl_list[0])
    decode_op = model.decoder(
        logits,
        model.inputs_seq_len_pl_list[0],
        beam_width=beam_width)

    # Create a saver for writing training checkpoints
    saver = tf.train.Saver()

    with tf.Session() as sess:
        ckpt = tf.train.get_checkpoint_state(model.save_path)

        # If check point exists
        if ckpt:
            model_path = ckpt.model_checkpoint_path
            if epoch != -1:
                model_path = model_path.split('/')[:-1]
                model_path = '/'.join(model_path) + '/model.ckpt-' + str(epoch)
            saver.restore(sess, model_path)
            print("Model restored: " + model_path)
        else:
            raise ValueError('There are not any checkpoints.')

        # Visualize
        decode(session=sess,
               decode_op=decode_op,
               model=model,
               dataset=test_data,
               label_type=params['label_type'],
               is_test=True,
               save_path=None)
        # save_path=model.save_path)


def decode(session, decode_op, model, dataset, label_type,
           is_test=True, save_path=None):
    """Visualize label outputs of CTC model.
    Args:
        session: session of training model
        decode_op: operation for decoding
        model: the model to evaluate
        dataset: An instance of a `Dataset` class
        label_type (string): phone39 or phone48 or phone61 or character or
            character_capital_divide
        is_test (bool, optional):
        save_path (string, optional): path to save decoding results
    """
    if label_type == 'character':
        map_fn = Idx2char(
            map_file_path='../metrics/mapping_files/character.txt')
    elif label_type == 'character_capital_divide':
        map_fn = Idx2char(
            map_file_path='../metrics/mapping_files/character_capital_divide.txt',
            capital_divide=True)
    else:
        map_fn = Idx2phone(
            map_file_path='../metrics/mapping_files/' + label_type + '.txt')

    if save_path is not None:
        sys.stdout = open(join(model.model_dir, 'decode.txt'), 'w')

    for data, is_new_epoch in dataset:

        # Create feed dictionary for next mini batch
        inputs, labels_true, inputs_seq_len, input_names = data

        feed_dict = {
            model.inputs_pl_list[0]: inputs[0],
            model.inputs_seq_len_pl_list[0]: inputs_seq_len[0],
            model.keep_prob_pl_list[0]: 1.0
        }

        batch_size = inputs[0].shape[0]
        labels_pred_st = session.run(decode_op, feed_dict=feed_dict)
        try:
            labels_pred = sparsetensor2list(
                labels_pred_st, batch_size=batch_size)
        except IndexError:
            # no output
            labels_pred = ['']

        for i_batch in range(batch_size):
            print('----- wav: %s -----' % input_names[0][i_batch])
            if 'char' in label_type:
                if is_test:
                    str_true = labels_true[0][i_batch][0]
                else:
                    str_true = map_fn(labels_true[0][i_batch])
                str_pred = map_fn(labels_pred[i_batch])
            else:
                if is_test:
                    str_true = labels_true[0][i_batch][0]
                else:
                    str_true = map_fn(labels_true[0][i_batch])
                str_pred = map_fn(labels_pred[i_batch])

            print('Ref: %s' % str_true)
            print('Hyp: %s' % str_pred)

        if is_new_epoch:
            break


def main():

    args = parser.parse_args()

    # Load config file
    with open(join(args.model_path, 'config.yml'), "r") as f:
        config = yaml.load(f)
        params = config['param']

    # Except for a blank label
    if params['label_type'] == 'phone61':
        params['num_classes'] = 61
    elif params['label_type'] == 'phone48':
        params['num_classes'] = 48
    elif params['label_type'] == 'phone39':
        params['num_classes'] = 39
    elif params['label_type'] == 'character':
        params['num_classes'] = 28
    elif params['label_type'] == 'character_capital_divide':
        params['num_classes'] = 72

    # Model setting
    model = CTC(encoder_type=params['encoder_type'],
                input_size=params['input_size'],
                splice=params['splice'],
                num_stack=params['num_stack'],
                num_units=params['num_units'],
                num_layers=params['num_layers'],
                num_classes=params['num_classes'],
                lstm_impl=params['lstm_impl'],
                use_peephole=params['use_peephole'],
                parameter_init=params['weight_init'],
                clip_grad_norm=params['clip_grad_norm'],
                clip_activation=params['clip_activation'],
                num_proj=params['num_proj'],
                weight_decay=params['weight_decay'])

    model.save_path = args.model_path
    do_decode(model=model, params=params,
              epoch=args.epoch, beam_width=args.beam_width,
              eval_batch_size=args.eval_batch_size)


if __name__ == '__main__':
    main()
