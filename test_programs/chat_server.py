import ssl
import socket
import select
import sys
import atexit
import queue
import argparse

# Command Line Argument Parsing
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--server", dest="server", help="Server IP")
parser.add_argument("-p", "--port", dest="port", help="Server port number to listen on")
args = parser.parse_args()

# Check command line arguments are valid.
if args.server is None or args.port is None:
    print(f"Invalid Arguments: use -h for list of accepted arguments. -s and -p flags must both be present.")
    sys.exit(0)

# Server Variables
address = args.server
port = int(args.port)
BUFF_SIZE = 1024


# Exit handler which is called on program termination
def exit_handler():
    for sock in inputs:
        sock.close()
    print("\nServer closing... all client connections terminated.")


atexit.register(exit_handler)

try:
    # Main Loop
    if __name__ == "__main__":

        # Create, bind, and start listening on main server socket.
        server_addr = (address, port)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(server_addr)
        server.listen(5)
        print(f"Server listening on: {address}:{port}")

        # Make server non-blocking.
        server.setblocking(0)

        # Create proper ssl context, using self generated keys, and certs.
        #context = ssl.SSLContext()
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain('./server.cert', './server_priv.key')

        # Define inputs,outputs list for select
        inputs = [server]
        outputs = []

        # Message queue to store client messages before sending to other clients.
        message_queues = {}

        # Main loop
        while inputs:
            read, write, exceptional = select.select(inputs, outputs, inputs)
            for s in read:
                # If server has a new connection.
                if s is server:
                    # Accept the connection.
                    conn, client_addr = s.accept()
                    # Set socket to non-blocking, this is necessary for select I believe.
                    conn.setblocking(0)
                    # Now wrap the socket in an SSLSocket. This means we have to handle it differently.
                    conn = context.wrap_socket(conn, do_handshake_on_connect=False, server_side=True)
                    # Add SSLSocket to input list and now we will be notified when
                    # there is data to be read. Select deals with raw sockets though so
                    # we will need to double check all the data from the SSL socket buffer
                    # has been read as well.
                    inputs.append(conn)
                    # Add the connection to the message queue dictionary.
                    message_queues[conn] = queue.Queue()
                    # Print connection accepted to stdout.
                    print(f"Connection Accepted from {conn.getpeername()}")
                    print("Updated list of clients:")
                    for cl in inputs:
                        if cl is not server:
                            print(cl.getpeername())
                else:
                    # Need to handle ssl.WANTREADERROR because we are dealing with non-blocking SSLSocket
                    # and not regular socket.
                    try:
                        data = s.recv(BUFF_SIZE)
                    except ssl.SSLError as e:
                        if e.errno != ssl.SSL_ERROR_WANT_READ:
                            raise
                        else:
                            continue
                    if not data:
                        break
                    data_left = s.pending()
                    while data_left:
                        data += s.recv(data_left)
                        data_left = s.pending()
                    # Data is received from a client
                    print(f"received {data} from {s.getpeername()}")
                    message_queues[s].put(data)
                    # Add to output list
                    if s not in outputs:
                            outputs.append(s)
                    #else:
                    #    # empty result means connection is closed
                    #    print(f"Closing connection {client_addr} after reading no data")
                    #    if s in outputs:
                    #        outputs.remove(s)
                    #    inputs.remove(s)
                    #    s.close()
                    #    del message_queues[s]
                    #    print("Updated list of clients:")
                    #    for cl in inputs:
                    #        if cl is not server:
                    #            print(cl.getpeername())

            for s in write:
                try:
                    next_msg = message_queues[s].get_nowait()
                except queue.Empty:
                    outputs.remove(s)
                else:
                    # Instead of just sending this back to the same person, go through the input list
                    # and send to everyone except for the server and the client.
                    for connection in inputs:
                        # if connection is not server and connection is not s:
                        if connection is not server and connection is not s:
                            print(f"Sending {next_msg} to {connection.getpeername()}")
                            connection.send(f"{s.getpeername()}: {next_msg.decode('utf-8')}".encode("utf-8"))

            for s in exceptional:
                print(f"Error for {s.getpeername()}")
                inputs.remove(s)
                if s in outputs:
                    outputs.remove(s)
                s.close()
                del message_queues[s]

except KeyboardInterrupt:
    sys.exit(0)
