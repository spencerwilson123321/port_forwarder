import pickle
from contextlib import contextmanager
import socket
import select
import ssl
import copyreg
import argparse
import sys
from multiprocessing import Process, Pipe
from server import Server
from os.path import exists

# Command Line Argument Parsing
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--server", dest="server", help="Server IP")
parser.add_argument("-p", "--port", dest="port", help="Server port number to listen on")
parser.add_argument("-m", "--multiprocess", dest="multiprocess", required=False, default=0, help="If this flag is present then the epoll server is run in multiprocessing mode. It expects an integer, representing the number"
                                                                                                 "of clients each process can maximally handle. I.e. -m 1000 means multiprocessing mode and create a process for every 1000 client"
                                                                                                 "connections.")
parser.add_argument("-l", "--log", dest="log", default=0, help="Acceptable values: 0 or 1. If 1 then the statistics will be logged to a file. Default value is 0 meaning do not log.", required=False)
args = parser.parse_args()

# Check ip and port are supplied.
if args.server is None or args.port is None:
    print(f"Invalid Arguments: use -h for list of accepted arguments. -s and -p flags must both be present.")
    sys.exit(0)

# Server Variables
ip = args.server
BUFF_SIZE = 1024
MAXCONN = 100000

# Check that LOG is an integer.
try:
    LOG = int(args.log)
except ValueError:
    print(f"Invalid Argument Type: -l flag expects an Integer (1 or 0). Use -h for list of accepted arguments.")
    sys.exit(0)

# Check that log is equal to 1 or 0.
if LOG != 0:
    if LOG != 1:
        print(f"Invalid Argument Type: -l flag expects 1 or 0. Use -h for list of accepted arguments.")
        sys.exit(0)

# Check that ip is a valid IP address string.
parts = ip.split('.')
if len(parts) != 4:
    print(f"Invalid Argument Type: -s flag expects a valid IP address. Use -h for list of accepted arguments.")
    sys.exit(0)
for num in parts:
    try:
        int(num)
    except ValueError:
        print(f"Invalid Argument Type: -s flag expects a valid IP address. Use -h for list of accepted arguments.")
        sys.exit(0)
try:
    socket.inet_aton(ip)
except socket.error:
    print(f"Invalid Argument Type: -s flag expects an IP address. Use -h for list of accepted arguments.")
    sys.exit(0)

# Check that port is valid argument.
try:
    port = int(args.port)
except ValueError:
    print(f"Invalid Argument Type: -p flag expects an Integer. Use -h for list of accepted arguments.")
    sys.exit(0)

# Check that multiprocessing flag is an integer.
if args.multiprocess == 0:
    NUM_CLIENTS_PER_PROCESS = 1000000
else:
    try:
        NUM_CLIENTS_PER_PROCESS = int(args.multiprocess)
    except ValueError:
        print(f"Invalid Argument Type: -m flag expects an Integer. Use -h for list of accepted arguments.")
        sys.exit(0)


