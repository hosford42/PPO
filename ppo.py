import tensorflow as tf
import scipy.signal
import numpy as np
import random
import copy
from queue import Queue
import sys
import pandas as pd

class Normal(object):
    ################################################
    #         Credit OpenAI Baselines              #
    # Tensorflows Default Normal Distribution      #
    # Was to numerically unstable to use as a PD   #
    ################################################

    def __init__(self, mu, log_sigma):
        self.mu        = mu
        self.log_sigma = log_sigma
        self.sigma     = tf.exp(log_sigma)


    def mode(self):
        return self.mu

    def mean(self):
        return self.mu

    def stddev(self):
        return self.sigma

    def neglogp(self, x):
        return 0.5 * tf.reduce_sum(tf.square((x - self.mu) / self.sigma), axis=-1) \
               + 0.5 * np.log(2.0 * np.pi) * tf.to_float(tf.shape(x)[-1]) \
               + tf.reduce_sum(self.log_sigma, axis=-1)

    def entropy(self):
        return tf.reduce_sum(self.log_sigma + .5 * np.log(2.0 * np.pi * np.e), axis=-1)

    def sample(self):
        return self.mu + self.sigma * tf.random_normal(tf.shape(self.mu))

    def prob(self, x):
        return tf.exp(-self.neglogp(x))


