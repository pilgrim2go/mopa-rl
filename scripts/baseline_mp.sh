python -m rl.main --env reacher-v0 --hrl True --log_root_dir ./logs --prefix baseline.mp.rrt.v2 --max_global_step 10000000 --meta_update_target both --ll_type mp --planner_type rrt --planner_objective state_const_integral --range 15.0 --threshold 0.1 --timelimit 1 --hl_type subgoal --gpu 1 --max_mp_steps 50 --max_meta_len 50 --construct_time 300
