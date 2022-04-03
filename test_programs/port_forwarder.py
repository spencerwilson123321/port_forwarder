import socket
import select
import threading
import sys
import ipaddress

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

# Holds all connections
communication_map = {}

# Epoll object to handle client connections.
multiplexor = select.epoll()

# Epoll object to handle file descriptors currently involved in an established connection.
io = select.epoll()

# boolean for if the server is running or not. Used to signal shutdown of child thread.
running = True


# This function checks if the given address is a valid IPv4/IPv6 address, returns True if it
# is valid, and returns False if it is invalid.
def valid_ip(address):
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return False
    return True


# This function checks to make sure that the ports from the configuration file,
# are in the typical port range.
def validate_port_mappings():
    for key in port_mapping:
        if key > 65535 or key < 1:
            return False
        if port_mapping[key] > 65535 or port_mapping[key] < 1:
            return False
    return True


# Read config file and validate
try:
    with open('./config', 'r') as config:
        # Validate the configuration file to ensure it is using proper syntax and types.
        lines = config.readlines()
        if len(lines) <= 4:
            print("Incomplete Configuration File, there should be at least 5 lines.", file=sys.stderr)
            sys.exit(0)
        server_host_ipv4 = lines[0].split()[1]
        internal_host_ipv4 = lines[1].split()[1]
        server_host_ipv6 = lines[2].split()[1]
        internal_host_ipv6 = lines[3].split()[1]
        # Check whether IP addresses are valid IP addresses.
        if not (valid_ip(server_host_ipv4) and valid_ip(internal_host_ipv4)):
            print("Invalid IPv4 strings detected in config file.", file=sys.stderr)
            sys.exit(0)
        if not (valid_ip(server_host_ipv6) and valid_ip(internal_host_ipv6)):
            print("Invalid IPv6 strings detected in config file.", file=sys.stderr)
            sys.exit(0)
        # If the IPs are valid - check the port mappings.
        counter = 4
        while counter < len(lines):
            temp = lines[counter].split()
            try:
                port_mapping[int(temp[0])] = int(temp[1])
            except ValueError:
                print("Invalid data type for port mappings. Integers only.", file=sys.stderr)
                sys.exit(0)
            counter = counter + 1
        if not validate_port_mappings():
            print("Invalid ports supplied. Ports must be in the range 1 - 65535.", file=sys.stderr)
            sys.exit(0)
        print(f"Port Forwarder IPv4: {server_host_ipv4}")
        print(f"Port Forwarder IPv6: {server_host_ipv6}")
        print(f"Internal IPv4: {internal_host_ipv4}")
        print(f"Internal IPv6: {internal_host_ipv6}")
        print(f"Port Mapping: {port_mapping}")
except FileNotFoundError:
    print("No config file found. Make sure a file named 'config' is in the same directory as 'port_forwarder.py'.",
          file=sys.stderr)
    sys.exit(0)


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
        listen_ipv4_sock.listen(10000)
        listen_ipv6_sock.listen(10000)
        # Add sockets to socket dictionary
        listening_socket_list[listen_ipv4_sock.fileno()] = listen_ipv4_sock
        listening_socket_list[listen_ipv6_sock.fileno()] = listen_ipv6_sock
        # Register file descriptors into listening socket list.
        multiplexor.register(listen_ipv4_sock.fileno())
        multiplexor.register(listen_ipv6_sock.fileno())


def create_two_way_communication(external, internal):
    communication_map[external.fileno()] = (external, internal)
    communication_map[internal.fileno()] = (internal, external)


def communication_thread_shutdown():
    for key in communication_map:
        communication_map[key][0].close()
    io.close()


def main_thread_shutdown():
    for key in listening_socket_list:
        listening_socket_list[key].close()
    multiplexor.close()


def communication_thread():
    print("Two-Way Communication Thread Started")
    while running:
        events = io.poll(1)
        for fd, event in events:
            if event & select.EPOLLIN:
                read, write = communication_map[fd]
                # Receive the data and forward to the corresponding destination.
                try:
                    data = read.recv(1024)
                except ConnectionResetError:
                    pass
                if data == b"" or data == b"quit\n":
                    del communication_map[read.fileno()]
                    del communication_map[write.fileno()]
                    io.unregister(read.fileno())
                    io.unregister(write.fileno())
                    read.close()
                    write.close()
                    print("Connection Closed")
                else:
                    write.send(data)
    # Shutdown when main thread signals.
    communication_thread_shutdown()


def main(thread):
    # Set up listening sockets
    port_forward_setup()
    # Start threads which will monitor established connections.
    thread.start()
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
                io.register(internal_conn.fileno(), select.EPOLLIN)
                io.register(external_conn.fileno(), select.EPOLLIN)


if __name__ == '__main__':
    try:
        comm_thread = threading.Thread(target=communication_thread)
        main(comm_thread)
    except KeyboardInterrupt:
        running = False
        print("\nBeginning shutdown please wait...")
        comm_thread.join()
        main_thread_shutdown()
        print("Port Forwarder shutdown successfully")
