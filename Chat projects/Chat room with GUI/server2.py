import socket
import threading
import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Client:
    """Encapsulates client data."""
    username: str
    socket: socket.socket
    address: tuple

class ChatServer:
    """Core server logic (no GUI dependencies)."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8001, 
                 on_status_change: Optional[Callable] = None,
                 on_message: Optional[Callable] = None):
        self.host = host
        self.port = port
        self.running = False
        self.socket: Optional[socket.socket] = None
        self.clients: dict[str, Client] = {}
        self.clients_lock = threading.Lock()
        
        # Callbacks for GUI updates
        self.on_status_change = on_status_change
        self.on_message = on_message
    
    def start(self):
        """Start the server."""
        if self.running:
            return
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.socket.settimeout(1.0)  # Prevent blocking indefinitely
            
            self.running = True
            self._notify_status(f"Server running on {self.host}:{self.port}")
            
            threading.Thread(target=self._accept_clients, daemon=True).start()
        except OSError as e:
            logger.error(f"Failed to start server: {e}")
            self._notify_status(f"Error: {e}")
    
    def stop(self):
        """Stop the server gracefully."""
        self.running = False
        
        # Close all client connections
        with self.clients_lock:
            clients_copy = list(self.clients.values())
        
        for client in clients_copy:
            self._close_client(client)
        
        if self.socket:
            self.socket.close()
            self.socket = None
        
        self._notify_status("Server stopped")
    
    def _accept_clients(self):
        """Accept incoming client connections."""
        while self.running:
            try:
                client_socket, address = self.socket.accept()
                username = self._generate_username()
                
                client = Client(username=username, socket=client_socket, address=address)
                
                # Send username to client
                try:
                    client_socket.sendall(username.encode())
                except (socket.error, BrokenPipeError):
                    client_socket.close()
                    continue
                
                # Store client
                with self.clients_lock:
                    self.clients[username] = client
                
                self.broadcast(f"{username} has joined the chat")
                
                # Handle client in separate thread
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
                
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                logger.error(f"Error accepting client: {e}")
    
    def _handle_client(self, client: Client):
        """Handle messages from a single client."""
        try:
            client.socket.settimeout(5.0)
            while self.running:
                try:
                    message = client.socket.recv(1024).decode('utf-8', errors='ignore').strip()
                    
                    if not message:
                        break
                    
                    self.broadcast(f"{client.username}: {message}")
                    
                except socket.timeout:
                    continue
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    break
                except Exception as e:
                    logger.error(f"Error reading from {client.username}: {e}")
                    break
        
        finally:
            self._remove_client(client.username)
    
    def _remove_client(self, username: str):
        """Remove client and notify others."""
        with self.clients_lock:
            client = self.clients.pop(username, None)
        
        if client:
            self._close_client(client)
            self.broadcast(f"{username} has left the chat")
    
    def _close_client(self, client: Client):
        """Close client socket safely."""
        try:
            client.socket.close()
        except Exception as e:
            logger.debug(f"Error closing socket for {client.username}: {e}")
    
    def broadcast(self, message: str):
        """Send message to all connected clients."""
        if self.on_message:
            self.on_message(message)
        
        with self.clients_lock:
            clients_copy = list(self.clients.values())
        
        dead_clients = []
        for client in clients_copy:
            try:
                client.socket.sendall(message.encode('utf-8'))
            except (socket.error, BrokenPipeError):
                dead_clients.append(client.username)
        
        # Clean up dead connections
        for username in dead_clients:
            self._remove_client(username)
    
    def _generate_username(self) -> str:
        """Generate unique username."""
        counter = 1
        with self.clients_lock:
            while f"User{counter}" in self.clients:
                counter += 1
        return f"User{counter}"
    
    def _notify_status(self, message: str):
        """Notify GUI of status change."""
        if self.on_status_change:
            self.on_status_change(message)
        logger.info(message)


class ServerGUI:
    """GUI layer for chat server."""
    
    def __init__(self, root: tk.Tk, port: int = 8001):
        self.root = root
        self.server = ChatServer(port=port, 
                                on_status_change=self._on_status_change,
                                on_message=self._on_message)
        
        self._build_gui()
    
    def _build_gui(self):
        """Build the GUI components."""
        self.root.title("Chat Room Server")
        self.root.geometry("400x300")
        
        # Status label
        self.status_label = tk.Label(
            self.root, 
            text="Server stopped", 
            wraplength=300,
            font=("Arial", 10)
        )
        self.status_label.pack(pady=10)
        
        # Message log
        self.log_frame = tk.Frame(self.root)
        self.log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(self.log_frame, text="Chat Log:").pack(anchor="w")
        
        scrollbar = tk.Scrollbar(self.log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(self.log_frame, height=10, yscrollcommand=scrollbar.set)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # Buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)
        
        self.start_button = tk.Button(
            button_frame, 
            text="Start Server", 
            command=self._start_server,
            bg="green",
            fg="white"
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = tk.Button(
            button_frame, 
            text="Stop Server", 
            command=self._stop_server,
            bg="red",
            fg="white",
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
    
    def _start_server(self):
        """Start server and update GUI."""
        self.server.start()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
    
    def _stop_server(self):
        """Stop server and update GUI."""
        self.server.stop()
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
    
    def _on_status_change(self, message: str):
        """Update status label from server."""
        self.status_label.config(text=message)
    
    def _on_message(self, message: str):
        """Log message to chat log."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    gui = ServerGUI(root, port=8001)
    root.mainloop()
