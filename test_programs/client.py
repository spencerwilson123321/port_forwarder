#!/usr/bin/python3.9
import argparse
import socket
import ssl
from os.path import exists
import time
import threading
from threading import Lock
import sys

# Command Line Argument Parsing
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--server", dest="server", help="Server IP address", required=True)
parser.add_argument("-p", "--port", dest="port", help="Server port number", required=True)
parser.add_argument("-b", "--bytes", dest="bytes", help="Number of bytes to send to the server.", required=True)
parser.add_argument("-c", "--clients", dest="clients", help="Number of client threads to create.", required=True)
parser.add_argument("-l", "--log", dest="log", default=0,
                    help="Acceptable values: 0 or 1. If 1 then the statistics will be logged to a file. Default value is 0 meaning do not log.",
                    required=False)
args = parser.parse_args()

# Check ip and port are supplied.
if args.server is None or args.port is None:
    print(f"Invalid Arguments: use -h for list of accepted arguments. -s and -p flags must both be present.")
    sys.exit(0)

# Check that ip is a valid IP address string.
ip = args.server
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

# Check that LOG is an integer.
try:
    LOG = int(args.log)
except ValueError:
    print(f"Invalid Argument Type: -l flag expects an Integer (1 or 0). Use -h for list of accepted arguments.")
    sys.exit(0)

# Check that port is valid argument.
try:
    port = int(args.port)
except ValueError:
    print(f"Invalid Argument Type: -p flag expects an Integer. Use -h for list of accepted arguments.")
    sys.exit(0)

# Check that log is equal to 1 or 0.
if LOG != 0:
    if LOG != 1:
        print(f"Invalid Argument Type: -l flag expects 1 or 0. Use -h for list of accepted arguments.")
        sys.exit(0)

server = (ip, port)
BUFF_SIZE = 1024
avg_response_time_list = set()
avg_response_time_of_clients = 0
avg_connection_time = 0
connection_time_list = set()
request_list = set()
avg_requests = 0
avg_bytes_sent = 0
total_bytes_sent = 0
bytes_sent_list = []
lock = Lock()
try:
    num_bytes = int(args.bytes)
except ValueError:
    print(f"Invalid Argument Type: -b expects an Integer. Use -h for list of accepted arguments.")
    sys.exit(0)
try:
    num_clients = int(args.clients)
except ValueError:
    print(f"Invalid Argument Type: -c expects an Integer. Use -h for list of accepted arguments.")
    sys.exit(0)


def calc_avg(list):
    sum = 0
    size = len(list)
    if size == 0:
        return -1
    for num in list:
        sum += num
    avg = sum / size
    return avg


def client_func(bytes_to_send, sock):
    conn_time_start = time.time()
    bytes_received = 0
    bytes_sent = 0
    response_times = set()
    num_requests = 0
    while bytes_received < bytes_to_send:
        data = b'a' * BUFF_SIZE
        send_time = time.time()
        bytes_sent += sock.send(data)
        num_requests = num_requests + 1
        try:
            response = sock.recv(BUFF_SIZE)
            recv_time = time.time()
            response_times.add(recv_time - send_time)
        except ConnectionResetError:
            print("Socket disconnected")
            sock.close()
            break
        except TimeoutError:
            print("Socket disconnected")
            sock.close()
            break
        bytes_received += len(response)
    conn_time_end = time.time()
    avg_response_time = calc_avg(response_times)
    # Send the client specific statistics to the main thread,
    # so that it can compile the results.
    lock.acquire()
    request_list.add(num_requests)
    connection_time_list.add(conn_time_end - conn_time_start)
    if avg_response_time != -1:
        avg_response_time_list.add(avg_response_time)
    bytes_sent_list.append(bytes_sent)
    lock.release()


sock_list = []
thread_list = []
unable_to_connect = 0

# Creating SSL Context.
context = ssl.SSLContext()
context.load_cert_chain(certfile="./cacert.pem", keyfile="./cakey.pem", password="password")
context.load_verify_locations(capath='./cacert.pem')

connection_time_start = time.time()
print("Creating client sockets and connecting to server...")
for x in range(0, num_clients):
    try:
        sock = socket.create_connection(server, timeout=60)
        sock = context.wrap_socket(sock=sock, do_handshake_on_connect=False, server_side=False)
    except OSError:
        unable_to_connect = unable_to_connect + 1
        continue
    sock.settimeout(120)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_list.append(sock)
print("Creating thread pool...")
for sock in sock_list:
    thread_list.append(threading.Thread(target=client_func, args=(num_bytes, sock)))
print(f"{len(thread_list)} threads created.")
for sock in sock_list:
    sock.do_handshake()
connection_time_end = time.time()
connection_time = connection_time_end - connection_time_start
input(f"To begin sending data, press the enter key.")
print("Starting threads...")
transmission_time_start = time.time()
for thread in thread_list:
    thread.start()
for thread in thread_list:
    thread.join()
transmission_time_end = time.time()
transmission_time = transmission_time_end - transmission_time_start

for sock in sock_list:
    sock.close()

# Main thread calculates the average of the average response times of each client.
avg_response_time_of_clients = calc_avg(avg_response_time_list)
avg_bytes_sent = calc_avg(bytes_sent_list)
total_bytes_sent = sum(bytes_sent_list)
avg_connection_time = calc_avg(connection_time_list)
avg_requests = calc_avg(request_list)

print(f"{len(thread_list)} threads finished\n"
      f"{len(sock_list)} sockets closed.")
print(f"Statistics:\n\t"
      f"Total time to connect {len(sock_list)} clients to server: {format(connection_time, '0.4f')} seconds.\n\t"
      f"Total transmission time for {len(sock_list)} clients: {format(transmission_time, '0.4f')} seconds.\n\t"
      f"Total bytes sent to server: {total_bytes_sent}.\n\t"
      f"Each client sent an average of {int(avg_bytes_sent)} bytes to the server.\n\t"
      f"Each client sent an average of {int(avg_requests)} requests to the server.\n\t"
      f"The average response time to each client packet: {format(avg_response_time_of_clients, '0.4f')} seconds.\n\t"
      f"Each individual client transmission took {format(avg_connection_time, '0.4f')} seconds on average.")

if LOG:
    if exists('./client_log.txt'):
        with open('./client_log.txt', 'a', encoding='utf-8') as log:
            log.write(
                f"{format(connection_time, '0.4f')} {format(transmission_time, '0.4f')} {total_bytes_sent} {int(avg_bytes_sent)} {int(avg_requests)} {format(avg_response_time_of_clients, '0.4f')} {format(avg_connection_time, '0.4f')}\n")
    else:
        with open('./client_log.txt', 'a', encoding='utf-8') as log:
            log.write(f"connection_time total_trans_time total_bytes avg_bytes avg_requests avg_response indv_trans_time\n")
            log.write(
                f"{format(connection_time, '0.4f')} {format(transmission_time, '0.4f')} {total_bytes_sent} {int(avg_bytes_sent)} {int(avg_requests)} {format(avg_response_time_of_clients, '0.4f')} {format(avg_connection_time, '0.4f')}\n")
