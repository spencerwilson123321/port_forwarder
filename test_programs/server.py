#!/usr/bin/python3.9
import select
import os
import ssl
import signal
from contextlib import contextmanager
import socket
from select import epoll
from multiprocessing import Process, Pipe


class Server:

    BUFF_SIZE = 1024

    def __init__(self):
        self.epoll = epoll()
        self.client_sd_list = {}
        self.client_msg_list = {}
        self.server_msg_list = {}
        self.request_count_list = {}
        self.data_sent = {}
        self.pipe = None
        # Create SSL context
        self.context = ssl.SSLContext()
        self.context.load_cert_chain('./server.cert', './server_priv.key')
        self.context.load_verify_locations(capath='./cacert.pem')

    # The main method of the server object.
    def start_server(self, pipe):
        try:
            self.pipe = pipe
            while True:
                while self.pipe.poll():
                    try:
                        conn = self.pipe.recv()
                        # conn = socket.fromfd(sd, family=socket.AF_INET, type=socket.SOCK_STREAM)
                        conn = self.context.wrap_socket(conn, do_handshake_on_connect=True, server_side=True)
                    except RuntimeError:
                        continue
                    sd = conn.fileno()
                    self.epoll.register(sd, select.EPOLLIN)
                    self.request_count_list[sd] = 0
                    self.data_sent[sd] = 0
                    self.client_sd_list[sd] = conn
                    self.client_msg_list[sd] = ''
                    self.server_msg_list[sd] = ''
                    print(f"PID:{os.getpid()} Registered client socket descriptor {sd}.")

                events = self.epoll.poll(1)

                if len(events) == 0:
                    continue
                for sd, event in events:
                    if event & select.EPOLLIN:
                        self.read_msg(sd)
                    if event & select.EPOLLOUT:
                        self.data_sent[sd] += self.send_msg(sd)

        except KeyboardInterrupt:
            self.close_connections()

    # Closes all connections in the client connection list.
    def close_connections(self):
        print(f"\nProcess PID: {os.getpid()} closing all connections.")
        self.generate_statistics()
        for key in self.client_sd_list:
            self.client_sd_list[key].close()
            self.epoll.close()

    def generate_statistics(self):
        total_data_sent = self.calc_sum(self.data_sent)
        average_data_sent = total_data_sent / len(self.data_sent)
        average_num_requests = self.calc_average(self.request_count_list)
        self.pipe.send((total_data_sent, average_data_sent, average_num_requests))

    def calc_sum(self, dictionary):
        sum = 0
        for key in dictionary:
            sum += dictionary[key]
        return sum

    def calc_average(self, dictionary):
        sum = 0
        size = len(dictionary)
        for key in dictionary:
            sum += dictionary[key]
        return sum/size

    def send_msg(self, sd):
        # Send the server's response to the client.
        num_bytes = self.client_sd_list[sd].send(self.server_msg_list[sd].encode("utf-8"))
        self.server_msg_list[sd] = ''
        self.epoll.modify(sd, select.EPOLLIN)
        return num_bytes

    def read_msg(self, sd):
        try:
            # Read the client message and place into client msg dict.
            self.client_msg_list[sd] = self.client_sd_list[sd].recv(self.BUFF_SIZE).decode("utf-8")
        except ConnectionResetError:
            pass
        # If we receive an empty string or quit then the client is closing the connection.
        if self.client_msg_list[sd] == 'quit\n' or self.client_msg_list[sd] == '':
            print("[{:02d}] Client Connection closed!".format(sd))
            # Remove client sd from epoll object.
            self.epoll.unregister(sd)
            # Close the client connection.
            self.client_sd_list[sd].close()
            # Remove sd from all dictionaries.
            del self.client_sd_list[sd], self.client_msg_list[sd], self.server_msg_list[sd]
        else:
            # Change the client sd from read to write mode for next iteration.
            self.epoll.modify(sd, select.EPOLLOUT)
            msg = self.client_msg_list[sd]
            self.request_count_list[sd] += 1
            self.server_msg_list[sd] = msg
            self.client_msg_list[sd] = ''
