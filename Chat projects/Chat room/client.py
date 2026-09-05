import socket
import threading

name = input("Enter username: ")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

host = "127.0.0.1"
port = 8001

s.connect((host, port))

def recieve():
    while True:
        try:
            respond = s.recv(2048).decode('utf-8')
            if respond == "name ?":
                s.send(name.encode('utf-8'))
            else:
                print(respond)
        except:
            print("error!!")
            s.close()
            break

def send():
    while True:
        msg = f"{name}: {input()}"
        s.send(msg.encode('utf-8'))

recv_thred = threading.Thread(target=recieve)
recv_thred.start()

send_thred = threading.Thread(target=send)
send_thred.start()
