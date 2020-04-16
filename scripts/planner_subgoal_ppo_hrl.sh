#!/bin/bash -x
v=$1
gpu=$2

if [ $v = 1 ]
then
    env="simple-pusher-v0"
    primitive_skills="reach_mp push"
elif [ $v = 2 ]
then
    env="simple-mover-v0"
    primitive_skills="reach_mp grasp manipulation_mp"
elif [ $v = 3 ]
then
    env='simple-mover-obstacle-v0'
    primitive_skills="reach_mp grasp manipulation_mp"
fi

workers="1"
prefix="4.15.LL.PPO.COLL.avg.grad.norm.tanh.rollout4096.addbias.ent.1e-3.num.batch.5.range.0.3"
hrl="True"
ll_type="mix"
planner_type="sst"
planner_objective="state_const_integral"
range="0.3"
threshold="0.5"
timelimit="0.01"
gpu=$gpu
rl_hid_size="256"
meta_update_target="LL"
meta_oracle="True"
meta_subgoal_rew="0."
max_meta_len="15"
buffer_size="12800"
num_batches="5"
debug="False"
rollout_length="4096"
batch_size="256"
evaluate_interval='10'
ckpt_interval='10'
reward_type="dense"
reward_scale="10."
entropy_loss_coeff='1e-3'
comment="init buffer size is 10 times batch size"
ctrl_reward_coef="1e-2"
actor_num_hid_layers="2"
subgoal_type="joint"
meta_algo='ppo'
success_reward='100.'
subgoal_predictor="True"
seed="1234"
has_terminal='True'
ignored_contact_geoms=' None,None box,l_finger_g0/box,r_finger_g0'
log_root_dir='./logs'
algo='ppo'
group='4.15.ppo-simple-mover-planner'
# max_grad_norm='0.5'
rl_activation='tanh'

#mpiexec -n $workers
python -m rl.main \
    --log_root_dir $log_root_dir \
    --wandb True \
    --prefix $prefix \
    --hrl $hrl \
    --ll_type $ll_type \
    --planner_type $planner_type \
    --planner_objective $planner_objective \
    --range $range \
    --threshold $threshold \
    --timelimit $timelimit \
    --env $env \
    --gpu $gpu \
    --rl_hid_size $rl_hid_size \
    --meta_update_target $meta_update_target \
    --meta_subgoal_rew $meta_subgoal_rew \
    --max_meta_len $max_meta_len \
    --buffer_size $buffer_size \
    --num_batches $num_batches \
    --debug $debug \
    --rollout_length $rollout_length \
    --batch_size $batch_size \
    --reward_type $reward_type \
    --reward_scale $reward_scale \
    --comment $comment \
    --seed $seed \
    --ctrl_reward_coef $ctrl_reward_coef \
    --actor_num_hid_layers $actor_num_hid_layers \
    --subgoal_type $subgoal_type \
    --meta_algo $meta_algo \
    --success_reward $success_reward \
    --primitive_skills $primitive_skills \
    --subgoal_predictor $subgoal_predictor \
    --has_terminal $has_terminal \
    --meta_oracle $meta_oracle \
    --ignored_contact_geoms $ignored_contact_geoms \
    --algo $algo \
    --evaluate_interval $evaluate_interval \
    --ckpt_interval $ckpt_interval \
    --entropy_loss_coeff $entropy_loss_coeff \
    --group $group \
    # --max_grad_norm $max_grad_norm \
    --rl_activation $rl_activation
