import argparse
import tools
import os
import communication
import time
import json
import sys
import pdb

class Experiment:

    experiment = None

    def __init__(self, add_new_experiment, config='', print_output_if_have_error=False, print_output=False):

        self.print_output_if_have_error = print_output_if_have_error
        self.print_output = print_output
        self.servers = []

        if add_new_experiment:

            communication.insert_experiment(
                comment='',
                scheduler_algorithm='',
                config=config
            )

            tools.log("Create new experiment.")

        Experiment.experiment = communication.Communication.get_current_experiment()

        if Experiment.experiment is not None:
            tools.log("Experiment id: %s" % str(Experiment.experiment["id"]))

        nova = tools.get_nova_client()
        for server in nova.servers.list():
            # pdb.set_trace()
            if server.status != 'ACTIVE':
                continue

            try:
                server_ip = server.networks['provider'][0]

                if server_ip == '10.18.75.182':
                    continue

                tools.log("Connecting via ssh to %s" % (server_ip))

                ssh_client = Experiment._create_ssh_clients(server_ip)

                self.servers.append({
                    "id": server.id,
                    "ssh": ssh_client,
                    "ip": server_ip,
                    "name": server.name
                })

            except Exception as ex:
                tools.log("Error -> canot create SSH client for %s\nError message -> %s"
                          % (server_ip, ex.message))

    def close_all_ssh_client(self):

        for server in self.servers:

            ssh_client = server["ssh"]
            ssh_client.close()

    def initialize_commands(self):

        for server in self.servers:

            ret = self._run_command(server, "ls ~")

            if "fio-2.0.9\n" not in ret["out"]:
                self._run_command(server, "sudo wget https://github.com/Crowd9/Benchmark/raw/master/fio-2.0.9.tar.gz")
                self._run_command(server, "sudo tar xf ~/fio-2.0.9.tar.gz")
                self._run_command(server, "sudo make -C ~/fio-2.0.9")

            ret = self._run_command(server, "sudo cat /etc/hosts")
            if server["name"] not in str(ret["out"]):
                self._run_command(
                    server,
                    "echo '%s\t%s' | sudo tee --append /etc/hosts" % (server["ip"], server["name"]))


            self._run_command(server, "sudo rm -r -d ~/MLSchedulerAgent/")
            ret = self._run_command(server, 'sudo git clone https://github.com/bravandi/MLSchedulerAgent.git')
            if ret["retval"] == 128:
                self._run_command(server, "sudo git -C ~/MLSchedulerAgent/ reset --hard; sudo git -C ~/MLSchedulerAgent/ pull")

            self._run_command(server, "sudo echo '%s' > ~/tenantid" % server["id"])

            self._run_command(server, "sudo echo '%s@%s' > ~/tenant_description" % (server["name"], server["ip"]))

            self._run_command(server, "sudo mkdir /media/")

    def _run_command(self, server, command):

        if self.print_output:
            print ("{EXECUTE %s} %s\n" % (server["ip"], command))

        ret = server["ssh"].execute(command)

        if (not self.print_output) and self.print_output_if_have_error and ret["retval"] > 0:
            print ("{EXECUTED %s} %s\n" % (server["ip"], command))
            print ("     [RESPONSE %s] OUT: %s\n     RETVAL:%s   ERR:%s \n" %
                   (server["ip"], ret["out"], ret["retval"], ret["err"]))

        if self.print_output:
            print ("     [RESPONSE %s] OUT: %s\n     RETVAL:%s   ERR:%s \n" %
                   (server["ip"], ret["out"], ret["retval"], ret["err"]))

        return ret

    def start_workload_generators(self, arguments):

        args = []
        for k, v in arguments.iteritems():
            args.append(str(k))
            args.append(str(v))

        self._run_command_on_all_servers("sudo nohup python ~/MLSchedulerAgent/workload_generator.py start %s >~/workload.out 2>~/workload.err &" % (" ".join(args)))

    def start_performance_evaluators(self, arguments):

        args = []
        for k, v in arguments.iteritems():
            args.append(str(k))
            args.append(str(v))

        self._run_command_on_all_servers(
            "sudo nohup python ~/MLSchedulerAgent/performance_evaluation.py %s >~/performance_evaluation.out 2>~/performance_evaluation.err &" % (" ".join(args)))


    def kill_performance_evaluators(self):
        self._run_command_on_all_servers(
            "ps -ef | grep performance_evaluation | grep -v grep | awk '{print $2}' | xargs sudo kill -9")

    def kill_workload_generator_all_servers(self):
        self._run_command_on_all_servers(
            "ps -ef | grep workload_generator | grep -v grep | awk '{print $2}' | xargs sudo kill -9")

    def _run_command_on_all_servers(self, command):
        for server in self.servers:
            self._run_command(server, command)

    def detach_delete_all_servers_volumes(self):
        self._run_command_on_all_servers("sudo nohup python ~/MLSchedulerAgent/workload_generator.py det-del >~/detach_delete_all_servers_volumes.out 2>~/detach_delete_all_servers_volumes.err &")

    @staticmethod
    def _create_ssh_clients(server_ip):
        f = open(
            os.path.join(
                os.path.expanduser('~'),
                "keys",
                "vm-test",
                "vm-test.pem"
            ), 'r')

        s = f.read()

        client = tools.SshClient(
            host=server_ip,
            port=22,
            key=s,
            username='ubuntu',
            password='')

        return client

