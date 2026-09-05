import socket
import threading

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = "127.0.0.1"
port = 7002

s.bind((host, port))
s.listen(5)
clients = []
names = []

def broadcast(msg):
    for c in clients:
        c.send(msg)

def handler(client):
    while True:
        try:
            respond = client.recv(2048)
            broadcast(respond)
        except:
            index = clients.index(client)
            clients.remove(index)
            name = names[index]
            broadcast(f"{name} has left the room".encode('utf-8'))
            names.remove(name)
            break



while True:
    client, address = s.accept()
    print(f"{address} has joind the chat")
    client.send("name ?".encode('utf-8'))
    name = client.recv(2048).decode('utf-8')
    print(f"{name} joind the room")
    clients.append(client)
    names.append(name)
    broadcast(f"{name} has joind the room".encode('utf-8'))
    client.send("you are now connected".encode('utf-8'))
    thread = threading.Thread(target=handler,args=(client,))
    thread.start()