Key Improvements:
Issue	Solution
Blocking accept()	Added settimeout(1.0) to allow graceful shutdown
Thread safety	Added threading.Lock() for self.clients dictionary
Unhandled exceptions	Comprehensive try/except with logging
Socket errors on broadcast	Catches errors per-client, removes dead clients
GUI coupling	Separated ChatServer (core logic) from ServerGUI (UI)
No logging	Added logging module for debugging
Type hints	Added type annotations for clarity
Better data structure	Created Client dataclass instead of dict
Chat history	Added Text widget to display messages
Graceful shutdown	Proper stop() method that closes all clients
Further Enhancements (Optional):
Persistent storage — Save chat history to a database
User authentication — Add login/password system
Custom message protocol — Use JSON for structured data (username, timestamp, etc.)
Queue-based messaging — Use queue.Queue instead of direct socket sends
Async I/O — Replace threading with asyncio for better scalability
Would you like me to implement any of these enhancements?

could you rewrite above code to include authentication

View file Chat projects/Chat room with GUI/server.py
Here's a complete rewrite with user authentication, including user registration, login, secure password hashing, and persistent user storage:

Python
import socket
import threading
import tkinter as tk
from tkinter import messagebox
import json
import os
import hashlib
import secrets
from dataclasses import dataclass, asdict
from typing import Callable, Optional, Dict
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# USER MANAGEMENT
# ============================================================================

@dataclass
class User:
    """User account information."""
    username: str
    password_hash: str
    created_at: str
    
    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return hashlib.sha256(password.encode()).hexdigest() == self.password_hash
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()


