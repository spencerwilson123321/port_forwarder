import ssl
import sys
import threading
import socket
from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import date
import tkinter
from tkinter import *

# Command Line Argument Parsing
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--server", dest="server", help="Server IP address", required=True)
parser.add_argument("-p", "--port", dest="port", help="Server port number", required=True)
parser.add_argument("-w", "--write", dest="file", required=False, default=0, help="Write the conversation to a file with "
                                                                                             "the given filename. If this flag"
                                                                                             " is not present, then no log file "
                                                                                             "will be created.")

args = parser.parse_args()


# Client Variables
filename = args.file
server = (args.server, int(args.port))
BUFF_SIZE = 1024
WRITE = args.file != 0
CONNECTED = True
if WRITE:
    with open(filename, "a") as file:
        file.write(f"Conversation on : {date.today()}\n")

try:

    # Main Block
    if __name__ == "__main__":

        def recv_data(s):
            while CONNECTED:
                try:
                    data = s.recv(BUFF_SIZE)
                except BlockingIOError:
                    continue
                except ssl.SSLError:
                    continue
                if data:
                    T.insert(tkinter.END, data.decode("utf-8") + "\n")
                    T.see(tkinter.END)
                    if WRITE:
                        with open(filename, "a") as file:
                            file.write(f"{data.decode('utf-8')}\n")

        def send_data(e):
            data = User_input.get()
            if data:
                sock.send(data.encode("utf-8"))
                T.insert(tkinter.END, f"{sock.getsockname()}: {data}\n")
                User_input.delete(first=0, last='end')
                if WRITE:
                    # write to a log file.
                    with open(filename, "a") as file:
                        file.write(f"{sock.getsockname()}: {data}\n")

        print(f"Server IP: {args.server}, Server Port: {args.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        context = ssl.SSLContext()
        #context = ssl.SSLContext()
        #context.load_cert_chain(certfile="./cacert.pem", keyfile="./cakey.pem", password="password")
        context.load_verify_locations(capath='./cacert.pem')
        sock = context.wrap_socket(sock=sock, server_hostname="10.0.0.202")
        sock.connect(server)
        sock.setblocking(0)
        recv_thread = threading.Thread(target=recv_data, args=[sock])
        recv_thread.start()

        window = Tk()
        User_input = Entry()
        User_input.bind("<Return>", func=send_data)
        User_input.pack()
        T = Text(window, height=5, width=52)
        T.pack()
        window.mainloop()

        # If the client window is closed, then the program needs to exit.
        print(f"Closing Connection to: {server}")
        if WRITE:
            with open(filename, 'a') as file:
                file.write(f"Closing Connection to: {server}\n")
        CONNECTED = False
        sock.close()
        recv_thread.join()
        sys.exit(0)

except KeyboardInterrupt:
    sock.close()
    sys.exit(0)
