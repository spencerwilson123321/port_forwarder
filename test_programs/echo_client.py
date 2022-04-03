import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("10.0.0.159", 8000))
print("Connected")
msg = input("Enter a message: ")
msg = msg.encode("utf-8")
sock.send(msg)
print(f"data sent: {msg}")
data = sock.recv(1024)
print(f"data received: {data}")
sock.close()
