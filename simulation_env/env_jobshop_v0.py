#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
##----- Job shop SL for RL Environment ------
# * Author: Colin, Lee
# * Date: Aug 16th, 2021
##-------------------------------------------
#
import os
import sys
if '..' not in sys.path:
    sys.path.append('..')

import time
import simpy
import numpy             as np
import pandas            as pd
import matplotlib.pyplot as plt

from matplotlib.animation import FuncAnimation
from utils.GanttPlot      import Gantt

INFINITY  = float('inf')
OPTIMAL_L = 55
ACTION    = 10 #5

#entity
class Order:
    def __init__(self, id, routing, prc_time, rls_time, intvl_arr):
        # *prc_time: process time, *rls_time: release time, *intvl_arr: arrival_interval
        self.id        = id
        self.routing   = routing
        self.prc_time  = prc_time
        self.rls_time  = rls_time
        self.intvl_arr = intvl_arr

        self.progress = 0

    def __str__(self):
        return f'Order #{self.id}'


#resource in factory
class Source:
    def __init__(self, fac, order_info = None):
        #reference
        self.fac = fac
        #attribute
        self.order_info  = order_info
        self.orders_list = []
        #statistics
        self.num_generated = 0

    def set_port(self):
        #reference
        self.env    = self.fac.env
        self.queues = self.fac.queues

        #initial process
        self.process = self.env.process(self._generate_order())

    def _generate_order(self):
        #get the data of orders
        self.order_info = self.order_info.sort_values(by='release_time')
        num_order       = self.order_info.shape[0]

        _orders_list = []

        #generate instances of Order from order information
        for num in range(num_order):
            id        = self.order_info.loc[num, "id"]
            routing   = self.order_info.loc[num, "routing"].split(',')
            prc_time  = [int(i) for i in self.order_info.loc[num, "process_time"].split(',')]
            rls_time  = self.order_info.loc[num, "release_time"]
            intvl_arr = self.order_info.loc[num, "arrival_interval"]

            _order    = Order(id, routing, prc_time, rls_time, intvl_arr)

            _orders_list.append(_order)

            #wait for inter-arrival time
        for num in range(num_order):
            #TO decide which order arrive first
            indx       = np.argmin([o.prc_time[0] for o in _orders_list])
            order      = _orders_list[indx]
            intvl_time = order.intvl_arr
            _orders_list.remove(order)

            yield self.env.timeout(intvl_time)
            #log for tracing
            if self.fac.log:
                print("  ({}) order {} release.".format(self.env.now, order.id))
            #send order to queue
            target = int(order.routing[order.progress])
            self.queues[target].order_arrive(order)
            #update statistics
            self.num_generated += 1


#################
#    TO DO:     
#################
#An actor to execute the action
class Dispatcher:
    def __init__(self, fac):
        self.fac = fac
        self.env = fac.env

    def dispatch_by(self, action):
        if action == 0:
            dspch_rule = 'FIFO'
        elif action == 1:
            dspch_rule = 'LIFO'
        elif action == 2:
            dspch_rule = 'SPT'
        elif action == 3:
            dspch_rule = 'LPT'
        elif action == 4:
            dspch_rule = 'TWKR'
        elif action == 5:
            dspch_rule = 'MWKR'
        elif action == 6:
            dspch_rule = 'SSO'
        elif action == 7:
            dspch_rule = 'LSO'
        elif action == 8:
            dspch_rule = 'SPT+SSO'
        elif action == 9:
            dspch_rule = 'LPT+LSO'
        # elif action == 9:
        #     dspch_rule = 'STPT' #shortest total processing time
        # elif action == 10:
        #     dspch_rule = 'LTPT' #longest total processing time

        #set the dispatch rule of each queue
        for _, queue in self.fac.queues.items():
            queue.dspch_rule = dspch_rule