class PPO(object):

    def __init__(self, state_dim, action_dim, gamma=0.90, lam=0.95,
                 traj=100, clip_param=0.2, optim_epoch=5, lr=0.001,
                 value_hidden_layers=1, actor_hidden_layers=1, 
                 value_hidden_neurons=64, actor_hidden_neurons=64, 
                 scope="ppo", add_layer_norm=False, continous=True, 
                 training=True):

        if not continous:
            raise NotImplementedError("TODO")

        self.sess  = tf.get_default_session()
        self.s_dim = state_dim
        self.a_dim = action_dim
        self.gamma = gamma
        self.lam   = lam
        self.traj  = traj
        self.clip_param  = clip_param
        self.optim_epoch = optim_epoch

        self.add_layer_norm  = add_layer_norm
        self.training        = training
        self.continous       = continous

        #####################################
        # Create Object and Value Functions # 
        #####################################


        with tf.variable_scope(scope):
            self.state = tf.placeholder(tf.float32, [None, self.s_dim])

            with tf.variable_scope("pi"):
                self.obf = self.create_actor(self.state,
                                             actor_hidden_layers, 
                                             actor_hidden_neurons,
                                             trainable=True)
            with tf.variable_scope("old_pi"):
                    self.old_obf = self.create_actor(self.state,
                                                     actor_hidden_layers,
                                                     actor_hidden_neurons,
                                                     trainable=False)
            with tf.variable_scope("value"):
                    self.value_out = self.create_value(self.state,
                                                       value_hidden_layers,
                                                       value_hidden_neurons)


            ###################################
            # Define Target Network Update Op #
            ###################################

            pi_vars     = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, 
                                           '{}/pi'.format(scope))

            old_pi_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, 
                                           '{}/old_pi'.format(scope))

            self.equal_op = [tpv.assign(pv)
                                for tpv, pv in zip(old_pi_vars, pi_vars)]

            pi_train_vars    = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,
                                                 '{}/pi'.format(scope))

            value_train_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,
                                                 '{}/value'.format(scope))

            train_vars = pi_train_vars + value_train_vars

            ################
            # Training Ops #
            ################
            self.advantages = tf.placeholder(dtype=tf.float32, shape=[None])
            self.vtarget    = tf.placeholder(dtype=tf.float32, shape=[None])
            self.actions    = tf.placeholder(dtype=tf.float32, shape=[None, self.a_dim])


            mean_action = tf.reduce_mean(self.actions)


            pi_a_likelihood    = self.obf.prob(self.actions)
            oldpi_a_likelihood = self.old_obf.prob(self.actions)
            pi_div_piold       = pi_a_likelihood / oldpi_a_likelihood


            mean, variance = tf.nn.moments(self.advantages, axes=0)
            normalized_adv = (self.advantages - mean) / tf.sqrt(variance)

            #########################################
            #       Surrogate Objectives            #
            # https://arxiv.org/pdf/1707.06347.pdf  #
            #          (6)    and    (7)            #
            #########################################
            surrogate         = pi_div_piold * normalized_adv
            clipped_surrogate = tf.clip_by_value(pi_div_piold, 1.0 - clip_param, 1.0 + clip_param) * normalized_adv

            LCLIP = tf.minimum(surrogate, clipped_surrogate)
            VF = tf.square(self.value_out - self.vtarget)

            c1 = 0.5
            c2 = 0.001
            
            entropy_bonus = self.obf.entropy()

            ############################################
            # https://arxiv.org/pdf/1707.06347.pdf (9) #
            ############################################
            self.Lt = tf.reduce_mean(-LCLIP + c1 * VF + c2 * entropy_bonus)
            gradients = tf.gradients(self.Lt, train_vars)

            
            self.optimizer = ((tf.reduce_mean(self.obf.mean()), tf.reduce_mean(self.obf.stddev())), tf.train.AdamOptimizer(learning_rate=lr).apply_gradients(zip(gradients, train_vars)))



            #####################################
            # If training use stochastic policy #
            #####################################
            if training:
                self.policy = self.obf.sample()
            else:
                self.policy = self.obf.mode()

    def create_value(self, state, layers, neurons):

        
        x = tf.layers.dense(state, 
                            neurons,
                            activation=tf.nn.relu)

        if self.add_layer_norm:
            x = tf.contrib.layers.layer_norm(x, trainable=False)

        for _ in range(layers):
            x = tf.layers.dense(x,
                                neurons,
                                activation=tf.nn.relu)

            if self.add_layer_norm:
                x = tf.contrib.layers.layer_norm(x, trainable=False)


        out = tf.layers.dense(x, 
                              1, 
                              activation=None)

        return out[:, 0]

    def create_actor(self, state, layers, neurons, trainable=True):

        x = tf.layers.dense(state, 
                            neurons,
                            activation=tf.nn.tanh,
                            trainable=trainable)

        if self.add_layer_norm:
            x = tf.contrib.layers.layer_norm(x, trainable=False)

        for _ in range(layers):
            x = tf.layers.dense(x,
                                neurons,
                                activation=tf.nn.tanh,
                                trainable=trainable)

            if self.add_layer_norm:
                x = tf.contrib.layers.layer_norm(x, trainable=False)


        #############################
        # Define objective function #
        #############################
        obf = None
        if self.continous:
            mean = tf.layers.dense(x, self.a_dim, 
                                   activation=tf.tanh,
                                   trainable=trainable)

            log_sigma = tf.layers.dense(x, self.a_dim,
                                    kernel_initializer=tf.zeros_initializer(),
                                    activation=tf.nn.tanh,
                                    trainable=trainable)

            obf = Normal(mean, log_sigma)
        else:
            raise NotImplementedError("TODO")

        return obf

    def predict(self, state):
        return self.sess.run(self.policy, feed_dict={self.state: state})


    def train(self, trajectory):
        states      = np.vstack(trajectory["observations"] + [trajectory["final_state"]])
        values      = self.sess.run((self.value_out), feed_dict={self.state: states})

        trajectory = pd.DataFrame(data={"observations":trajectory["observations"],
                                        "actions": trajectory["actions"],
                                        "rewards": trajectory["rewards"],
                                        "terminals": trajectory["terminals"]})


        rewards     = trajectory["rewards"]
        rewards     = np.append(rewards, [0])
        is_terminal = 1 - trajectory["terminals"]

        trajectory_length = len(is_terminal)

        #################################################
        # GAE https://arxiv.org/pdf/1707.06347.pdf (11) #
        #################################################
        adv = np.zeros(trajectory_length)
        for i in reversed(range(trajectory_length)):
            delta      = rewards[i] + (self.gamma * values[i + 1] - values[i]) * is_terminal[i]
            rewards[i] = adv[i] = delta + self.gamma * self.lam * rewards[i + 1] * is_terminal[i]


        trajectory["adv"]          = adv
        trajectory["value_target"] = values[:-1] + adv


        self.sess.run(self.equal_op)

        total_loss = 0
        training_samples = trajectory.shape[0] // self.traj
        for _ in range(training_samples):
            sample = trajectory.sample(self.traj)
            obs   = np.vstack(sample["observations"])
            acs   = np.vstack(sample["actions"])
            vtarg = np.asarray(sample["value_target"])
            adv   = np.asarray(sample["adv"])



            loss = 0
            for _ in range(self.optim_epoch):
                (LCP, _), epoch_l = self.sess.run((self.optimizer, self.Lt),
                                feed_dict={self.state: obs,
                                           self.actions: acs,
                                           self.vtarget: vtarg,
                                           self.advantages: adv})



                # print(LCP)
                loss += abs(epoch_l)

            total_loss += abs(loss / self.optim_epoch)

        return total_loss / training_samples

