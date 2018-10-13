import tensorflow as tf
from tensorflow.contrib import rnn
from tensorflow.contrib import legacy_seq2seq

import numpy as np


class Model:
    def __init__(self,
                 vocab_size,
                 hidden_layer_size=128,
                 layers_size=2,
                 batch_size=50,
                 sequence_length=50,
                 gradient_clip=5., training=True):

        if not training:
            batch_size = 1
            sequence_length = 1

        cell_fn = rnn.LSTMCell
        # warp multi layered rnn cell into one cell with dropout
        cells = []
        for _ in range(layers_size):
            cells.append(cell_fn(hidden_layer_size))
        self.cell = cell = rnn.MultiRNNCell(cells, state_is_tuple=True)

        # input/target data (int32 since input is char-level)
        self.input_data = tf.placeholder(
            tf.int32, [batch_size, sequence_length])
        self.targets = tf.placeholder(
            tf.int32, [batch_size, sequence_length])
        self.initial_state = cell.zero_state(batch_size, tf.float32)

        # softmax output layer, use softmax to classify
        with tf.variable_scope('rnnlm', reuse=tf.AUTO_REUSE):
            softmax_w = tf.get_variable("softmax_w",
                                        [hidden_layer_size, vocab_size])
            softmax_b = tf.get_variable("softmax_b", [vocab_size])

        # transform input to embedding
        with tf.variable_scope("embedding", reuse=tf.AUTO_REUSE):
            embedding = tf.get_variable("embedding", [vocab_size, hidden_layer_size])
            inputs = tf.nn.embedding_lookup(embedding, self.input_data)

        # # dropout beta testing: double check which one should affect next line
        # if training and args.output_keep_prob:
        #     inputs = tf.nn.dropout(inputs, args.output_keep_prob)

        # unstack the input to fits in rnn model
        inputs = tf.split(inputs, sequence_length, 1)
        inputs = [tf.squeeze(input_, [1]) for input_ in inputs]

        # loop function for rnn_decoder, which take the previous i-th cell's output and generate the (i+1)-th cell's input
        def loop(prev, _):
            prev = tf.matmul(prev, softmax_w) + softmax_b
            prev_symbol = tf.stop_gradient(tf.argmax(prev, 1))
            return tf.nn.embedding_lookup(embedding, prev_symbol)

        # rnn_decoder to generate the ouputs and final state. When we are not training the model, we use the loop function.
        with tf.variable_scope('rnnlm', reuse=tf.AUTO_REUSE):
            outputs, last_state = legacy_seq2seq.rnn_decoder(inputs, self.initial_state, cell, loop_function=loop if not training else None)
            output = tf.reshape(tf.concat(outputs, 1), [-1, hidden_layer_size])

        # output layer
        self.logits = tf.matmul(output, softmax_w) + softmax_b
        self.probs = tf.nn.softmax(self.logits)

        # loss is calculate by the log loss and taking the average.
        loss = legacy_seq2seq.sequence_loss_by_example(
                [self.logits],
                [tf.reshape(self.targets, [-1])],
                [tf.ones([batch_size * sequence_length])])
        with tf.name_scope('cost'):
            self.cost = tf.reduce_sum(loss) / batch_size / sequence_length
        self.final_state = last_state
        self.learning_rate = tf.Variable(0.0, trainable=False)
        tvars = tf.trainable_variables()

        # calculate gradients
        grads, _ = tf.clip_by_global_norm(tf.gradients(self.cost, tvars), gradient_clip)

        with tf.variable_scope('optimizer', reuse=tf.AUTO_REUSE):
            with tf.name_scope('optimizer'):
                optimizer = tf.train.AdamOptimizer(self.learning_rate)
                # apply gradient change to the all the trainable variables
                self.train_op = optimizer.apply_gradients(zip(grads, tvars))

        # instrument tensorboard
        tf.summary.histogram('logits', self.logits)
        tf.summary.histogram('loss', loss)
        tf.summary.scalar('train_loss', self.cost)

    def sample(self, sess, chars, vocab, num=200, prime='The '):
        state = sess.run(self.cell.zero_state(1, tf.float32))
        for char in prime[:-1]:
            x = np.zeros((1, 1))
            x[0, 0] = vocab[char]
            feed = {self.input_data: x, self.initial_state: state}
            [state] = sess.run([self.final_state], feed)

        def weighted_pick(weights):
            t = np.cumsum(weights)
            s = np.sum(weights)
            return(int(np.searchsorted(t, np.random.rand(1)*s)))

        ret = prime
        char = prime[-1]
        for _ in range(num):
            x = np.zeros((1, 1))
            x[0, 0] = vocab[char]
            feed = {self.input_data: x, self.initial_state: state}
            [probs, state] = sess.run([self.probs, self.final_state], feed)
            p = probs[0]

            sample = weighted_pick(p)

            pred = chars[sample]
            ret += pred
            char = pred
        return ret


















