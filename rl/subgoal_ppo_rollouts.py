import os
from collections import defaultdict, Counter

import numpy as np
import torch
import cv2
import gym
from collections import OrderedDict
from env.inverse_kinematics import qpos_from_site_pose_sampling, qpos_from_site_pose
from util.logger import logger
from util.env import joint_convert
from util.gym import action_size
from util.info import Info


class Rollout(object):
    def __init__(self):
        self._history = defaultdict(list)

    def add(self, data):
        for key, value in data.items():
            self._history[key].append(value)

    def __len__(self):
        return len(self._history['ob'])

    def get(self):
        batch = {}
        for k, v in self._history.items():
            batch[k] = v
        self._history = defaultdict(list)
        return batch

class MetaRollout(object):
    def __init__(self):
        self._history = defaultdict(list)

    def add(self, data):
        for key, value in data.items():
            self._history[key].append(value)

    def __len__(self):
        return len(self._history['meta_ob'])

    def get(self):
        batch = {}
        batch['ob'] = self._history['meta_ob']
        batch['ac'] = self._history['meta_ac']
        batch['ac_before_activation'] = self._history['meta_ac_before_activation']
        batch['log_prob'] = self._history['meta_log_prob']
        batch['done'] = self._history['meta_done']
        batch['rew'] = self._history['meta_rew']
        self._history = defaultdict(list)
        return batch