if __name__ == '__main__':

    # todo ******* run python experiment.py execute --command "sudo mkdir /media" on the other servers that you shut down
    # todo when create new server make sure dependecies such as numpy are installed -->python experiment.py execute --command "pip install numpy"


    parser = argparse.ArgumentParser(description='Manage experiments.')

    parser.add_argument('commands', type=str, nargs="+",
                        choices=[
                            'start', 'shutdown', 'start-new', 'workload', 'del-avail-err',
                            'performance', 'det-del', 'kill-workload',
                            'kill-performance', 'execute', 'init', 'create-experiment'],
                        help=
"""
Manage experiments.
"""
                        )

    parser.add_argument('--new', default=False, metavar='', type=bool,
                        required=False,
                        help='Create new experiment otherwise the last created experiment will be used.')

    parser.add_argument('--is_training', default=False, metavar='', type=bool, required=False,
                        help='training will use the default scheduler.')

    parser.add_argument('--command', metavar='', type=str,
                        required=False,
                        help='Command that needs to be executed.')

    parser.add_argument("--max_number_volumes", default=6, metavar='', type=int,
                        required=False,
                        help='max number of volumes each worklaod generator creates')

    args = parser.parse_args()

    if "shutdown" in args.commands:
        args.commands = ["kill-workload", "kill-performance", "det-del"]

    if "start" in args.commands:
        args.commands = ["init", "workload", "performance"]

    if "start-new" in args.commands:
        args.commands = ["init", "workload", "performance"]
        args.new = True

    if "create-experiment" in args.commands:
        args.new = True

    workload_args = {
        "--fio_test_name": "workload_generator.fio",
        '--delay_between_workload_generation': 8,
        "--max_number_volumes": args.max_number_volumes,
        "--volume_life_seconds": 500,
        "--volume_size": 9
    }

    performance_args = {
        "--fio_test_name": "resource_evaluation.fio",
        "--terminate_if_takes": 175,
        "--restart_gap": 25,
        "--restart_gap_after_terminate": 50,
        "--show_fio_output": False,
    }

    if "del-avail-err" in args.commands:
        tools.delete_volumes_available_error()

        sys.exit()

    e = Experiment(
        add_new_experiment=args.new,
        print_output_if_have_error=True,
        print_output=True,
        config=json.dumps({
            "is_training": args.is_training,
            "workload_args": workload_args,
            "performance_args": performance_args,
            "mod_normalized_clock_for_feature_generation": 180,
            "training_dataset_size": 500,
            "volume_clock_calc":
"""
def volume_clock_calc(t):
    return t.strftime("%s")
""",
            "volume_performance_meter_clock_calc":
"""
def volume_performance_meter_clock_calc(t):
    if(t.second > 30):
        t = t.replace(second=30)
    else:
        t = t.replace(second=0)
    t = t.replace(microsecond=0)
    return t.strftime("%s")
"""
        })
    )

    if "init" in args.commands:
        e.initialize_commands()

    if "workload" in args.commands:
        e.start_workload_generators(workload_args)

    if "performance" in args.commands:
        e.start_performance_evaluators(performance_args)

    if "kill-performance" in args.commands:
        e.kill_performance_evaluators()

    if "kill-workload" in args.commands:
        e.kill_workload_generator_all_servers()

        #sleep 4 to make sure all the processes are dead are not going to create new volumes!
        if "det-del" in args.commands:
            time.sleep(4)

    if "det-del" in args.commands:
        e.detach_delete_all_servers_volumes()
        # tools.delete_volumes_available_error()

    if "execute" in args.commands:
        e._run_command_on_all_servers(args.command)

    e.close_all_ssh_client()
