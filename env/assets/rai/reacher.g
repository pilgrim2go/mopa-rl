body joint0 {type=1 size=[0.011 0.011 0.11 0.011] pose=<T 0 0 0.01 0 0.70711 0 0.70711> color=[0.9 0.4 0.6]}
body link0 { type=cylinder size=[0 0 0.1 .005] contact color=[0 0.4 0.6] pose=<T 0 0 0 1 0 0 0>}

body joint1 { type=1 size=[1. 1. 0.1 .005] color=[0 0.4 0.6]}
body link1 { type=cylinder size=[0. 0. 0.1 .005] contact color=[0 0.4 0.6]}

body joint2 { type=1 size=[1. 1. 0 .005] color=[0 0.4 0.6]}
body link2 { type=cylinder size=[0. 0. 0.1 .005] contact color=[0 0.4 0.6]}

body joint3 { type=1 size=[0. 0. 1 .005] color=[0 0.4 0.6]}
body link3 { type=cylinder size=[0. 0. 0.1 .005] contact color=[0 0.4 0.6]}

body joint4 { type=1 size=[0. 0. 0 .005] color=[0 0.4 0.6]}
body link4 { type=cylinder size=[0. 0. 0.1 .005] contact color=[0 0.4 0.6]}


body joint5 { type=1 size=[0. 0. 0 .005] color=[0 0.4 0.6]}
body link5 { type=cylinder size=[0. 0. 0.1 .005] contact color=[0 0.4 0.6]}

body joint6 { type=1 size=[0. 0. 0 .005] color=[0 0.4 0.6]}
body link6 { type=cylinder size=[0. 0. 0.1 .005] contact color=[0 0.4 0.6]}

body endeff {type=1 size=[0. 0. 0. .005] color=[0 1 0.6]}
body goal { type=cylinder size=[0.07 0.07 0.002 .02] X=<T t(0.02195 -0.195 0.01) > color=[0.9 0.2 0.2]}

joint (joint0 link0) { type=hingeX,  limits=[ -3 3 ] from=<T 0 0 0 1 0 0 0> to=<T 0 0 0.05 1 0 0 0>  }
joint (link0 joint1) { type=rigid, from=<T t(0 0 0.05) > }
joint (joint1 link1) { type=hingeX,  limits=[ -3 3 ] from=<T 0 0 0 1 0 0 0> to=<T t(0 0 0.05) >  }
joint (link1 joint2) { type=rigid, from=<T t(0 0 0.05) > }
joint (joint2 link2) { type=hingeX,  limits=[ -3 3 ] from=<T 0 0 0 1 0 0 0> to=<T t(0 0 0.05) >  }
joint (link2 joint3) { type=rigid, from=<T t(0 0 0.05) > }
joint (joint3 link3) { type=hingeX, limits=[ -3 3 ] from=<T t(0 0 0)> to=<T t(0 0 0.05) >  }
joint (link3 joint4) { type=rigid, from=<T t(0 0 0.05) > }
joint (joint4 link4) { type=hingeX, limits=[ -3 3 ] from=<T t(0 0 0)> to=<T t(0 0 0.05) >  }
joint (link4 joint5) { type=rigid, from=<T t(0 0 0.05) > }
joint (joint5 link5) { type=hingeX, limits=[ -3 3 ] from=<T t(0 0 0)> to=<T t(0 0 0.05) >  }

joint (link5 joint6) { type=rigid, from=<T t(0 0 0.05) > }
joint (joint6 link6) { type=hingeX, limits=[ -3 3 ] from=<T t(0 0 0)> to=<T t(0 0 0.05) >  }
joint (link6 endeff) { type=rigid, from=<T t(-0 -0 0.05) > }


