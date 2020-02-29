import re
from collections import OrderedDict

import numpy as np
from gym import spaces

from env.base import BaseEnv


class SimplePusherObstacleEnv(BaseEnv):
    """ Pusher with Obstacles environment. """

    def __init__(self, **kwargs):
        super().__init__("simple_pusher_obstacle.xml", **kwargs)
        self.obstacle_names = list(filter(lambda x: re.search(r'obstacle', x), self.model.body_names))

    def _reset(self):
        self._set_camera_position(0, [0, -0.7, 1.5])
        self._set_camera_rotation(0, [0, 0, 0])
        while True:
            goal = np.random.uniform(low=-0.2, high=.2, size=2)
            box = np.random.uniform(low=-0.2, high=.2, size=2)
            qpos = np.random.uniform(low=-0.1, high=0.1, size=self.model.nq) + self.sim.data.qpos.ravel()
            qpos[-4:-2] = goal
            qpos[-2:] = box
            qvel = np.random.uniform(low=-.005, high=.005, size=self.model.nv) + self.sim.data.qvel.ravel()
            qvel[-4:-2] = 0
            qvel[-2:] = 0
            self.set_state(qpos, qvel)
            if self.sim.data.ncon == 0 and np.linalg.norm(goal) > 0.2:
                self.goal = goal
                break
        return self._get_obs()

    def initalize_joints(self):
        while True:
            qpos = np.random.uniform(low=-0.1, high=0.1, size=self.model.nq) + self.sim.data.qpos.ravel()
            qpos[-4:-2] = goal
            qpos[-2:] = box
            self.set_state(qpos, self.sim.data.qvel.ravel())
            if self.sim.data.ncon == 0:
                break

    def _get_obstacle_states(self):
        obstacle_states = []
        obstacle_size = []
        for name in self.obstacle_names:
            obstacle_states.extend(self._get_pos(name)[:2])
            obstacle_size.extend(self._get_size(name)[:2])
        return np.concatenate([obstacle_states, obstacle_size])

    def _get_obs(self):
        theta = self.sim.data.qpos.flat[:self.model.nu]
        return OrderedDict([
            ('default', np.concatenate([
                np.cos(theta),
                np.sin(theta),
                self.sim.data.qpos.flat[self.model.nu:],
                self.sim.data.qvel.flat[:self.model.nu],
                self._get_obstacle_states(),
                self._get_pos('box'),
                self._get_pos("target")
            ]))
        ])

    @property
    def observation_space(self):
        return spaces.Dict([
            ('default', spaces.Box(shape=(26,), low=-1, high=1, dtype=np.float32))
        ])

    @property
    def get_joint_positions(self):
        """
        The joint position except for goal states
        """
        return self.sim.data.qpos.ravel()[:-4]

    def _step(self, action):
        """
        Args:
            action (numpy array): The array should have the corresponding elements.
                0-6: The desired change in joint state (radian)
        """

        info = {}
        done = False
        desired_state = self.get_joint_positions + action

        if self._env_config['reward_type'] == 'dense':
            reward_dist = -self._get_distance("fingertip", "target")
            reward_ctrl = self._ctrl_reward(action)
            reward = reward_dist + reward_ctrl
            info = dict(reward_dist=reward_dist, reward_ctrl=reward_ctrl)
        else:
            reward = -(self._get_distance('fingertip', 'target') > self._env_config['distance_threshold']).astype(np.float32)

        n_inner_loop = int(self._frame_dt/self.dt)

        prev_state = self.sim.data.qpos[:self.model.nu].copy()
        target_vel = (desired_state-prev_state) / self._frame_dt
        for t in range(n_inner_loop):
            action = self._get_control(desired_state, prev_state, target_vel)
            self._do_simulation(action)

        obs = self._get_obs()
        # if self._get_distance('fingertip', 'target') < self._env_config['distance_threshold']:
        #     done =True
        #     self._success = True
        return obs, reward, done, info

    def _kinematics_step(self, states):
        info = {}
        done = False

        if self._env_config['reward_type'] == 'dense':
            reward_dist = -self._get_distance("box", "target")
            reward = reward_dist
            info = dict(reward_dist=reward_dist)
        else:
            reward = -(self._get_distance('box', 'target') > self._env_config['distance_threshold']).astype(np.float32)

        states = np.concatenate((states[:self.model.nu], self.goal))
        self.set_state(states, self.sim.data.qvel.ravel())
        obs = self._get_obs()
        # if self._get_distance('fingertip', 'target') < self._env_config['distance_threshold']:
        #     done =True
        #     self._success = True
        return obs, reward, done, info
