python -m rl.main --env reacher-pixel-v0 --hrl True --log_root_dir ./logs --prefix baseline.mp.sst.reacher.pixel --max_global_step 10000000 --meta_update_target both --ll_type mp --planner_type sst --planner_objective state_const_integral --range 6.0 --threshold 0.05 --timelimit 1 --hl_type subgoal --gpu 0 --max_mp_steps 50 --max_meta_len 50 --construct_time 300
