# SAC training code reference
# https://github.com/vitchyr/rlkit/blob/master/rlkit/torch/sac/sac.py

from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from rl.dataset import ReplayBuffer, RandomSampler
from rl.base_agent import BaseAgent
from rl.policies.decoder import Decoder
from rl.policies.encoder import Encoder
from util.logger import logger
from util.mpi import mpi_average
from util.pytorch import optimizer_cuda, count_parameters, \
    compute_gradient_norm, compute_weight_norm, sync_networks, sync_grads, to_tensor
from util.gym import action_size, observation_size
from gym import spaces


class SACAEAgent(BaseAgent):
    def __init__(self, config, ob_space, ac_space,
                 actor, critic):
        super().__init__(config, ob_space)

        self._ob_space = ob_space
        self._ac_space = ac_space

        self.policy_ob_space = spaces.Dict({'default': spaces.Box(shape=(config.ae_feat_dim, ), low=-1., high=1.)})

        self._target_entropy = -action_size(ac_space)
        self._log_alpha = torch.zeros(1, requires_grad=True, device=config.device)
        self._alpha_optim = optim.Adam([self._log_alpha], lr=config.lr_actor)

        # build up networks
        self._build_actor(actor)
        self._critic1 = critic(config, self.policy_ob_space, ac_space)
        self._critic2 = critic(config, self.policy_ob_space, ac_space)

        # build up target networks
        self._critic1_target = critic(config, self.policy_ob_space, ac_space)
        self._critic2_target = critic(config, self.policy_ob_space, ac_space)
        self._critic1_target.load_state_dict(self._critic1.state_dict())
        self._critic2_target.load_state_dict(self._critic2.state_dict())
        self._critic_encoder = Encoder(config, ob_space['default'].shape[0], config.ae_feat_dim)
        self._actor_encoder = Encoder(config, ob_space['default'].shape[0], config.ae_feat_dim)
        self._actor_encoder.copy_conv_weights_from(self._critic_encoder)
        self._decoder = Decoder(config, config.ae_feat_dim, self._critic_encoder.w)
        print(self._actor_encoder)

        self._network_cuda(config.device)

        self._actor_optims = [optim.Adam(list(_actor.parameters())+list(self._actor_encoder.parameters()), lr=config.lr_actor) for _actor in self._actors]
        self._critic1_optim = optim.Adam(list(self._critic1.parameters())+list(self._critic_encoder.parameters()), lr=config.lr_critic)
        self._critic2_optim = optim.Adam(list(self._critic2.parameters())+list(self._critic_encoder.parameters()), lr=config.lr_critic)

        self._encoder_optim = optim.Adam(self._critic_encoder.parameters(),
                                         lr=config.lr_encoder)
        self._decoder_optim = optim.Adam(self._decoder.parameters(),
                                         lr=config.lr_decoder)

        sampler = RandomSampler()
        buffer_keys = ['ob', 'ac', 'meta_ac', 'done', 'rew']
        self._buffer = ReplayBuffer(buffer_keys,
                                    config.buffer_size,
                                    sampler.sample_func)

        self._log_creation()

    def _log_creation(self):
        if self._config.is_chef:
            logger.info('Creating a SAC agent')
            for i, _actor in enumerate(self._actors):
                logger.info('Skill #{} has %d parameters'.format(i + 1), count_parameters(_actor))
            logger.info('The critic1 has %d parameters', count_parameters(self._critic1))
            logger.info('The critic2 has %d parameters', count_parameters(self._critic2))


    def _build_actor(self, actor):
        self._actors = [actor(self._config, self.policy_ob_space, self._ac_space,
                               self._config.tanh_policy)] # num_body_parts, num_skills

    def store_episode(self, rollouts):
        self._buffer.store_episode(rollouts)

    def state_dict(self):
        return {
            'log_alpha': self._log_alpha.cpu().detach().numpy(),
            'actor_state_dict': [_actor.state_dict() for _actor in self._actors],
            'critic1_state_dict': self._critic1.state_dict(),
            'critic2_state_dict': self._critic2.state_dict(),
            'alpha_optim_state_dict': self._alpha_optim.state_dict(),
            'actor_optim_state_dict': [_actor_optim.state_dict() for _actor_optim in self._actor_optims],
            'critic1_optim_state_dict': self._critic1_optim.state_dict(),
            'critic2_optim_state_dict': self._critic2_optim.state_dict(),
            'ob_norm_state_dict': self._ob_norm.state_dict(),
            'critic_encoder_state_dict': self._critic_encoder.state_dict(),
            'decoder_state_dict': self._decoder.state_dict(),
            'actor_encoder_state_dict': self._actor_encoder.state_dict(),
            'encoder_optim_state_dict': self._encoder_optim.state_dict(),
            'decoder_optim_state_dict': self._decoder_optim.state_dict()
        }

    def load_state_dict(self, ckpt):
        self._log_alpha.data = torch.tensor(ckpt['log_alpha'], requires_grad=True,
                                            device=self._config.device)
        for _actor, actor_ckpt in zip(self._actors, ckpt['actor_state_dict']):
            _actor.load_state_dict(actor_ckpt)
        self._critic1.load_state_dict(ckpt['critic1_state_dict'])
        self._critic2.load_state_dict(ckpt['critic2_state_dict'])
        self._critic1_target.load_state_dict(self._critic1.state_dict())
        self._critic2_target.load_state_dict(self._critic2.state_dict())
        self._actor_encoder.load_state_dict(ckpt['actor_encoder_state_dict'])
        self._critic_encoder.load_state_dict(ckpt['critc_encoder_state_dict'])
        self._actor_encoder.copy_conv_weights_from(self._critic_encoder)
        self._decoder.load_state_dict(ckpt['decoder_state_dict'])
        self._ob_norm.load_state_dict(ckpt['ob_norm_state_dict'])
        self._network_cuda(self._config.device)

        self._alpha_optim.load_state_dict(ckpt['alpha_optim_state_dict'])
        for _actor_optim, actor_optim_ckpt in zip(self._actor_optims, ckpt['actor_optim_state_dict']):
            _actor_optim.load_state_dict(actor_optim_ckpt)
        self._critic1_optim.load_state_dict(ckpt['critic1_optim_state_dict'])
        self._critic2_optim.load_state_dict(ckpt['critic2_optim_state_dict'])
        self._encoder_optim.load_state_dict(ckpt['encoder_optim_state_dict'])
        self._decoder_optim.load_state_dict(ckpt['decoder_optim_state_dict'])
        optimizer_cuda(self._alpha_optim, self._config.device)
        for _actor_optim in self._actor_optims:
            optimizer_cuda(_actor_optim, self._config.device)
        optimizer_cuda(self._critic1_optim, self._config.device)
        optimizer_cuda(self._critic2_optim, self._config.device)

    def _network_cuda(self, device):
        for _actor in self._actors:
            _actor.to(device)
        self._critic1.to(device)
        self._critic2.to(device)
        self._critic1_target.to(device)
        self._critic2_target.to(device)
        self._actor_encoder.to(device)
        self._critic_encoder.to(device)
        self._decoder.to(device)

    def sync_networks(self):
        for _actor in self._actors:
            sync_networks(_actor)
        sync_networks(self._critic1)
        sync_networks(self._critic2)

    def train(self):
        for i in range(self._config.num_batches):
            transitions = self._buffer.sample(self._config.batch_size)
            train_info = self._update_network(transitions, i)

            if i % self._config.critic_target_update_freq == 0:
                self._soft_update_target_network(self._critic1_target, self._critic1, self._config.polyak)
                self._soft_update_target_network(self._critic2_target, self._critic2, self._config.polyak)
            decoder_info = self._update_decoder(transitions['ob'], transitions['ob'])

        train_info.update({
            'actor_grad_norm': np.mean([compute_gradient_norm(_actor) for _actor in self._actors]),
            'actor_weight_norm': np.mean([compute_weight_norm(_actor) for _actor in self._actors]),
            'critic1_grad_norm': compute_gradient_norm(self._critic1),
            'critic2_grad_norm': compute_gradient_norm(self._critic2),
            'critic1_weight_norm': compute_weight_norm(self._critic1),
            'critic2_weight_norm': compute_weight_norm(self._critic2),
        })

        for k, v in decoder_info.items():
            train_info.update({
                k: v
            })
        return train_info

    def act_log(self, ob, meta_ac=None):
        #assert meta_ac is None, "vanilla SAC agent doesn't support meta action input"
        if meta_ac:
            raise NotImplementedError()
        ob['default'] = self._actor_encoder(ob['default'], detach=True)
        return self._actors[0].act_log(ob)

    def act(self, ob, is_train=True, return_stds=False):
        ob = to_tensor(ob, self._config.device)
        ob['default'] = self._actor_encoder(ob['default'])
        if return_stds:
            ac, activation, stds = self._actors[0].act(ob, is_train=is_train, return_stds=return_stds)
            return ac, activation, stds
        else:
            ac, activation = self._actors[0].act(ob, is_train=is_train, return_stds=return_stds)
            return ac, activation

    def _update_decoder(self, obs, target_obs):
        info = {}
        _to_tensor = lambda x: to_tensor(x, self._config.device)
        obs = _to_tensor(obs)
        target_obs = _to_tensor(target_obs)
        h = self._critic_encoder(obs['default'])

        rec_obs = self._decoder(h)
        rec_loss = F.mse_loss(target_obs['default'], rec_obs)

        latent_loss = (0.5*h.pow(2).sum(1)).mean()

        loss = rec_loss + self._config.decoder_latent_lambda * latent_loss
        self._encoder_optim.zero_grad()
        self._decoder_optim.zero_grad()
        loss.backward(retain_graph=True)

        self._encoder_optim.step()
        self._decoder_optim.step()
        info['ae_loss'] = loss

        return info


    def _update_network(self, transitions, step=0):
        info = {}
        o_h = OrderedDict()
        o_next_h = OrderedDict()

        # pre-process observations
        o, o_next = transitions['ob'], transitions['ob_next']

        if self._config.policy == 'mlp':
            o = self.normalize(o)
            o_next = self.normalize(o_next)

        bs = len(transitions['done'])
        _to_tensor = lambda x: to_tensor(x, self._config.device)
        o = _to_tensor(o)
        o_next = _to_tensor(o_next)
        ac = _to_tensor(transitions['ac'])
        if self._config.hrl:
            meta_ac = _to_tensor(transitions['meta_ac'])
        else:
            meta_ac = None
        done = _to_tensor(transitions['done']).reshape(bs, 1)
        rew = _to_tensor(transitions['rew']).reshape(bs, 1)

        # update alpha
        o_act = OrderedDict([('default', o['default'])])
        actions_real, log_pi = self.act_log(o_act, meta_ac=meta_ac)
        alpha_loss = -(self._log_alpha * (log_pi + self._target_entropy).detach()).mean()
        self._alpha_optim.zero_grad()
        alpha_loss.backward(retain_graph=True)
        self._alpha_optim.step()
        alpha = self._log_alpha.exp()

        # the actor loss
        o_h['default'] = self._critic_encoder(o['default'])
        entropy_loss = (alpha * log_pi).mean()
        actor_loss = -torch.min(self._critic1(o_h, actions_real),
                                self._critic2(o_h, actions_real)).mean()
        info['entropy_alpha'] = alpha.cpu().item()
        info['entropy_loss'] = entropy_loss.cpu().item()
        info['actor_loss'] = actor_loss.cpu().item()
        actor_loss += entropy_loss

        # calculate the target Q value function
        with torch.no_grad():
            o_next_act = OrderedDict([('default', o_next['default'])])
            actions_next, log_pi_next = self.act_log(o_next_act, meta_ac=meta_ac)
            o_next_h['default'] = self._critic_encoder(o_next['default'])
            q_next_value1 = self._critic1_target(o_next_h, actions_next)
            q_next_value2 = self._critic2_target(o_next_h, actions_next)
            q_next_value = torch.min(q_next_value1, q_next_value2) - alpha * log_pi_next
            target_q_value = rew * self._config.reward_scale + \
                (1 - done) * self._config.discount_factor * q_next_value
            target_q_value = target_q_value.detach()
            ## clip the q value
            #clip_return = 1 / (1 - self._config.discount_factor)
            #target_q_value = torch.clamp(target_q_value, -clip_return, clip_return)

        # the q loss
        real_q_value1 = self._critic1(o_h, ac)
        real_q_value2 = self._critic2(o_h, ac)
        critic1_loss = 0.5 * (target_q_value - real_q_value1).pow(2).mean()
        critic2_loss = 0.5 * (target_q_value - real_q_value2).pow(2).mean()

        info['min_target_q'] = target_q_value.min().cpu().item()
        info['target_q'] = target_q_value.mean().cpu().item()
        info['min_real1_q'] = real_q_value1.min().cpu().item()
        info['min_real2_q'] = real_q_value2.min().cpu().item()
        info['real1_q'] = real_q_value1.mean().cpu().item()
        info['real2_q'] = real_q_value2.mean().cpu().item()
        info['critic1_loss'] = critic1_loss.cpu().item()
        info['critic2_loss'] = critic2_loss.cpu().item()


        if step % self._config.actor_update_freq == 0:
            # update the actor
            for _actor_optim in self._actor_optims:
                _actor_optim.zero_grad()
            actor_loss.backward(retain_graph=True)
            for i, _actor in enumerate(self._actors):
                if self._config.max_grad_norm is not None:
                    torch.nn.utils.clip_grad_norm_(_actor.parameters(), self._config.max_grad_norm)
                sync_grads(_actor)
                self._actor_optims[i].step()

        # update the critic
        self._critic1_optim.zero_grad()
        critic1_loss.backward(retain_graph=True)
        if self._config.max_grad_norm is not None:
            torch.nn.utils.clip_grad_norm_(self._critic1.parameters(), self._config.max_grad_norm)
        sync_grads(self._critic1)
        self._critic1_optim.step()

        self._critic2_optim.zero_grad()
        critic2_loss.backward(retain_graph=True)
        if self._config.max_grad_norm is not None:
            torch.nn.utils.clip_grad_norm_(self._critic2.parameters(), self._config.max_grad_norm)
        sync_grads(self._critic2)
        self._critic2_optim.step()

        # include info from policy
        if len(self._actors) == 1:
            info.update(self._actors[0].info)
        else:
            constructed_info = {}
            for i, _agent in enumerate(self._actors):
                for j, _actor in enumerate(_agent):
                    for k, v in _actor.info:
                        constructed_info['agent_{}/skill_{}/{}'.format(i + 1, j + 1, k)] = v
            info.update(constructed_info)

        return mpi_average(info)