class Queue:
    def __init__(self, fac, id):
        #reference
        self.fac     = fac
        self.env     = self.fac.env
        #attribute
        self.id         = id
        self.space      = []
        self.dspch_rule = None

    def __str__(self):
        return f'queue #{self.id}'

    def set_port(self):
        #reference
        self.machine = self.fac.machines[self.id]

    def order_arrive(self, order):
        machine_idle  = self.machine.status == 'idle'
        none_in_space = len(self.space) == 0
        if machine_idle and none_in_space:
            self.machine.process_order(order)
        else:
            self.space.append(order)

    #################
    #    TO DO:     
    #################
    #A way to pause simulation and resume after the actor take an action
    def check_obs_point(self):
        machine_idle  = self.machine.status == 'idle'
        if machine_idle and len(self.space) > 0:

            self.fac.obs_point.succeed()
            self.fac.mc_need_dspch.add(self.id)

            self.fac.obs_point = self.env.event()

            self.fac.dict_dspch_evt[self.id] = self.env.event()
            self.env.process(self.get_order())

    def get_order(self):
        if len(self.space) > 0:
            yield self.fac.dict_dspch_evt[self.id]

            #################
            #    TO DO:     
            #################
            #set an event for resuming after receive an action
            self.fac.dict_dspch_evt[self.id] = self.env.event()
            #get oder in queue
            if self.dspch_rule == 'FIFO':
                order = self.space[0]
            elif self.dspch_rule == 'LIFO':
                order = self.space[-1]
            elif self.dspch_rule == 'SPT':
                indx  = np.argmin([order.prc_time[order.progress] for order in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'LPT':
                indx  = np.argmax([order.prc_time[order.progress] for order in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'LWKR':
                indx  = np.argmin([sum(ord.prc_time[ord.progress:]) for ord in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'MWKR':
                indx  = np.argmax([sum(ord.prc_time[ord.progress:]) for ord in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'SSO':
                indx  = np.argmin([order.prc_time[order.progress+1] for order in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'LSO':
                indx  = np.argmax([order.prc_time[order.progress+1] for order in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'SPT+SSO':
                indx  = np.argmin([sum(ord.prc_time[ord.progress:ord.progress+2]) for ord in self.space])
                order = self.space[indx]
            elif self.dspch_rule == 'LPT+LSO':
                indx  = np.argmax([sum(ord.prc_time[ord.progress:ord.progress+2]) for ord in self.space])
                order = self.space[indx]
            else:
                raise "[ERROR #1]"
                # elif self.dspch_rule == 'STPT':
                #     indx  = np.argmin([sum(order.prc_time) for order in self.space])
                # elif self.dspch_rule == 'LTPT':
                #     indx  = np.argmax([sum(order.prc_time) for order in self.space])

            
            #send order to machine
            self.machine.process_order(order)
            #remove order form queue
            self.space.remove(order)


class Machine:
    def __init__(self, fac, id, num = 1):
        self.fac = fac
        self.id  = id
        self.num = num
        self.processing = None
        #reference
        self.env    = self.fac.env
        #attributes
        self.status = "idle"
        #statistics
        self.using_time = 0

    def __str__(self):
        return f'machine #{self.id}'

    def set_port(self):
        #reference
        self.queues = self.fac.queues
        self.sink   = self.fac.sink

    #################
    #    TO DO:     
    #################
    #update the information which is state-related
    def process_order(self, order):
        #change status
        self.status = order
        #process order
        if self.fac.log:
            print("  ({}) machine {} start processing order {} - {} progress".format(self.env.now, self.id, order.id, order.progress))

        #################
        #    TO DO:     
        #################
        #update the table of process status(progess matrix)
        self.fac.tb_proc_status[order.id - 1][order.progress] = 1

        #[Gantt plot preparing] udate the start/finish processing time of machine
        prc_time = order.prc_time[order.progress]
        self.fac.gantt_plot.update_gantt(self.id, self.env.now, prc_time, order.id)

        #do the action about processing
        self.process = self.env.process(self._process_order_callback())

    #################
    #    TO DO:     
    #################
    #check observation point if there is any idle machine
    def _process_order_callback(self):
        #processing order for prc_time mins
        order    = self.status
        prc_time = order.prc_time[order.progress]
        #[Gantt plot preparing] udate the start/finish processing time of machine
        self.fac.gantt_plot.update_gantt(self.id, self.env.now, prc_time, order.id)

        yield self.env.timeout(prc_time)
        if self.fac.log:
            print("  ({}) machine {} finish processing order {} - {} progress".format(self.env.now, self.id, order.id, order.progress))
        #change order status
        order.progress += 1
        #send order to next station
        if order.progress < len(order.routing):
            target = int(order.routing[order.progress])
            self.queues[target].order_arrive(order)
        else:
            self.sink.complete_order(order)

        #change status
        self.using_time += prc_time
        self.status      = "idle"

        #################
        #    TO DO:     
        #################
        #get next order in queue
        terminal_is_true = self.fac.terminal.triggered
        if terminal_is_true:
            self.fac.obs_point.succeed()
        else:
            for queue in self.queues.values():
                queue.check_obs_point()


class Sink:
    def __init__(self, fac):
        self.fac = fac

    def set_port(self):
        #reference
        self.env = self.fac.env
        #attribute
        #statistics
        self.order_statistic = pd.DataFrame(columns =
                                            ["id", "release_time", "complete_time", "flow_time"]
                                            )

    #################
    #    TO DO:     
    #################
    #define the terminal condition
    def complete_order(self, order):
        #update factory statistic
        self.fac.throughput += 1
        #update order statistic
        self.update_order_statistic(order)

        #################
        #    TO DO:     
        #################
        #ternimal condition
        num_order = self.fac.order_info.shape[0]
        if self.fac.throughput >= num_order:
            self.fac.terminal.succeed()
            self.fac.makespan = self.env.now

    def update_order_statistic(self, order):
        id            = order.id
        rls_time      = order.rls_time
        complete_time = self.env.now
        flow_time     = complete_time - rls_time

        self.order_statistic.loc[id] = \
        [id, rls_time, complete_time, flow_time]


#factory
class Factory:
    '''
    A SimPy job-shop simulation which present a familiar OpenAI Gym like interface
       for Reinforcement Learning.

    Any environment needs:
    * A way to pause simulation and resume after the actor take an action
    * A state space
    * A reward function
    * An initialize (reset) method that returns the initial observations
    * A choice of actions
    * A islegal method to make sure the action is possible and legal
    * A step method that passes an action into the environment and returns:
        1. new observations as state
        2. reward
        3. whether state is terminal
        4. additional information
    * A render method to refresh and display the environment.
    * A way to recognize and return a terminal state (end of episode)

    -----------------
    Internal methods:
    -----------------
    __init__:
        Constructor method.
    _get_observation:
        Gets current state observations
    _islegal:
        Checks whether requested action is legal
    _pass_action:
        Execute the action to change the status of system
    _get_reward:
        Calculates reward based on empty beds or beds without patient


    Interfacing methods:
    --------------------
    render:
        Display state
    reset:
        Initialise environment
        Return first state observations
    step:
        Take an action. Update state. Return obs, reward, terminal, info

    '''
    def __init__(self, num_job, num_machine, file_name, opt_makespan, log=False):
        self.log        = log

        #statistics
        self.throughput = 0
        self.last_util  = 0
        self.makespan   = INFINITY

        #system config
        self.num_machine    = num_machine
        self.num_job        = num_job
        self.order_info     = pd.read_excel(file_name)
        self.df_machine_no  = pd.read_excel(file_name, sheet_name='machine_no')
        self.df_proc_times  = pd.read_excel(file_name, sheet_name='proc_time')
        self.tb_proc_status = np.zeros((num_job, num_machine))
        self.opt_makespan   = opt_makespan

        #[Gantt]
        self.gantt_plot = Gantt()

        #[RL] attributes for the Environment of RL
        self.dim_actions      = ACTION
        self.dim_observations = (3, self.num_job, self.num_job)
        self.observations     = np.zeros(self.dim_observations)
        self.actions          = np.arange(self.dim_actions)

        from gym import spaces
        self.action_space = spaces.Discrete(self.dim_actions)

        self.observations[0] = self.df_machine_no.values
        self.observations[1] = self.df_proc_times.values
        self.observations[2] = self.tb_proc_status

        #display        
        self._render_his = []

    def build(self):
        #build
        self.env        = simpy.Environment()
        self.source     = Source(self, self.order_info)
        self.dispatcher = Dispatcher(self)
        self.queues     = {}
        self.machines   = {}
        self.sink       = Sink(self)
        for num in range(self.num_machine):
            self.queues[num]   = Queue(self, num)
            self.machines[num] = Machine(self, num)
        #make connection
        self.source.set_port()
        for num, queue in self.queues.items():
            queue.set_port()
        for num, machine in self.machines.items():
            machine.set_port()
        self.sink.set_port()

        #dispatch event which would be successed when the mc finished dispatching
        self.dict_dspch_evt = {}
        self.mc_need_dspch  = set()
        for num in range(self.num_machine):
            self.dict_dspch_evt[num] = self.env.event()

        #terminal event
        self.terminal   = self.env.event()

    def get_utilization(self):
        #compute average utiliztion of machines
        total_using_time = 0
        for _, machine in self.machines.items():
            total_using_time += machine.using_time

        avg_using_time = total_using_time / self.num_machine
        return avg_using_time / self.env.now

    def _islegal(self, action):
        """
        Check action is in list of allowed actions. If not, raise an exception.
        """

        if action not in self.actions:
            _msg = f'Requested action -->{action},not in the action space'
            raise ValueError(_msg)

    def _pass_action(self, action):
        #to execute the action
        self.dispatcher.dispatch_by(action)
        for mc in self.mc_need_dspch:
            if mc != None:
                self.dict_dspch_evt[mc].succeed()
        self.mc_need_dspch = set()

    def _get_observations(self):
        self.observations[0] = self.df_machine_no.values
        self.observations[1] = self.df_proc_times.values
        self.observations[2] = self.tb_proc_status
        return self.observations.copy()

    def _get_reward(self):
        current_util = self.get_utilization()
        last_util    = self.last_util
        reward       = (current_util - last_util)

        #final state
        if self.terminal:
            makespan = self.makespan
            optimal  = self.opt_makespan
            if makespan == optimal:
                reward += 100
            else:
                reward += 100 / (makespan - optimal)
        
        #record current utilization as last utilization
        self.last_util = current_util
        return reward

    def render(self, terminal=False, human_cntrl=False, motion_speed=0.1):
        plt.set_loglevel('WARNING') 
        if human_cntrl:
            if len(self._render_his) % 3 == 0:
                plt.ioff()
                plt.close('all')
            # queues_status = {}
            # for id, queue in self.queues.items():
                # queues_status[id] = [str(order) for order in queue.space]
            # print(f'\n (time: {self.env.now}) - Status of queues:\n {queues_status}')
            plt.ion()
            plt.pause(motion_speed)
            fig = self.gantt_plot.draw_gantt(self.env.now)
            self._render_his.append(fig)

            if terminal:
                plt.ioff()
                trm_frame = [plt.close(fig) for fig in self._render_his[:-1]]
                plt.show()
        else:
            if terminal:
                plt.ion()
                fig = self.gantt_plot.draw_gantt(self.env.now)
                plt.pause(motion_speed)
                # plt.ioff()
                # plt.show()
    
    def close(self):
        plt.ioff()
        plt.close('all')

    def reset(self):
        #re-build factory include re-setting the events
        self.build()

        #display
        self._render_his = []

        #reset statistics
        self.throughput = 0
        self.last_util  = 0
        self.makespan   = INFINITY

        #get initial observations
        observations = self._get_observations()

        return observations

    def step(self, action):

        #execute the action
        self._islegal(action)
        self._pass_action(action)

        #Resume to simulate until next observation_point(pause)
        self.obs_point = self.env.event()
        self.env.run(until = self.obs_point)

        #get new observations
        observations = self._get_observations()

        #get reward
        reward = self._get_reward()

        #ternimal condition
        terminal = self.terminal.triggered

        info = {}

        return observations, reward, terminal, info


if __name__ == '__main__':
    import time
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows'   , None)
    pd.set_option('display.width'      , 300)
    pd.set_option('max_colwidth'       , 100)

    human_control   = str(input('\n* Human control [y/n]? '))
    usr_interaction = False
    if human_control == 'y':
        usr_interaction = True

    replication = 3

    # read problem config
    opt_makespan = 55
    file_name    = 'job_info.xlsx'
    file_dir     = os.getcwd() + '/input_data'
    file_path    = os.path.join(file_dir, file_name)

    for rep in range(replication):
        # make environment
        fac = Factory(6, 6, file_path, opt_makespan, log=False)
        print(f'Rep #{rep}')
        print('* Order Information: ')
        print(fac.order_info)
        print('')

        state = fac.reset() #include the bulid function
        done  = False
        # print(f'({fac.env.now})')
        # print(f'[{state[-1]}]')
        # print()
        fac.render(done)
        while not done:

            if not usr_interaction:
                action = rep % fac.dim_actions #1
            else:
                action = int(input(' * Choose an action from {0,1}: '))

            next_state, reward, done, _ = fac.step(action)
            # print(f'({fac.env.now})')
            # print(f'[{state[-1]},\n {action}, {reward},\n {next_state[-1]}]')
            # print()
            state = next_state

            fac.render(terminal=done, human_cntrl=usr_interaction)

        
        # fac.render(done)
        time.sleep(0.5)
        fac.close()

        # print(fac.event_record)
        print("============================================================")
        print(fac.sink.order_statistic.sort_values(by = "id"))
        print("============================================================")
        print("Average flow time: {}".format(np.mean(fac.sink.order_statistic['flow_time'])))
        print("Makespan = {}".format(fac.makespan))
