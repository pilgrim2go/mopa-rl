#!/bin/bash -x
gpu=$1
seed=$2

algo='sac'
rollout_length="1000"
evaluate_interval="1000"
ckpt_interval='200000'
rl_activation="relu"
num_batches="2"
log_interval="150"

workers="1"
tanh="True"
prefix="05.19.SAC.REUSE.SAWYER.ALLOW_APPROXIMATE"
max_global_step="60000000"
env="sawyer-lift-robosuite-v0"
rl_hid_size="256"
max_episode_step="1000"
entropy_loss_coef="1e-3"
buffer_size="1000000"
lr_actor="3e-4"
lr_critic="3e-4"
debug="False"
batch_size="256"
clip_param="0.2"
ctrl_reward='1e-2'
reward_type='dense'
comment='Fix motion planner'
start_steps='10000'
actor_num_hid_layers='2'
log_root_dir="./logs"
group='05.19.SAC.PLANNER.REUSE.SAWYER.ALLOW_APPROXIMATE'
env_debug='False'
log_freq='1000'
planner_integration="True"
ignored_contact_geoms='None,None'
planner_type="sst"
planner_objective="path_length"
range="0.03"
threshold="0.03"
timelimit="1.5"
allow_self_collision="False"
allow_manipulation_collision="True"
reward_scale="0.1"
subgoal_hindsight="False"
reuse_subgoal_data="True"
reuse_rl_data='False'
relative_goal="True"
simple_planner_timelimit="0.02"
action_range="1.0"
ac_rl_minimum="-0.1"
ac_rl_maximum="0.1"
invalid_planner_rew="0."
extended_action="False"
allow_approximate="True"
vis_replay="False"
# success_reward='150.'
# has_terminal='True'


# max_grad_norm='0.5'

#mpiexec -n $workers
python -m rl.main \
    --log_root_dir $log_root_dir \
    --wandb True \
    --prefix $prefix \
    --max_global_step $max_global_step \
    --env $env \
    --gpu $gpu \
    --rl_hid_size $rl_hid_size \
    --max_episode_step $max_episode_step \
    --evaluate_interval $evaluate_interval \
    --entropy_loss_coef $entropy_loss_coef \
    --buffer_size $buffer_size \
    --num_batches $num_batches \
    --lr_actor $lr_actor \
    --lr_critic $lr_critic \
    --debug $debug \
    --rollout_length $rollout_length \
    --batch_size $batch_size \
    --clip_param $clip_param \
    --rl_activation $rl_activation \
    --algo $algo \
    --seed $seed \
    --ctrl_reward $ctrl_reward \
    --reward_type $reward_type \
    --comment $comment \
    --start_steps $start_steps \
    --actor_num_hid_layers $actor_num_hid_layers \
    --group $group \
    --env_debug $env_debug \
    --log_freq $log_freq \
    --log_interval $log_interval \
    --tanh $tanh \
    --planner_integration $planner_integration \
    --ignored_contact_geoms $ignored_contact_geoms \
    --planner_type $planner_type \
    --planner_objective $planner_objective \
    --range $range \
    --threshold $threshold \
    --timelimit $timelimit \
    --allow_manipulation_collision $allow_manipulation_collision \
    --allow_self_collision $allow_self_collision \
    --reward_scale $reward_scale \
    --subgoal_hindsight $subgoal_hindsight \
    --reuse_subgoal_data $reuse_subgoal_data \
    --reuse_rl_data $reuse_rl_data \
    --relative_goal $relative_goal \
    --simple_planner_timelimit $simple_planner_timelimit \
    --action_range $action_range \
    --ac_rl_maximum $ac_rl_maximum \
    --ac_rl_minimum $ac_rl_minimum \
    --invalid_planner_rew $invalid_planner_rew \
    --extended_action $extended_action \
    --allow_approximate $allow_approximate \
    --vis_replay $vis_replay