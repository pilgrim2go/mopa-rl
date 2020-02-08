python -m rl.main --env reacher-pixel-v0 --hrl True --log_root_dir ./logs --prefix baseline.mp.sst.reacher.pixel.sac-ae.v3 --max_global_step 40000000 --meta_update_target both  --hrl_network_to_update both --ll_type mp --planner_type sst --planner_objective state_const_integral --range 12.0 --threshold 0.05 --timelimit 1 --hl_type subgoal --max_mp_steps 50 --max_meta_len 50 --policy cnn --rl_hid_size 128 --use_ae True --buffer_size 100000 --gpu 1
