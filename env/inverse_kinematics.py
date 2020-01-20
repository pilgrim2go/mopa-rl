import os, sys

import numpy as np
import collections
from dm_control.mujoco.wrapper import mjbindings

IKResult = collections.namedtuple(
    'IKResult', ['qpos', 'err_norm', 'steps', 'success']
)

def indexer(env, names):
    indices = []
    for name in names:
        indices.append(env.model.joint_name2id(name))

    return indices



def qpos_from_site_pose(env, site, target_pos=None, target_quat=None, joint_names=None,
                        max_steps=100, rot_weight=1., tol=1e-14,
                        max_update_norm=2.0, progress_thresh=20.0,
                        regularization_threshold=0.1, regularization_strength=3e-2):
    mjlib = mjbindings.mjlib
    dtype = env.sim.data.qpos.dtype

    if target_pos is not None and target_quat is not None:
        jac = np.empty((6, len(joint_names)), dtype=dtype)
        err = np.empty(6, dtype=dtype)

        jac_pos, jac_rot = jac[:3], jac[3:]
        err_pos, err_rot = err[:3], err[3:]
    else:
        jac = np.empty((3, len(joint_names)), dtype=dtype)
        err = np.empty(3, dtype=dtype)
        if target_pos is not None:
            jac_pos, _ = jac, None
            err_pos, _ = err, None
        elif target_quat is not None:
            _, jac_rot = None, jac
            _, err_rot = None, err
        else:
            raise ValueError('At least one of `target_pos` or `target_quat` must be specified')


    non_movable_joint_names = list(set(env.model.joint_names) - set(joint_names))
    non_movable_joint_indices = indexer(env, non_movable_joint_names)

    update_nv = np.zeros(env.model.nv, dtype=dtype)
    #for i, name in zip(non_movable_joint_indices, non_movable_joint_names):
    #    update_nv[i] = env._get_qpos(name)

    site_xpos = env.data.get_site_xpos(site)
    site_xmat = env.data.get_site_xmat(site).ravel()

    if target_quat is not None:
        neg_site_xquat = np.empty(4, dtype=dtype)
        err_rot_quat = np.empty(4, dtype=dtype)
        site_xquat = np.empty(4, dtype=dtype)

    if joint_names is None:
        dof_indices = slice(None)
    elif isinstance(joint_names, (list, np.ndarray, tuple)):
        if isinstance(joint_names, tuple):
            joint_names = list(joint_names)
        dof_indices = indexer(env, joint_names)


    steps = 0
    success = False

    for steps in range(max_steps):
        err_norm = 0.0

        if target_pos is not None:
            err_pos[:] = target_pos - site_xpos
           # print('steps=', steps, '   ', np.linalg.norm(err_pos))
            err_norm += np.linalg.norm(err_pos)

        if target_quat is not None:
            mjlib.mju_mat2Quat(site_xquat, site_xmat)
            mjlib.mju_negQuat(neg_site_xquat, site_xquat)
            mjlib.mju_mulQuat(err_rot_quat, target_quat, neg_site_xquat)
            mjlib.mju_quat2Vel(err_rot, err_rot_quat, 1)
            err_norm += np.linalg.norm(err_rot) * rot_weight


        if err_norm < tol:
            print('success')
            success =True
            break
        else:
            jac_pos = env.data.get_site_jacp(site).reshape((3, env.model.nv))
            jac_rot = env.data.get_site_jacr(site).reshape((3, env.model.nv))
            jac = np.concatenate((jac_pos, jac_rot))
            jac_joints = jac[:, dof_indices]

            # reg_strength later
            reg_strength = (
                regularization_strength if err_norm > regularization_threshold else 0.0
            )

            update_joints = nullspace_method(jac_joints, err, regularization_strength)
            update_norm = np.linalg.norm(update_joints)

            progress_criterion = err_norm / update_norm
            if progress_criterion > progress_thresh:
                print('halting')
                break

            if update_norm > max_update_norm:
                update_joints *= max_update_norm / update_norm

            update_nv[dof_indices] = update_joints

            env.set_state(env.sim.data.qpos+update_nv, env.sim.data.qvel.ravel())
            site_xpos = env._get_pos(site)
            site_xmat = env.data.get_body_xmat(site).ravel()
            if steps % 10 == 0:
                print('Step %2i: err_norm=%-10.3g update_norm=%-10.3g',
                      steps, err_norm)

    return IKResult(qpos = env.sim.data.qpos[dof_indices], err_norm=err_norm, steps=steps, success=success)





def nullspace_method(jac_joints, delta, regularization_strength=0.0):
    hess_approx = jac_joints.T.dot(jac_joints)
    joint_delta = jac_joints.T.dot(delta)
    if regularization_strength > 0:
        hess_approx += np.eye(hess_approx.shape[0]) * regularization_strength
        return np.linalg.solve(hess_approx, joint_delta)
    else:
        return np.linalg.lstsq(hess_approx, joint_delta, rcond=-1)[0]




