import socks  # SocksiPy module
import socket
import stem.process
from stem.util import term

class TorPlugin:
    def __init__(self, client):
        self.socks_port = 7000
        self.tor_process = {}
        self.original_socket = socket.socket
        self.mail_client = client


    def pre_connect(self):
        self.tor_process = stem.process.launch_tor_with_config(
          config = {
            'SocksPort': str(self.socks_port),
          },
          init_msg_handler = self.print_bootstrap_lines,
        )
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', self.socks_port)
        socket.socket = socks.socksocket

    def post_deconnect(self):
        self.tor_process.kill()
        socket.socket = self.original_socket

    def print_bootstrap_lines(self, line):
        if "Bootstrapped " in line:
            self.mail_client.update_tor_status(line)
            print(term.format(line, term.Color.BLUE))