class SubgoalPPORolloutRunner(object):
    def __init__(self, config, env, env_eval, meta_pi, pi):
        self._config = config
        self._env = env
        self._env_eval = env_eval
        self._meta_pi = meta_pi
        self._pi = pi
        self._ik_env = gym.make(config.env, **config.__dict__)

    def run(self, max_step=10000, is_train=True, random_exploration=False, every_steps=None, every_episodes=None):
        if every_steps is None and every_episodes is None:
            raise ValueError("Both every_steps and every_episodes cannot be None")

        config = self._config
        device = config.device
        env = self._env if is_train else self._env_eval
        max_step = env.max_episode_steps
        meta_pi = self._meta_pi
        pi = self._pi
        ik_env = self._ik_env
        ik_env.reset()

        rollout = Rollout()
        meta_rollout = MetaRollout()
        reward_info = Info()
        ep_info = Info()
        episode = 0
        step = 0

        while True:
            done = False
            ep_len = 0
            ep_rew = 0
            mp_success = 0
            prev_primitive = -1
            cur_primitive = -1
            contact_skill_num = 0
            meta_ac = None
            success = False
            term = True
            skill_count = {}
            if self._config.hrl:
                for skill in pi._skills:
                    skill_count[skill] = 0
            ob = env.reset()

            while not done and ep_len < max_step:
                if not config.meta_oracle:
                    meta_ac, meta_ac_before_activation, meta_log_prob =\
                            meta_pi.act(ob, is_train=is_train)
                else:
                    if config.skill_ordering:
                        if config.termination and term:
                            cur_primitive += 1
                            term = False
                        meta_ac = OrderedDict([('default', np.array([cur_primitive]))])
                    elif config.alternation:
                        assert config.termiantion, "Termination has to be turned on"
                        if term:
                            if cur_primitive == 1:
                                cur_primitive = 0
                            elif cur_primitive == 0:
                                cur_primitive = 1
                            else:
                                cur_primitive = 0
                        meta_ac = OrderedDict([('default', np.array([cur_primitive]))])
                    else:
                        prev_primitive = cur_primitive
                        cur_primitive_str = env.get_next_primitive(np.array([prev_primitive]))
                        if cur_primitive_str is not None:
                            cur_primitive = [cur_primitive_str in v.lower() for v in config.primitive_skills].index(True)
                            meta_ac = OrderedDict([('default', np.array([cur_primitive]))])
                        else:
                            cur_primitive = prev_primitive
                    meta_ac_before_activation = None
                    meta_log_prob = None

                meta_len = 0
                meta_rew = 0

                curr_qpos = env.sim.data.qpos.ravel().copy()
                skill_type = pi.return_skill_type(meta_ac)
                skill_count[skill_type] += 1
                info = OrderedDict()
                if 'mp' in skill_type:
                    traj, success, target_qpos, subgoal_ac, ac_before_activation = pi.plan(curr_qpos, meta_ac=meta_ac,
                                                                     ob=ob.copy(),
                                                                     random_exploration=random_exploration,
                                                                     ref_joint_pos_indexes=env.ref_joint_pos_indexes)
                    if success:
                        mp_success += 1
                        cum_rew = 0
                        ll_ob = ob.copy()
                        prev_ob = ob.copy()
                        meta_rollout.add({
                            'meta_ob': ob, 'meta_ac': meta_ac, 'meta_ac_before_activation': meta_ac_before_activation, 'meta_log_prob': meta_log_prob,
                        })
                        vpred = pi.get_value(ll_ob, meta_ac)
                        step += 1
                        for next_qpos in traj:
                            ll_ob = ob.copy()
                            ac = env.form_action(next_qpos, cur_primitive)
                            ob, reward, done, info = env.step(ac, is_planner=True)
                            cum_rew += reward
                            ep_len += 1
                            ep_rew += reward
                            meta_len += 1
                            reward_info.add(info)
                            if done or ep_len >= max_step:
                                break

                        if self._config.subgoal_hindsight: # refer to HAC
                            hindsight_subgoal_ac = OrderedDict([('default', env.sim.data.qpos[env.ref_joint_pos_indexes].copy() - curr_qpos[env.ref_joint_pos_indexes])])
                            if config.termination:
                                hindsight_subgoal_ac['term'] = subgoal_ac['term']
                            rollout.add({'ob': prev_ob, 'meta_ac': meta_ac, 'ac': hindsight_subgoal_ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})
                        else:
                            rollout.add({'ob': prev_ob, 'meta_ac': meta_ac, 'ac': subgoal_ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})

                        meta_rollout.add({'meta_done': done, 'meta_rew': reward})
                        rollout.add({'done': done, 'rew': reward})
                        if config.termination:
                            term = bool(subgoal_ac['term'][0])
                        if every_steps is not None and step % every_steps == 0:
                            # last frame
                            ll_ob = ob.copy()
                            vpred = pi.get_value(ll_ob, meta_ac)
                            rollout.add({'ob': ll_ob, 'vpred': vpred})
                            meta_rollout.add({'meta_ob': ob})
                            yield rollout.get(), meta_rollout.get(), ep_info.get_dict(only_scalar=True)

                        if not done and config.skill_ordering:
                            if config.termination and term and cur_primitive == len(config.primitive_skills)-1:
                                done = True
                                done, info, _ = env._after_step(None, done, {})
                                reward_info.add(info)

                    else:
                        ll_ob = ob.copy()
                        reward = self._config.meta_subgoal_rew
                        vpred = pi.get_value(ll_ob, meta_ac)
                        meta_rollout.add({
                            'meta_ob': ob, 'meta_ac': meta_ac, 'meta_ac_before_activation': meta_ac_before_activation, 'meta_log_prob': meta_log_prob,
                        })
                        rollout.add({'ob': ll_ob, 'meta_ac': meta_ac, 'ac': subgoal_ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})
                        if not env.isValidState(self._config.ignored_contact_geom_ids[cur_primitive]):
                            done = True
                        done, info, _ = env._after_step(reward, done, info)
                        rollout.add({'done': done, 'rew': reward})
                        meta_rollout.add({'meta_done': done, 'meta_rew': reward})
                        ep_len += 1
                        step += 1
                        ep_rew += reward
                        meta_len += 1
                        reward_info.add(info)
                        if config.termination:
                            term = bool(subgoal_ac['term'][0])
                        if every_steps is not None and step % every_steps == 0:
                            # last frame
                            vpred = pi.get_value(ll_ob, meta_ac)
                            rollout.add({'ob': ll_ob, 'vpred': vpred})
                            meta_rollout.add({'meta_ob': ob})
                            yield rollout.get(), meta_rollout.get(), ep_info.get_dict(only_scalar=True)
                        if not done and config.skill_ordering:
                            if config.termination and term and cur_primitive == len(config.primitive_skills)-1:
                                done = True
                                done, info, _ = env._after_step(None, done, {})
                                reward_info.add(info)

                else:
                    contact_skill_num += 1
                    meta_rollout.add({
                        'meta_ob': ob, 'meta_ac': meta_ac, 'meta_ac_before_activation': meta_ac_before_activation, 'meta_log_prob': meta_log_prob,
                    })
                    while not done and ep_len < max_step and meta_len < config.max_meta_len:
                        ll_ob = ob.copy()
                        if config.hrl:
                            ac, ac_before_activation, stds = pi.act(ll_ob, meta_ac, is_train=is_train, return_stds=True)
                        else:
                            ac, ac_before_activation, stds = pi.act(ll_ob, is_train=is_train, return_stds=True)
                        vpred = pi.get_value(ll_ob, meta_ac)
                        rollout.add({'ob': ll_ob, 'meta_ac': meta_ac, 'ac': ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})
                        ob, reward, done, info = env.step(ac)
                        rollout.add({'done': done, 'rew': reward})

                        ep_len += 1
                        step += 1
                        ep_rew += reward
                        meta_len += 1
                        meta_rew += reward
                        reward_info.add(info)
                        if config.termination:
                            term = bool(ac['term'][0])

                        if every_steps is not None and step % every_steps == 0:
                            # last frame
                            ll_ob = ob.copy()
                            vpred = pi.get_value(ll_ob, meta_ac)
                            rollout.add({'ob': ll_ob, 'vpred': vpred})
                            meta_rollout.add({'meta_done': done, 'meta_rew': meta_rew})
                            meta_rollout.add({'meta_ob': ob})
                            yield rollout.get(), meta_rollout.get(), ep_info.get_dict(only_scalar=True)

                        if not done and (config.skill_ordering or config.alternation) and config.termination and term: # break the loop if termination is true
                            break

                    if len(meta_rollout) != 0:
                        meta_rollout.add({'meta_done': done, 'meta_rew': meta_rew})
                    if not done and config.skill_ordering:
                        if cur_primitive == len(config.primitive_skills)-1 or (config.contact_check and not env.is_contact_skill_success(contact_skill_num)):
                            done = True
                            done, info, _ = env._after_step(None, done, {})
                            reward_info.add(info)
                        else:
                            term = True



            ep_info.add({'len': ep_len, 'rew': ep_rew, 'mp_success': mp_success})
            ep_info.add(skill_count)
            reward_info_dict = reward_info.get_dict(reduction="sum", only_scalar=True)
            ep_info.add(reward_info_dict)
            logger.info('Ep %d rollout: %s %s', episode,
                        {k: v for k, v in reward_info_dict.items()
                         if not 'qpos' in k and np.isscalar(v)}, {k: v for k, v in skill_count.items()})
            episode += 1

    def run_episode(self, max_step=10000, is_train=True, record=False, random_exploration=False):
        config = self._config
        device = config.device
        env = self._env if is_train else self._env_eval
        max_step = env.max_episode_steps
        meta_pi = self._meta_pi
        pi = self._pi
        ik_env = self._ik_env
        ik_env.reset()

        self._record_frames = []

        rollout = Rollout()
        meta_rollout = MetaRollout()
        reward_info = Info()
        ep_info = Info()
        step = 0

        done = False
        ep_len = 0
        ep_rew = 0
        mp_success = 0
        meta_ac = None
        term = True
        prev_primitive = -1
        cur_primitive = -1
        contact_skill_num = 0
        skill_count = {}
        if self._config.hrl:
            for skill in pi._skills:
                skill_count[skill] = 0

        ob = env.reset()
        if record: self._store_frame(env)

        while not done and ep_len < max_step:
            if not config.meta_oracle:
                if random_exploration: # Random exploration for SAC
                    meta_ac = meta_pi.sample_action()
                    meta_ac_before_activation = None
                    meta_log_prob = None
                else:
                    meta_ac, meta_ac_before_activation, meta_log_prob =\
                            meta_pi.act(ob, is_train=is_train)
            else:
                if config.skill_ordering:
                    if config.termination and term:
                        cur_primitive += 1
                        term = False
                    meta_ac = OrderedDict([('default', np.array([cur_primitive]))])
                elif config.alternation:
                    assert config.termiantion, "Termination has to be turned on"
                    if term:
                        if cur_primitive == 1:
                            cur_primitive = 0
                        elif cur_primitive == 0:
                            cur_primitive = 1
                        else:
                            cur_primitive = 0
                    meta_ac = OrderedDict([('default', np.array([cur_primitive]))])
                else:
                    prev_primitive = cur_primitive
                    cur_primitive_str = env.get_next_primitive(np.array([prev_primitive]))
                    if cur_primitive_str is not None:
                        cur_primitive = [cur_primitive_str in v.lower() for v in config.primitive_skills].index(True)
                        meta_ac = OrderedDict([('default', np.array([cur_primitive]))])
                    else:
                        cur_primitive = prev_primitive
                meta_ac_before_activation = None
                meta_log_prob = None

            meta_len = 0
            meta_rew = 0
            curr_qpos = env.sim.data.qpos.ravel().copy()
            skill_type = pi.return_skill_type(meta_ac)
            skill_count[skill_type] += 1
            goal_xpos = None
            goal_xquat = None

            info = OrderedDict()
            if 'mp' in skill_type:
                traj, success, target_qpos, subgoal_ac, ac_before_activation = pi.plan(curr_qpos,
                                                                                       meta_ac=meta_ac,
                                                                                       ob=ob.copy(),
                                                                                       ref_joint_pos_indexes=env.ref_joint_pos_indexes)

                ik_env.set_state(target_qpos, env.sim.data.qvel.ravel().copy())
                goal_xpos, goal_xquat = self._get_mp_body_pos(ik_env, postfix='goal')
                ll_ob = ob.copy()
                prev_ob = ob.copy()
                meta_rollout.add({
                    'meta_ob': ob, 'meta_ac': meta_ac, 'meta_ac_before_activation': meta_ac_before_activation, 'meta_log_prob': meta_log_prob,
                })
                vpred = pi.get_value(ll_ob, meta_ac)
                if success:
                    mp_success += 1
                    for next_qpos in traj:
                        ll_ob = ob.copy()
                        ac = env.form_action(next_qpos, cur_primitive)
                        ob, reward, done, info = env.step(ac, is_planner=True)
                        meta_rollout.add({'meta_done': done, 'meta_rew': reward})
                        rollout.add({'done': done, 'rew': reward})

                        ep_len += 1
                        step += 1
                        ep_rew += reward
                        meta_len += 1
                        reward_info.add(info)

                        if record:
                            frame_info = info.copy()
                            frame_info['ac'] = ac['default']
                            frame_info['target_qpos'] = target_qpos
                            frame_info['subgoal'] = subgoal_ac
                            frame_info['states'] = 'Valid states'
                            curr_qpos = env.sim.data.qpos.copy()
                            frame_info['curr_qpos'] = curr_qpos
                            frame_info['mp_path_qpos'] = next_qpos[env.ref_joint_pos_indexes]
                            frame_info['goal'] = env.goal
                            frame_info['skill_type'] = skill_type
                            for i, k in enumerate(meta_ac.keys()):
                                if k == 'subgoal' and k != 'default':
                                    frame_info['meta_subgoal'] = meta_ac[k]
                                elif k != 'default':
                                    frame_info['meta_'+k] = meta_ac[k]

                            ik_qpos = env.sim.data.qpos.ravel().copy()
                            ik_qpos[env.ref_joint_pos_indexes] = next_qpos[env.ref_joint_pos_indexes]
                            ik_env.set_state(ik_qpos, ik_env.sim.data.qvel.ravel())
                            xpos, xquat = self._get_mp_body_pos(ik_env)
                            vis_pos = [(xpos, xquat), (goal_xpos, goal_xquat)]
                            self._store_frame(env, frame_info, None, vis_pos=vis_pos)
                        if done or ep_len >= max_step:
                            break
                    if config.termination:
                        term = bool(subgoal_ac['term'][0])
                    if self._config.subgoal_hindsight: # refer to HAC
                        hindsight_subgoal_ac = OrderedDict([('default', env.sim.data.qpos[env.ref_joint_pos_indexes].copy() - curr_qpos[env.ref_joint_pos_indexes])])
                        hindsight_subgoal_ac['term'] = subgoal_ac['term']
                        rollout.add({'ob': prev_ob, 'meta_ac': meta_ac, 'ac': hindsight_subgoal_ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})
                    else:
                        rollout.add({'ob': prev_ob, 'meta_ac': meta_ac, 'ac': subgoal_ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})
                    if not done and config.skill_ordering:
                        if config.termination and term and cur_primitive == len(config.primitive_skills)-1:
                            done = True
                            done, info, _ = env._after_step(None, done, info)
                            reward_info.add(info)

                else:
                    ll_ob = ob.copy()
                    meta_rollout.add({
                        'meta_ob': ob, 'meta_ac': meta_ac, 'meta_ac_before_activation': meta_ac_before_activation, 'meta_log_prob': meta_log_prob,
                    })
                    reward = self._config.meta_subgoal_rew
                    vpred = pi.get_value(ll_ob, meta_ac)
                    rollout.add({'ob': ll_ob, 'meta_ac': meta_ac, 'ac': subgoal_ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})
                    done, info, _ = env._after_step(reward, False, info)
                    reward_info.add(info)
                    rollout.add({'done': done, 'rew': reward})
                    ep_len += 1
                    step += 1
                    ep_rew += reward
                    meta_len += 1
                    meta_rollout.add({'meta_done': done, 'meta_rew': reward})
                    if config.termination:
                        term = bool(subgoal_ac['term'][0])
                    if record:
                        frame_info = info.copy()
                        frame_info['states'] = 'Invalid states'
                        frame_info['target_qpos'] = target_qpos
                        curr_qpos = env.sim.data.qpos.copy()
                        frame_info['curr_qpos'] = curr_qpos
                        frame_info['goal'] = env.goal
                        frame_info['skill_type'] = skill_type
                        frame_info['contacts'] = env.sim.data.ncon
                        for i, k in enumerate(meta_ac.keys()):
                            if k == 'subgoal' and k != 'default':
                                frame_info['meta_subgoal'] = meta_ac[k]
                            elif k != 'default':
                                frame_info['meta_'+k] = meta_ac[k]

                        xpos, xquat = self._get_mp_body_pos(ik_env)
                        vis_pos = [(xpos, xquat), (goal_xpos, goal_xquat)]
                        self._store_frame(env, frame_info, None, vis_pos=vis_pos)
                    if not done and config.skill_ordering:
                        if config.termination and term and cur_primitive == len(config.primitive_skills)-1:
                            done = True
                            done, info, _ = env._after_step(None, done, info)
                            reward_info.add(info)
            else:
                contact_skill_num += 1
                while not done and ep_len < max_step and meta_len < config.max_meta_len:
                    ll_ob = ob.copy()
                    meta_rollout.add({
                        'meta_ob': ob, 'meta_ac': meta_ac, 'meta_ac_before_activation': meta_ac_before_activation, 'meta_log_prob': meta_log_prob,
                    })
                    if config.hrl:
                        ac, ac_before_activation, stds = pi.act(ll_ob, meta_ac, is_train=is_train, return_stds=True)
                    else:
                        ac, ac_before_activation, stds = pi.act(ll_ob, is_train=is_train, return_stds=True)
                    vpred = pi.get_value(ll_ob, meta_ac)
                    rollout.add({'ob': ll_ob, 'meta_ac': meta_ac, 'ac': ac, 'ac_before_activation': ac_before_activation, 'vpred': vpred})

                    ob, reward, done, info = env.step(ac)
                    rollout.add({'done': done, 'rew': reward})

                    ep_len += 1
                    step += 1
                    ep_rew += reward
                    meta_len += 1
                    meta_rew += reward
                    reward_info.add(info)
                    meta_rollout.add({'meta_done': done, 'meta_rew': reward})
                    if config.termination:
                        term = bool(ac['term'][0])
                    if record:
                        frame_info = info.copy()
                        frame_info['ac'] = ac['default']
                        curr_qpos = env.sim.data.qpos.copy()
                        frame_info['curr_qpos'] = curr_qpos
                        frame_info['goal'] = env.goal
                        frame_info['skill_type'] = skill_type
                        for i, k in enumerate(meta_ac.keys()):
                            if k == 'subgoal' and k != 'default':
                                frame_info['meta_subgoal'] = meta_ac[k]
                            elif k != 'default':
                                frame_info['meta_'+k] = meta_ac[k]

                        vis_pos=[]
                        self._store_frame(env, frame_info, None, vis_pos=[])

                    if not done and (config.skill_ordering or config.alternation) and config.termination and term: # break the loop if termination is true
                        break

                if not done and config.skill_ordering:
                    if cur_primitive == len(config.primitive_skills)-1 or (config.contact_check and not env.is_contact_skill_success(contact_skill_num)):
                        done = True
                        done, info, _ = env._after_step(None, done, {})
                        reward_info.add(info)
                    else:
                        term = True


        ep_info.add({'len': ep_len, 'rew': ep_rew, 'mp_success': mp_success})
        ep_info.add(skill_count)
        reward_info_dict = reward_info.get_dict(reduction="sum", only_scalar=True)
        ep_info.add(reward_info_dict)
        # last frame
        ll_ob = ob.copy()
        vpred = pi.get_value(ll_ob, meta_ac)
        rollout.add({'ob': ll_ob, 'meta_ac': meta_ac, 'vpred': vpred})
        meta_rollout.add({'meta_ob': ob})
        return rollout.get(), meta_rollout.get(), ep_info.get_dict(only_scalar=True), self._record_frames

    def _get_mp_body_pos(self, ik_env, postfix='dummy'):
        xpos = OrderedDict()
        xquat = OrderedDict()
        for i in range(len(ik_env.ref_joint_pos_indexes)):
            name = 'body'+str(i)
            body_idx = ik_env.sim.model.body_name2id(name)
            xpos[name+'-'+ postfix] = ik_env.sim.data.body_xpos[body_idx].copy()
            xquat[name+'-'+postfix] = ik_env.sim.data.body_xquat[body_idx].copy()

        return xpos, xquat

    def _store_frame(self, env, info={}, subgoal=None, vis_pos=[]):
        color = (200, 200, 200)

        text = "{:4} {}".format(env._episode_length,
                                env._episode_reward)

        if self._config.hl_type == 'subgoal' and subgoal is not None:
            env._set_pos('subgoal', [subgoal[0], subgoal[1], env._get_pos('subgoal')[2]])
            env._set_color('subgoal', [0.2, 0.9, 0.2, 1.])

        for xpos, xquat in vis_pos:
            for k in xpos.keys():
                env._set_pos(k, xpos[k])
                env._set_quat(k, xquat[k])
                color = env._get_color(k)
                color[-1] = 0.3
                env._set_color(k, color)

        frame = env.render('rgb_array') * 255.0
        env._set_color('subgoal', [0.2, 0.9, 0.2, 0.])
        for xpos, xquat in vis_pos:
            if xpos is not None and xquat is not None:
                for k in xpos.keys():
                    color = env._get_color(k)
                    color[-1] = 0.
                    env._set_color(k, color)

        fheight, fwidth = frame.shape[:2]
        frame = np.concatenate([frame, np.zeros((fheight, fwidth, 3))], 0)

        if self._config.record_caption:
            font_size = 0.4
            thickness = 1
            offset = 12
            x, y = 5, fheight + 10
            cv2.putText(frame, text,
                        (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                        font_size, (255, 255, 0), thickness, cv2.LINE_AA)
            for i, k in enumerate(info.keys()):
                v = info[k]
                key_text = '{}: '.format(k)
                (key_width, _), _ = cv2.getTextSize(key_text, cv2.FONT_HERSHEY_SIMPLEX,
                                                    font_size, thickness)

                cv2.putText(frame, key_text,
                            (x, y + offset * (i + 2)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            font_size, (66, 133, 244), thickness, cv2.LINE_AA)

                cv2.putText(frame, str(v),
                            (x + key_width, y + offset * (i + 2)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            font_size, (255, 255, 255), thickness, cv2.LINE_AA)

        self._record_frames.append(frame)