# This is the main server function which takes the server address as arguments.
# address should be a tuple in the form (string, int) --> (ip, port)
def main_process(address):
    try:
        # Using context to create the listening socket and that is wrapped into an epoll object.
        with socket_context() as server, epoll_context(server.fileno(), select.EPOLLIN) as epoll:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(address)
            server.listen(MAXCONN)
            print(f"Listening on {address}...")
            server.setblocking(0)
            server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            #Create SSL context
            context = ssl.SSLContext()
            context.load_cert_chain('./server.cert', './server_priv.key')
            context.load_verify_locations(capath='./cacert.pem')
            #Wrap socket in context.
            # server = context.wrap_socket(sock=server, server_side=True)
            server_sd = server.fileno()
            # Process and Pipe List
            process_list = []
            pipe_list = []

            # Pre-allocating 10 processes which will be able to handle many clients each in parallel.
            for x in range(0, 10):
                s = Server()
                parent, child = Pipe()
                p = Process(target=s.start_server, args=(child,))
                process_list.append(p)
                pipe_list.append(parent)
            num_clients = 0
            num_processes = 0

            # Check for new connections.
            while True:
                events = epoll.poll(1)
                for sd, event in events:
                    if sd == server_sd:
                        conn, addr = server.accept()
                        conn.setblocking(0)
                        print("Listening Socket --> Client connected: ", addr)
                        if num_clients != 0:
                            if num_clients % NUM_CLIENTS_PER_PROCESS != 0:
                                pipe_list[num_processes].send(conn)
                            if num_clients % NUM_CLIENTS_PER_PROCESS == 0:
                                num_processes = num_processes + 1
                                process_list[num_processes].start()
                                pipe_list[num_processes].send(conn)
                        if num_clients == 0:
                            process_list[num_processes].start()
                            pipe_list[num_processes].send(conn)
                        num_clients = num_clients + 1
    except KeyboardInterrupt:
        process_data = []
        for process in process_list:
            if process.is_alive():
                process.join()
        if num_processes == 0:
            data = pipe_list[num_processes].recv()
            generate_single_process_statistics(data)
        else:
            for x in range(0, num_processes+1):
                data = pipe_list[x].recv()
                process_data.append(data)
            generate_multiprocess_statistics(process_data)


def generate_single_process_statistics(data):
    print(f"Statistics:\n"
          f"\tTotal bytes sent to clients: {int(data[0])}\n"
          f"\tAverage bytes sent to each client: {int(data[1])}\n"
          f"\tAverage number of requests from each client: {int(data[2])}")
    if LOG:
        if exists('./server_log_single_process.txt'):
            with open('./server_log_single_process.txt', 'a', encoding='utf-8') as log:
                log.write(f"{int(data[0])} {int(data[1])} {int(data[2])}\n")
        else:
            with open('./server_log_single_process.txt', 'a', encoding='utf-8') as log:
                log.write(f"total_bytes avg_bytes avg_requests\n")
                log.write(f"{int(data[0])} {int(data[1])} {int(data[2])}\n")


def generate_multiprocess_statistics(process_data):
    total_data_sent = 0
    average_data_sent_list = []
    average_data_sent = 0
    average_num_requests_list = []
    average_num_requests = 0
    for data in process_data:
        total_data_sent += data[0]
        average_data_sent_list.append(data[1])
        average_num_requests_list.append(data[2])
    for num in average_num_requests_list:
        average_num_requests += num
    average_num_requests = int(average_num_requests / len(average_num_requests_list))
    for num in average_data_sent_list:
        average_data_sent += num
    average_data_sent = int(average_data_sent / len(average_data_sent_list))
    print(f"Statistics:\n"
          f"\tTotal bytes sent to clients: {total_data_sent}\n"
          f"\tAverage bytes sent to each client: {average_data_sent}\n"
          f"\tAverage number of requests from each client: {average_num_requests}")
    if LOG:
        if exists('./server_log_multi_process.txt'):
            with open('./server_log_multi_process.txt', 'a', encoding='utf-8') as log:
                log.write(f"{total_data_sent} {average_data_sent} {average_num_requests}\n")
        else:
            with open('./server_log_multi_process.txt', 'a', encoding='utf-8') as log:
                log.write(f"total_bytes avg_bytes avg_requests\n")
                log.write(f"{total_data_sent} {average_data_sent} {average_num_requests}\n")


@contextmanager
def socket_context():
    sd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        yield sd
    finally:
        print("Listening socket closed")
        sd.close()


@contextmanager
def epoll_context(sd, event):
    eps = select.epoll()
    eps.register(sd, event)
    try:
        yield eps
    finally:
        print("epoll loop exiting")
        eps.unregister(sd)
        eps.close()


try:
    main_process((ip, port))
except KeyboardInterrupt:
    pass







