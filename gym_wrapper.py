import tensorflow as tf
import numpy as np
import time

def train(env, 
          actor, 
          steps, 
          max_ep_step=200, 
          a_mod=lambda x: x,
          warm_up_steps=1000,
          render=True, 
          summary_dir="summaries/"):

    summary_write = tf.summary.FileWriter(summary_dir, actor.sess.graph)
    summary_index = 0
    s             = 0

    while s < steps:
        s1   = env.reset()
        ep_r = 0
        ep_l = 0
        for _ in range(max_ep_step):
            if render:
                env.render()

            s += 1
            ss = s1.reshape(1, -1)

            action = actor.predict(ss)[0]

            # print(action)

            s1, r1, terminal, _ = env.step(a_mod(action))

            actor.add_experience(s1, r1, terminal, action)

            ep_r += r1
            if terminal:
                break

        ep_l += actor.train()


        summary = tf.Summary()
        summary.value.add(tag="Steps", simple_value=float(s))
        summary.value.add(tag="Reward", simple_value=float(ep_r / max_ep_step))
        summary.value.add(tag="Loss", simple_value=float(ep_l / max_ep_step))

        summary_write.add_summary(summary, summary_index)
        summary_write.flush()
        summary_index += 1

    print("Done.")
    env.close()


def play(env, actor, a_mod=lambda x: x, games=20):
    for i in range(games):
        terminal = False
        s0 = env.reset()

        while not terminal:
            env.render()
            s0 = s0.reshape(1, -1)
            action = actor.predict(s0)[0]
            print(action)
            s0, _, terminal, _ = env.step(a_mod(action))

    env.close()
