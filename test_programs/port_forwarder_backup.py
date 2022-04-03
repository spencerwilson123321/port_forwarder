import socket
import select
import threading

# Network Variables
server_host_ipv4 = ''
internal_host_ipv4 = ''
server_host_ipv6 = ''
internal_host_ipv6 = ''

# Contains port mappings where:
#   key = external facing port on port forwarder, value = port of internal machine to forward to.
port_mapping = {}

# This holds all the listening sockets where key = file descriptor, and val = socket obj
listening_socket_list = {}

# This holds all the external connections made where key = file descriptor, and val = (socket, socket)
external_to_internal_map = {}

# This holds all the internal connections made where key = file descriptor, and val = (socket, socket)
internal_to_external_map = {}

# Epoll object to handle client connections.
multiplexor = select.epoll()

# Epoll object to handle external facing file descriptors
external_io = select.epoll()

# Epoll object to handle internal facing file descriptors
internal_io = select.epoll()

# boolean for if the server is running or not. Used to signal shutdown of child threads.
running = True


# Read config file
with open('./config', 'r') as config:
    lines = config.readlines()
    server_host_ipv4 = lines[0].split()[1]
    internal_host_ipv4 = lines[1].split()[1]
    server_host_ipv6 = lines[2].split()[1]
    internal_host_ipv6 = lines[3].split()[1]
    print(f"Port Forwarder IPv4: {server_host_ipv4}")
    print(f"Port Forwarder IPv6: {server_host_ipv6}")
    print(f"Internal IPv4: {internal_host_ipv4}")
    print(f"Internal IPv6: {internal_host_ipv6}")
    counter = 4
    while counter < len(lines):
        temp = lines[counter].split()
        port_mapping[int(temp[0])] = int(temp[1])
        counter = counter + 1
    print(f"Port Mapping: {port_mapping}")

# This function creates and sets up all the listening server sockets.
def port_forward_setup():
    # For each mapping: create a socket, set the socket options, bind, and register.
    for key in port_mapping:
        # Create ipv4 and ipv6 listening sockets
        listen_ipv4_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_ipv6_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        # Set socket options
        listen_ipv4_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_ipv6_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_ipv4_sock.setblocking(0)
        listen_ipv6_sock.setblocking(0)
        # Bind sockets to each port, the first index of each mapping is the port
        # that will be outwardly facing on the port forwarder.
        listen_ipv4_sock.bind((server_host_ipv4, key))
        listen_ipv6_sock.bind((server_host_ipv6, key))
        # Start listening on the socket.
        listen_ipv4_sock.listen(5)
        listen_ipv6_sock.listen(5)
        # Add sockets to socket dictionary
        listening_socket_list[listen_ipv4_sock.fileno()] = listen_ipv4_sock
        listening_socket_list[listen_ipv6_sock.fileno()] = listen_ipv6_sock
        # Register file descriptors into listening socket list.
        multiplexor.register(listen_ipv4_sock.fileno())
        multiplexor.register(listen_ipv6_sock.fileno())


def create_two_way_communication(external, internal):
    external_to_internal_map[external.fileno()] = (external, internal)
    internal_to_external_map[internal.fileno()] = (internal, external)


def display_current_connections():
    print("Current Connections:")
    for key in external_to_internal_map:
        print(f"{external_to_internal_map[key][0].getpeername()} --> {external_to_internal_map[key][1].getpeername()}")


# This checks if there is data ready to be transferred, and transfers it to the correct location using
# the internal_to_external map.
def internal_to_external_thread():
    print("Internal thread started")
    while running:
        events = internal_io.poll(1)
        for fd, event in events:
            if event & select.EPOLLIN:
                internal, external = internal_to_external_map[fd]
                # Receive the data and forward to the external host.
                try:
                    data = internal.recv(1024)
                except ConnectionResetError:
                    pass
                if data == b"" or data == b"quit\n":
                    del external_to_internal_map[external.fileno()]
                    del internal_to_external_map[internal.fileno()]
                    external_io.unregister(external.fileno())
                    internal_io.unregister(internal.fileno())
                    external.close()
                    internal.close()
                else:
                    external.send(data)
                

# This checks if there is data ready to be transferred, and transfers it to the correct location using
# the external_to_internal map.
def external_to_internal_thread():
    print("External thread started")
    while running:
        events = external_io.poll(1)
        for fd, event in events:
            if event & select.EPOLLIN:
                external, internal = external_to_internal_map[fd]
                try:
                    data = external.recv(1024)
                except ConnectionResetError:
                    pass
                if data == b"" or data == b"quit\n":
                    del external_to_internal_map[external.fileno()]
                    del internal_to_external_map[internal.fileno()]
                    external_io.unregister(external.fileno())
                    internal_io.unregister(internal.fileno())
                    external.close()
                    internal.close()
                    print("External Connection closed")
                    display_current_connections()
                else:
                    internal.send(data)


def main(internal_thread, external_thread):
    # Set up listening sockets
    port_forward_setup()
    # Start threads which will monitor established connections.
    internal_thread.start()
    external_thread.start()
    while True:
        # Poll the listening socket polling object
        # and accept all the incoming connections.
        events = multiplexor.poll(1)
        if len(events) == 0:
            continue
        for fd, event in events:
            if event == select.EPOLLIN:
                external_conn, addr = listening_socket_list[fd].accept()
                print(f"Connection established to {external_conn.getsockname()} from external host {external_conn.getpeername()}")
                # Once the connection is established between the pf and the external host, create the subsequent
                # connection between the pf and the internal host using the port map.
                if external_conn.family == socket.AF_INET:
                    internal_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    internal_conn.connect((internal_host_ipv4, port_mapping[external_conn.getsockname()[1]]))
                    print(f"Establishing connection from {external_conn.getsockname()} to internal host {(internal_host_ipv4, port_mapping[external_conn.getsockname()[1]])}")
                else:
                    internal_conn = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    internal_conn.connect((internal_host_ipv6, port_mapping[external_conn.getsockname()[1]]))
                    print(f"Establishing connection from {external_conn.getsockname()} to internal host {(internal_host_ipv4, port_mapping[external_conn.getsockname()[1]])}")
                # Once both connections are made, pass the sockets into the create_two_way_communication function.
                create_two_way_communication(external_conn, internal_conn)
                # Once two way communication data structure is established, register the sockets into the
                # data transfer epoll object.
                internal_conn.setblocking(0)
                external_conn.setblocking(0)
                internal_io.register(internal_conn.fileno(), select.EPOLLIN)
                external_io.register(external_conn.fileno(), select.EPOLLIN)
                display_current_connections()


if __name__ == '__main__':
    try:
        internal_thread = threading.Thread(target=internal_to_external_thread)
        external_thread = threading.Thread(target=external_to_internal_thread)
        main(internal_thread, external_thread)
    except KeyboardInterrupt:
        running = False
        print("\nBeginning shutdown please wait...")
        internal_thread.join()
        external_thread.join()
        print("Port Forwarder shutdown successfully")