class UserManager:
    """Manages user accounts and persistence."""
    
    def __init__(self, users_file: str = "users.json"):
        self.users_file = users_file
        self.users: Dict[str, User] = {}
        self.users_lock = threading.Lock()
        self._load_users()
    
    def _load_users(self):
        """Load users from JSON file."""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    data = json.load(f)
                    for username, user_data in data.items():
                        self.users[username] = User(**user_data)
                logger.info(f"Loaded {len(self.users)} users from {self.users_file}")
            except Exception as e:
                logger.error(f"Failed to load users: {e}")
    
    def _save_users(self):
        """Save users to JSON file."""
        try:
            with open(self.users_file, 'w') as f:
                data = {username: asdict(user) for username, user in self.users.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save users: {e}")
    
    def register(self, username: str, password: str) -> tuple[bool, str]:
        """Register a new user."""
        if not username or not password:
            return False, "Username and password cannot be empty"
        
        if len(username) < 3:
            return False, "Username must be at least 3 characters"
        
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        
        with self.users_lock:
            if username in self.users:
                return False, "Username already exists"
            
            password_hash = User.hash_password(password)
            user = User(
                username=username,
                password_hash=password_hash,
                created_at=datetime.now().isoformat()
            )
            self.users[username] = user
            self._save_users()
        
        logger.info(f"User registered: {username}")
        return True, f"User '{username}' registered successfully"
    
    def login(self, username: str, password: str) -> tuple[bool, str]:
        """Authenticate user."""
        with self.users_lock:
            if username not in self.users:
                return False, "Invalid username or password"
            
            user = self.users[username]
            if not user.verify_password(password):
                return False, "Invalid username or password"
        
        logger.info(f"User logged in: {username}")
        return True, f"Welcome, {username}!"
    
    def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        with self.users_lock:
            return username in self.users
    
    def get_all_users(self) -> list[str]:
        """Get list of all usernames."""
        with self.users_lock:
            return list(self.users.keys())


# ============================================================================
# CLIENT SESSION
# ============================================================================

@dataclass
class Client:
    """Connected client session."""
    username: str
    socket: socket.socket
    address: tuple
    authenticated: bool = False


# ============================================================================
# CHAT SERVER WITH AUTHENTICATION
# ============================================================================

class AuthenticatedChatServer:
    """Chat server with user authentication."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8001,
                 on_status_change: Optional[Callable] = None,
                 on_message: Optional[Callable] = None,
                 on_user_count: Optional[Callable] = None):
        self.host = host
        self.port = port
        self.running = False
        self.socket: Optional[socket.socket] = None
        self.clients: Dict[str, Client] = {}
        self.clients_lock = threading.Lock()
        
        # User management
        self.user_manager = UserManager()
        
        # Callbacks for GUI updates
        self.on_status_change = on_status_change
        self.on_message = on_message
        self.on_user_count = on_user_count
    
    def start(self):
        """Start the server."""
        if self.running:
            return
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.socket.settimeout(1.0)
            
            self.running = True
            self._notify_status(f"Server running on {self.host}:{self.port}")
            self._notify_message(f"[SERVER] {len(self.user_manager.get_all_users())} registered users")
            
            threading.Thread(target=self._accept_clients, daemon=True).start()
        except OSError as e:
            logger.error(f"Failed to start server: {e}")
            self._notify_status(f"Error: {e}")
    
    def stop(self):
        """Stop the server gracefully."""
        self.running = False
        
        with self.clients_lock:
            clients_copy = list(self.clients.values())
        
        for client in clients_copy:
            self._close_client(client)
        
        if self.socket:
            self.socket.close()
            self.socket = None
        
        self._notify_status("Server stopped")
    
    def _accept_clients(self):
        """Accept incoming client connections."""
        while self.running:
            try:
                client_socket, address = self.socket.accept()
                client = Client(username="<unauthenticated>", socket=client_socket, 
                               address=address, authenticated=False)
                
                logger.info(f"New connection from {address}")
                
                # Handle authentication in separate thread
                threading.Thread(target=self._authenticate_client, args=(client,), 
                                daemon=True).start()
                
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                logger.error(f"Error accepting client: {e}")
    
    def _authenticate_client(self, client: Client):
        """Handle user authentication/registration."""
        try:
            client.socket.settimeout(30.0)
            
            # Send authentication prompt
            prompt = json.dumps({
                "type": "auth_prompt",
                "message": "Enter 'login' or 'register'"
            }) + "\n"
            client.socket.sendall(prompt.encode('utf-8'))
            
            # Get choice
            choice = client.socket.recv(1024).decode('utf-8').strip().lower()
            
            if choice == "register":
                success, message = self._handle_registration(client)
            elif choice == "login":
                success, message = self._handle_login(client)
            else:
                success, message = False, "Invalid choice"
            
            # Send authentication result
            response = json.dumps({
                "type": "auth_result",
                "success": success,
                "message": message,
                "username": client.username if success else None
            }) + "\n"
            
            client.socket.sendall(response.encode('utf-8'))
            
            if success:
                client.authenticated = True
                
                # Add to authenticated clients
                with self.clients_lock:
                    self.clients[client.username] = client
                
                self._update_user_count()
                self.broadcast(f"[SERVER] {client.username} has joined the chat", 
                             exclude=client.username)
                self._notify_message(f"{client.username} joined")
                
                # Handle messages
                self._handle_client(client)
            else:
                client.socket.close()
        
        except socket.timeout:
            self._notify_message("Client auth timeout")
            client.socket.close()
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            client.socket.close()
    
    def _handle_registration(self, client: Client) -> tuple[bool, str]:
        """Handle user registration."""
        try:
            # Get username
            username_msg = json.dumps({"type": "input", "field": "username"}) + "\n"
            client.socket.sendall(username_msg.encode('utf-8'))
            username = client.socket.recv(1024).decode('utf-8').strip()
            
            # Get password
            password_msg = json.dumps({"type": "input", "field": "password"}) + "\n"
            client.socket.sendall(password_msg.encode('utf-8'))
            password = client.socket.recv(1024).decode('utf-8').strip()
            
            # Register
            success, message = self.user_manager.register(username, password)
            if success:
                client.username = username
            
            return success, message
        
        except Exception as e:
            return False, f"Registration error: {str(e)}"
    
    def _handle_login(self, client: Client) -> tuple[bool, str]:
        """Handle user login."""
        try:
            # Get username
            username_msg = json.dumps({"type": "input", "field": "username"}) + "\n"
            client.socket.sendall(username_msg.encode('utf-8'))
            username = client.socket.recv(1024).decode('utf-8').strip()
            
            # Get password
            password_msg = json.dumps({"type": "input", "field": "password"}) + "\n"
            client.socket.sendall(password_msg.encode('utf-8'))
            password = client.socket.recv(1024).decode('utf-8').strip()
            
            # Authenticate
            success, message = self.user_manager.login(username, password)
            if success:
                client.username = username
            
            return success, message
        
        except Exception as e:
            return False, f"Login error: {str(e)}"
    
    def _handle_client(self, client: Client):
        """Handle messages from authenticated client."""
        try:
            client.socket.settimeout(5.0)
            
            while self.running and client.authenticated:
                try:
                    message = client.socket.recv(1024).decode('utf-8', errors='ignore').strip()
                    
                    if not message:
                        break
                    
                    # Parse JSON message or treat as plain text
                    try:
                        data = json.loads(message)
                        msg_text = data.get("message", message)
                    except:
                        msg_text = message
                    
                    self.broadcast(f"{client.username}: {msg_text}")
                    self._notify_message(f"{client.username}: {msg_text}")
                    
                except socket.timeout:
                    continue
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    break
                except Exception as e:
                    logger.error(f"Error reading from {client.username}: {e}")
                    break
        
        finally:
            self._remove_client(client.username)
    
    def _remove_client(self, username: str):
        """Remove client and notify others."""
        with self.clients_lock:
            client = self.clients.pop(username, None)
        
        if client:
            self._close_client(client)
            self.broadcast(f"[SERVER] {username} has left the chat", exclude=username)
            self._notify_message(f"{username} left")
            self._update_user_count()
    
    def _close_client(self, client: Client):
        """Close client socket safely."""
        try:
            client.socket.close()
        except Exception as e:
            logger.debug(f"Error closing socket for {client.username}: {e}")
    
    def broadcast(self, message: str, exclude: Optional[str] = None):
        """Send message to all authenticated clients."""
        with self.clients_lock:
            clients_copy = list(self.clients.values())
        
        dead_clients = []
        
        for client in clients_copy:
            if exclude and client.username == exclude:
                continue
            
            try:
                msg_packet = json.dumps({
                    "type": "message",
                    "content": message
                }) + "\n"
                client.socket.sendall(msg_packet.encode('utf-8'))
            except (socket.error, BrokenPipeError):
                dead_clients.append(client.username)
        
        # Clean up dead connections
        for username in dead_clients:
            self._remove_client(username)
    
    def _update_user_count(self):
        """Update connected user count."""
        with self.clients_lock:
            count = len(self.clients)
        
        if self.on_user_count:
            self.on_user_count(count)
    
    def _notify_status(self, message: str):
        """Notify GUI of status change."""
        if self.on_status_change:
            self.on_status_change(message)
        logger.info(message)
    
    def _notify_message(self, message: str):
        """Notify GUI of new message."""
        if self.on_message:
            self.on_message(message)


# ============================================================================
# GUI APPLICATION
# ============================================================================

class ChatServerGUI:
    """GUI for authenticated chat server."""
    
    def __init__(self, root: tk.Tk, port: int = 8001):
        self.root = root
        self.server = AuthenticatedChatServer(
            port=port,
            on_status_change=self._on_status_change,
            on_message=self._on_message,
            on_user_count=self._on_user_count
        )
        
        self._build_gui()
    
    def _build_gui(self):
        """Build the GUI components."""
        self.root.title("Authenticated Chat Room Server")
        self.root.geometry("500x450")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Header frame
        header_frame = tk.Frame(self.root, bg="lightblue", height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(header_frame, text="Chat Server with Authentication", 
                font=("Arial", 14, "bold"), bg="lightblue").pack()
        
        self.status_label = tk.Label(
            header_frame,
            text="Server stopped",
            font=("Arial", 10),
            bg="lightblue"
        )
        self.status_label.pack()
        
        # User count
        self.user_count_label = tk.Label(
            header_frame,
            text="Connected Users: 0",
            font=("Arial", 9),
            bg="lightblue"
        )
        self.user_count_label.pack()
        
        # Log frame
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(log_frame, text="Server Log:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_frame, height=15, yscrollcommand=scrollbar.set)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # Button frame
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)
        
        self.start_button = tk.Button(
            button_frame,
            text="Start Server",
            command=self._start_server,
            bg="green",
            fg="white",
            font=("Arial", 10),
            padx=15,
            pady=5
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = tk.Button(
            button_frame,
            text="Stop Server",
            command=self._stop_server,
            bg="red",
            fg="white",
            font=("Arial", 10),
            padx=15,
            pady=5,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Credentials frame (for demo purposes)
        demo_frame = tk.LabelFrame(self.root, text="Demo Credentials", padx=10, pady=5)
        demo_frame.pack(fill=tk.X, padx=10, pady=5)
        
        demo_text = tk.Text(demo_frame, height=3, width=50)
        demo_text.pack()
        demo_text.insert(tk.END, "Register new user or login with existing credentials\n")
        demo_text.insert(tk.END, "Credentials are saved in users.json file\n")
        demo_text.config(state=tk.DISABLED)
    
    def _start_server(self):
        """Start server and update GUI."""
        self.server.start()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
    
    def _stop_server(self):
        """Stop server and update GUI."""
        self.server.stop()
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
    
    def _on_status_change(self, message: str):
        """Update status label."""
        self.status_label.config(text=message)
    
    def _on_message(self, message: str):
        """Log message to server log."""
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
    
    def _on_user_count(self, count: int):
        """Update user count display."""
        self.user_count_label.config(text=f"Connected Users: {count}")
    
    def _on_closing(self):
        """Handle window closing."""
        if messagebox.askokcancel("Quit", "Stop server and quit?"):
            self.server.stop()
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    gui = ChatServerGUI(root, port=8001)
    root.mainloop()