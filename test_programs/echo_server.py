import socket

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('10.0.0.131', 8000))
server.listen(5)
while True:
    conn, addr = server.accept()
    print(f"Connection received from {conn.getpeername()}")
    data = conn.recv(1024)
    if data == '':
        conn.close()
    print(f"Received: {data}")
    echo = b'Echo -->  ' + data
    conn.send(echo)
    print("Data echoed")

